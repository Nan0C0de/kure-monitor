import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Lightbulb,
  Play,
  RefreshCw,
  AlertTriangle,
  Download,
  ChevronDown,
  Info,
} from "lucide-react";
import { api } from "../services/api";
import AdviceFindingCard from "./AdviceFindingCard";
import AdviceScopePicker from "./AdviceScopePicker";

/**
 * AdvicePanel — owns advice findings list, scope picker state, scan progress.
 *
 * The parent Dashboard funnels `advice_*` WebSocket messages into this panel
 * via the `wsEvent` prop (counter-bumped on every new message so we can react
 * via useEffect without re-applying on re-renders).
 */
const AdvicePanel = ({
  isDark = false,
  canWrite = true,
  wsEvent = null, // {seq, type, data} — seq increments per message
}) => {
  const [findings, setFindings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showDismissed, setShowDismissed] = useState(false);
  const [scope, setScope] = useState({
    namespace: undefined,
    workload_kind: undefined,
    workload_name: undefined,
    pod_name: undefined,
  });

  // Scan progress tracking — only one banner at a time.
  const [scanStatus, setScanStatus] = useState(null); // null | 'started' | 'failed'
  const [scanScope, setScanScope] = useState(null);
  const [scanError, setScanError] = useState(null);
  const [scanRequesting, setScanRequesting] = useState(false);
  const [hasCompletedScan, setHasCompletedScan] = useState(false);
  const activeScanIdRef = useRef(null);

  // Keep a ref of showDismissed so the WS event effect (which intentionally
  // only depends on wsEvent.seq) can read the current value without going
  // stale between toggles.
  const showDismissedRef = useRef(showDismissed);
  useEffect(() => {
    showDismissedRef.current = showDismissed;
  }, [showDismissed]);

  // Export menu state.
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState(null);
  const exportMenuRef = useRef(null);

  // Detector coverage banner state.
  // Populated from /api/advice/detectors on mount; silently swallows errors so
  // a failed fetch never breaks the panel.
  const [detectorCoverage, setDetectorCoverage] = useState(null);

  // ----- Loading findings -----
  const loadFindings = useCallback(async () => {
    try {
      setLoading(true);
      const params = {};
      if (showDismissed) params.include_dismissed = true;
      const res = await api.getAdviceFindings(params);
      setFindings(res?.findings || []);
      setError(null);
    } catch (err) {
      console.error("Failed to load advice findings:", err);
      setError("Failed to load advice findings.");
    } finally {
      setLoading(false);
    }
  }, [showDismissed]);

  useEffect(() => {
    loadFindings();
  }, [loadFindings]);

  // Reset the "scan completed" flag whenever the scope changes. Without this,
  // after scanning namespace A, switching to namespace B would show
  // "No improvements suggested — this scope looks healthy" even though B was
  // never scanned. `showDismissed` is intentionally NOT a dep: it's view state.
  useEffect(() => {
    setHasCompletedScan(false);
  }, [
    scope.namespace,
    scope.workload_kind,
    scope.workload_name,
    scope.pod_name,
  ]);

  // ----- Detector coverage (for "FYI: Hubble unavailable" banner) -----
  useEffect(() => {
    let cancelled = false;
    const loadCoverage = async () => {
      try {
        const data = await api.getAdviceDetectors();
        if (cancelled) return;
        const detectors = Array.isArray(data?.detectors) ? data.detectors : [];
        const hubbleAvailable = !!data?.hubble_status?.available;
        let totalEnabled = 0;
        let activeEnabled = 0;
        for (const d of detectors) {
          if (!d?.enabled) continue;
          totalEnabled += 1;
          if (!d.requires_hubble || hubbleAvailable) {
            activeEnabled += 1;
          }
        }
        setDetectorCoverage({
          totalEnabled,
          activeEnabled,
          gatedCount: totalEnabled - activeEnabled,
          hubbleAvailable,
        });
      } catch (err) {
        // Silent: the panel works fine without the banner.
        console.warn("Failed to load advice detector coverage:", err);
      }
    };
    loadCoverage();
    return () => {
      cancelled = true;
    };
  }, []);

  // ----- WS event handling -----
  useEffect(() => {
    if (!wsEvent) return;
    const { type, data } = wsEvent;
    if (!type || !data) return;

    if (type === "advice_finding") {
      // Upsert by id.
      setFindings((prev) => {
        const idx = prev.findIndex((f) => f.id === data.id);
        if (idx >= 0) {
          const next = [...prev];
          next[idx] = { ...prev[idx], ...data };
          return next;
        }
        // If we're not showing dismissed and the incoming one is dismissed,
        // skip insertion. Otherwise prepend.
        if (!showDismissedRef.current && data.dismissed) {
          return prev;
        }
        return [data, ...prev];
      });
    } else if (type === "advice_finding_deleted") {
      setFindings((prev) => prev.filter((f) => f.id !== data.id));
    } else if (type === "advice_scan_status") {
      const status = data.status;
      if (status === "started") {
        activeScanIdRef.current = data.scan_id;
        setScanStatus("started");
        setScanScope(data.scope || null);
        setScanError(null);
      } else if (status === "completed") {
        // Only clear if this is the scan we were tracking (or no active scan).
        if (
          !activeScanIdRef.current ||
          activeScanIdRef.current === data.scan_id
        ) {
          activeScanIdRef.current = null;
          setScanStatus(null);
          setScanScope(null);
          setHasCompletedScan(true);
          // Safety-net refresh of findings (WS upserts may have already done it).
          loadFindings();
        }
      } else if (status === "failed") {
        if (
          !activeScanIdRef.current ||
          activeScanIdRef.current === data.scan_id
        ) {
          activeScanIdRef.current = null;
          setScanStatus("failed");
          setScanError("Scan failed — check backend logs");
        }
      }
    }
    // wsEvent.seq changes on each new message, ensuring this effect re-runs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wsEvent]);

  // ----- Actions -----
  const handleRunScan = async () => {
    if (scanRequesting) return;
    setScanRequesting(true);
    setScanError(null);
    try {
      const res = await api.runAdviceScan(scope);
      // Backend returns scan_id and immediate findings; WS will deliver
      // upserts and a completion event. If WS never tells us "started" first
      // (race), the response itself is a strong signal — but we let WS drive
      // the banner. If findings arrived synchronously, merge them in.
      if (res?.findings && Array.isArray(res.findings)) {
        setFindings((prev) => {
          const byId = new Map(prev.map((f) => [f.id, f]));
          for (const f of res.findings) {
            byId.set(f.id, { ...(byId.get(f.id) || {}), ...f });
          }
          return Array.from(byId.values());
        });
        // The sync response is also "scan completed" evidence; the WS event
        // sets this too, but the response wins races against slow sockets.
        setHasCompletedScan(true);
      }
    } catch (err) {
      console.error("Failed to run advice scan:", err);
      setScanError(err?.message || "Failed to start scan");
      setScanStatus("failed");
    } finally {
      setScanRequesting(false);
    }
  };

  const handleDismiss = async (finding) => {
    // Optimistic: remove from the visible list (if not showing dismissed) or
    // mark as dismissed in place (if showing dismissed).
    const prevFindings = findings;
    setFindings((prev) =>
      showDismissed
        ? prev.map((f) => (f.id === finding.id ? { ...f, dismissed: true } : f))
        : prev.filter((f) => f.id !== finding.id),
    );
    try {
      await api.dismissAdviceFinding(finding.id);
    } catch (err) {
      console.error("Failed to dismiss advice finding:", err);
      // Roll back on failure.
      setFindings(prevFindings);
    }
  };

  const handleRestore = async (finding) => {
    const prevFindings = findings;
    setFindings((prev) =>
      prev.map((f) => (f.id === finding.id ? { ...f, dismissed: false } : f)),
    );
    try {
      await api.restoreAdviceFinding(finding.id);
    } catch (err) {
      console.error("Failed to restore advice finding:", err);
      setFindings(prevFindings);
    }
  };

  // ----- Export -----
  // Close the export menu when clicking outside.
  useEffect(() => {
    if (!exportMenuOpen) return undefined;
    const handleClick = (e) => {
      if (
        exportMenuRef.current &&
        !exportMenuRef.current.contains(e.target)
      ) {
        setExportMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [exportMenuOpen]);

  const handleExport = async (format) => {
    if (exporting) return;
    setExportMenuOpen(false);
    setExportError(null);
    setExporting(true);
    try {
      const params = {};
      if (showDismissed) params.include_dismissed = true;
      // The panel currently surfaces scope (namespace/workload/pod) only as
      // scan input — apply matching filters to the export so the file mirrors
      // what the user sees when a narrow scope is set.
      if (scope?.namespace) params.namespace = scope.namespace;
      if (scope?.workload_kind) params.resource_kind = scope.workload_kind;
      if (scope?.workload_name) params.resource_name = scope.workload_name;
      await api.downloadAdviceFindings(format, params);
    } catch (err) {
      console.error("Failed to export advice findings:", err);
      setExportError(err?.message || "Failed to export findings");
    } finally {
      setExporting(false);
    }
  };

  // ----- Derived list -----
  const sortedFindings = React.useMemo(() => {
    const order = { high: 1, medium: 2, low: 3, info: 4 };
    return [...findings].sort((a, b) => {
      const sa = order[(a.severity || "").toLowerCase()] || 99;
      const sb = order[(b.severity || "").toLowerCase()] || 99;
      if (sa !== sb) return sa - sb;
      // Prefer non-dismissed first within same severity.
      if (!!a.dismissed !== !!b.dismissed) return a.dismissed ? 1 : -1;
      return (b.id || 0) - (a.id || 0);
    });
  }, [findings]);

  const scopeSummary = () => {
    const parts = [];
    const s = scanScope || scope;
    if (s?.namespace) parts.push(`ns=${s.namespace}`);
    if (s?.workload_kind) parts.push(`kind=${s.workload_kind}`);
    if (s?.workload_name) parts.push(`name=${s.workload_name}`);
    if (s?.pod_name) parts.push(`pod=${s.pod_name}`);
    return parts.length > 0 ? parts.join(", ") : "whole cluster";
  };

  return (
    <div className="p-4">
      {/* Header: title + show-dismissed toggle */}
      <div className="flex flex-wrap items-center justify-between mb-4 gap-2">
        <div className="flex items-center space-x-2">
          <Lightbulb
            className={`w-5 h-5 ${isDark ? "text-yellow-400" : "text-yellow-500"}`}
          />
          <h2
            className={`text-lg font-semibold ${
              isDark ? "text-gray-100" : "text-gray-900"
            }`}
          >
            AI Advice
          </h2>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center text-sm cursor-pointer">
            <input
              type="checkbox"
              className="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
              checked={showDismissed}
              onChange={(e) => setShowDismissed(e.target.checked)}
            />
            <span
              className={`ml-2 ${isDark ? "text-gray-300" : "text-gray-700"}`}
            >
              Show dismissed
            </span>
          </label>

          {/* Export dropdown */}
          <div className="relative" ref={exportMenuRef}>
            <button
              type="button"
              onClick={() => setExportMenuOpen((v) => !v)}
              disabled={
                exporting || loading || sortedFindings.length === 0
              }
              aria-haspopup="menu"
              aria-expanded={exportMenuOpen}
              title={
                sortedFindings.length === 0
                  ? "No findings to export"
                  : "Export findings"
              }
              className={`inline-flex items-center px-3 py-1.5 text-sm font-medium rounded-md border transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                isDark
                  ? "border-gray-600 bg-gray-700 hover:bg-gray-600 text-gray-200"
                  : "border-gray-300 bg-white hover:bg-gray-50 text-gray-700"
              }`}
            >
              <Download className="w-4 h-4 mr-1.5" />
              {exporting ? "Exporting…" : "Export"}
              <ChevronDown className="w-3.5 h-3.5 ml-1.5" />
            </button>
            {exportMenuOpen && (
              <div
                role="menu"
                className={`absolute right-0 mt-1 z-20 min-w-[10rem] rounded-md border shadow-lg ${
                  isDark
                    ? "bg-gray-800 border-gray-700"
                    : "bg-white border-gray-200"
                }`}
              >
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => handleExport("json")}
                  className={`block w-full text-left px-3 py-2 text-sm ${
                    isDark
                      ? "text-gray-200 hover:bg-gray-700"
                      : "text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  Export as JSON
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => handleExport("csv")}
                  className={`block w-full text-left px-3 py-2 text-sm ${
                    isDark
                      ? "text-gray-200 hover:bg-gray-700"
                      : "text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  Export as CSV
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Detector coverage banner — informational, only when Hubble gates
          one or more enabled detectors. */}
      {detectorCoverage &&
        detectorCoverage.gatedCount > 0 &&
        !detectorCoverage.hubbleAvailable && (
          <div
            data-testid="advice-detector-coverage-banner"
            className={`mb-4 p-3 rounded-lg border flex items-start text-sm ${
              isDark
                ? "bg-blue-900/20 border-blue-800 text-blue-200"
                : "bg-blue-50 border-blue-200 text-blue-800"
            }`}
          >
            <Info
              className={`w-4 h-4 mr-2 mt-0.5 flex-shrink-0 ${
                isDark ? "text-blue-300" : "text-blue-600"
              }`}
            />
            <span>
              {detectorCoverage.activeEnabled} of{" "}
              {detectorCoverage.totalEnabled} detectors active. Install Cilium
              + Hubble to unlock {detectorCoverage.gatedCount} network-flow
              detector
              {detectorCoverage.gatedCount === 1 ? "" : "s"}.{" "}
              <a
                href="https://github.com/nan0c0de/kure-monitor/blob/main/docs/AI-ADVICE-LAYER2.md"
                target="_blank"
                rel="noopener noreferrer"
                className={`underline ${
                  isDark
                    ? "text-blue-300 hover:text-blue-200"
                    : "text-blue-700 hover:text-blue-900"
                }`}
              >
                Learn more
              </a>
            </span>
          </div>
        )}

      {/* Scope picker + run scan */}
      <div
        className={`mb-4 rounded-lg border p-3 ${
          isDark
            ? "bg-gray-900/40 border-gray-700"
            : "bg-gray-50 border-gray-200"
        }`}
      >
        <AdviceScopePicker
          scope={scope}
          onChange={setScope}
          isDark={isDark}
          disabled={scanRequesting || scanStatus === "started"}
        />
        <div className="mt-3 flex items-center justify-between">
          <span
            className={`text-xs ${isDark ? "text-gray-400" : "text-gray-500"}`}
          >
            Scope: <span className="font-mono">{scopeSummary()}</span>
          </span>
          {canWrite && (
            <button
              type="button"
              onClick={handleRunScan}
              disabled={scanRequesting || scanStatus === "started"}
              className={`inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                isDark
                  ? "border-blue-600 bg-blue-700 hover:bg-blue-600 text-white"
                  : "border-blue-600 bg-blue-600 hover:bg-blue-700 text-white"
              }`}
            >
              {scanRequesting || scanStatus === "started" ? (
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Play className="w-4 h-4 mr-2" />
              )}
              {scanRequesting
                ? "Requesting…"
                : scanStatus === "started"
                  ? "Scanning…"
                  : "Run scan"}
            </button>
          )}
        </div>
      </div>

      {/* Scan-in-progress banner */}
      {scanStatus === "started" && (
        <div
          className={`mb-4 p-3 rounded-lg border flex items-center ${
            isDark
              ? "bg-blue-900/30 border-blue-700 text-blue-200"
              : "bg-blue-50 border-blue-200 text-blue-800"
          }`}
        >
          <RefreshCw className="w-5 h-5 mr-3 animate-spin" />
          <div className="text-sm">
            <p className="font-medium">Advice scan in progress…</p>
            <p
              className={`text-xs ${
                isDark ? "text-blue-300" : "text-blue-700"
              }`}
            >
              Scope: <span className="font-mono">{scopeSummary()}</span>
            </p>
          </div>
        </div>
      )}

      {/* Scan failed banner */}
      {scanStatus === "failed" && (
        <div
          className={`mb-4 p-3 rounded-lg border flex items-center justify-between ${
            isDark
              ? "bg-red-900/30 border-red-700 text-red-200"
              : "bg-red-50 border-red-200 text-red-800"
          }`}
        >
          <div className="flex items-center">
            <AlertTriangle className="w-5 h-5 mr-3" />
            <div className="text-sm">
              <p className="font-medium">{scanError || "Scan failed"}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              setScanStatus(null);
              setScanError(null);
            }}
            className={`text-xs underline ${
              isDark ? "text-red-300" : "text-red-700"
            }`}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Export error banner */}
      {exportError && (
        <div
          className={`mb-4 p-3 rounded-lg border flex items-center justify-between ${
            isDark
              ? "bg-red-900/30 border-red-700 text-red-200"
              : "bg-red-50 border-red-200 text-red-800"
          }`}
        >
          <div className="flex items-center">
            <AlertTriangle className="w-5 h-5 mr-3" />
            <p className="text-sm">{exportError}</p>
          </div>
          <button
            type="button"
            onClick={() => setExportError(null)}
            className={`text-xs underline ${
              isDark ? "text-red-300" : "text-red-700"
            }`}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Generic error banner */}
      {error && (
        <div
          className={`mb-4 p-3 rounded-lg border flex items-center ${
            isDark
              ? "bg-red-900/30 border-red-700 text-red-200"
              : "bg-red-50 border-red-200 text-red-800"
          }`}
        >
          <AlertTriangle className="w-5 h-5 mr-3" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      {/* Findings list */}
      {loading ? (
        <div className="py-12 text-center">
          <div className="inline-flex items-center space-x-2">
            <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <span className={isDark ? "text-gray-300" : "text-gray-700"}>
              Loading advice…
            </span>
          </div>
        </div>
      ) : sortedFindings.length === 0 ? (
        <div className="py-12 text-center">
          <Lightbulb
            className={`w-12 h-12 mx-auto mb-3 ${
              isDark ? "text-gray-600" : "text-gray-400"
            }`}
          />
          <h3
            className={`text-base font-medium mb-1 ${
              isDark ? "text-gray-100" : "text-gray-900"
            }`}
          >
            {hasCompletedScan && !showDismissed
              ? "No improvements suggested"
              : "No advice findings"}
          </h3>
          <p
            className={`text-sm ${isDark ? "text-gray-400" : "text-gray-600"}`}
          >
            {showDismissed
              ? "No findings — dismissed or active."
              : hasCompletedScan
                ? "This scope looks healthy — no architectural mismatches detected."
                : "Run a scan to surface scaling, startup, and capacity advice."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {sortedFindings.map((finding) => (
            <AdviceFindingCard
              key={finding.id}
              finding={finding}
              isDark={isDark}
              canWrite={canWrite}
              onDismiss={handleDismiss}
              onRestore={handleRestore}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default AdvicePanel;

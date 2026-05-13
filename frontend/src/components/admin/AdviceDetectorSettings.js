import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Lightbulb,
  AlertTriangle,
  X,
  Search,
  ChevronDown,
  ChevronRight,
  CheckCircle,
  RotateCcw,
  ToggleLeft,
  ToggleRight,
} from "lucide-react";
import { api } from "../../services/api";
import { useCanWrite } from "../../contexts/AuthContext";
import useModalA11y from "../../hooks/useModalA11y";

/**
 * AdviceDetectorSettings — admin panel section to enable/disable AI Advice
 * detectors. Settings are presented as a pop-up modal opened from a single
 * "Manage detectors" button. The modal groups detectors by category, supports
 * a search filter, bulk Enable/Disable/Reset actions, and per-row optimistic
 * toggles that hit `PUT /api/advice/detectors/{id}`.
 */

const severityClasses = (severity, isDark) => {
  switch ((severity || "").toLowerCase()) {
    case "critical":
      return isDark
        ? "bg-red-900/70 text-red-200 border border-red-600"
        : "bg-red-200 text-red-900 border border-red-400";
    case "high":
      return isDark
        ? "bg-red-900/50 text-red-300 border border-red-700"
        : "bg-red-100 text-red-800 border border-red-300";
    case "medium":
      return isDark
        ? "bg-yellow-900/50 text-yellow-300 border border-yellow-700"
        : "bg-amber-100 text-amber-800 border border-amber-300";
    case "low":
      return isDark
        ? "bg-blue-900/50 text-blue-300 border border-blue-700"
        : "bg-blue-100 text-blue-800 border border-blue-300";
    case "info":
    default:
      return isDark
        ? "bg-gray-700 text-gray-300 border border-gray-600"
        : "bg-gray-100 text-gray-700 border border-gray-300";
  }
};

const humanizeId = (id) => {
  if (!id) return "";
  return id
    .split(/[-_]/)
    .filter(Boolean)
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(" ");
};

/**
 * Derive a friendly title from a detector's description text. Backend
 * descriptions are typically a short phrase followed by more detail, separated
 * by an em-dash, en-dash, colon, or period. We take the first segment, trim
 * trailing trailing words, and capitalise it. Falls back to a humanised ID.
 */
const friendlyTitle = (detector) => {
  const desc = (detector?.description || "").trim();
  if (desc) {
    // Split on em-dash, en-dash, colon, or sentence-ending period+space.
    const parts = desc.split(/\s+[–—-]\s+|:\s+|\.\s+/);
    const head = (parts[0] || desc).trim().replace(/\.$/, "");
    if (head.length > 0 && head.length <= 80) {
      return head.charAt(0).toUpperCase() + head.slice(1);
    }
  }
  return humanizeId(detector?.id);
};

const humanizeCategory = (cat) => {
  if (!cat) return "Other";
  return cat
    .split(/[-_]/)
    .filter(Boolean)
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(" ");
};

const matchesQuery = (detector, query) => {
  if (!query) return true;
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const hay = [
    friendlyTitle(detector),
    detector.description || "",
    detector.category || "",
    detector.default_severity || "",
    detector.id || "",
  ]
    .join(" ")
    .toLowerCase();
  return hay.includes(q);
};

/* -------------------------------------------------------------------------- */
/* Toggle switch — controlled, accessible, no new deps.                       */
/* -------------------------------------------------------------------------- */

const ToggleSwitch = ({
  checked,
  disabled,
  onChange,
  ariaLabel,
  isDark,
  title,
}) => (
  <label
    className={`relative inline-flex items-center mt-0.5 ${
      disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"
    }`}
    title={title}
  >
    <input
      type="checkbox"
      className="sr-only peer"
      checked={!!checked}
      disabled={disabled}
      onChange={onChange}
      aria-label={ariaLabel}
      role="switch"
      aria-checked={!!checked}
    />
    <div
      className={`w-9 h-5 rounded-full transition-colors peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-offset-1 peer-focus:ring-purple-500 ${
        checked ? "bg-purple-600" : isDark ? "bg-gray-600" : "bg-gray-300"
      } after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-transform ${
        checked ? "after:translate-x-4" : ""
      }`}
    />
  </label>
);

/* -------------------------------------------------------------------------- */
/* Modal                                                                      */
/* -------------------------------------------------------------------------- */

const DetectorRow = ({
  detector,
  isDark,
  canWrite,
  pending,
  rowError,
  recentlySaved,
  hubbleAvailable,
  onToggle,
}) => {
  const requiresHubble = !!detector.requires_hubble;
  const hubbleBlocked = requiresHubble && !hubbleAvailable;
  const toggleDisabled = !canWrite || pending || hubbleBlocked;
  const title = friendlyTitle(detector);

  return (
    <li
      className={`px-4 py-3 ${hubbleBlocked ? "opacity-60" : ""} ${
        isDark ? "hover:bg-gray-800/40" : "hover:bg-gray-50"
      }`}
      data-detector-id={detector.id}
    >
      <div className="flex items-start gap-3">
        <ToggleSwitch
          checked={!!detector.enabled}
          disabled={toggleDisabled}
          onChange={() => onToggle(detector)}
          ariaLabel={`Toggle detector ${detector.id}`}
          isDark={isDark}
          title={
            hubbleBlocked
              ? "Cilium Hubble is not configured on this cluster, so this detector cannot run."
              : !canWrite
                ? "You do not have permission"
                : detector.enabled
                  ? "Click to disable"
                  : "Click to enable"
          }
        />

        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`text-sm font-medium ${
                isDark ? "text-gray-100" : "text-gray-900"
              }`}
            >
              {title}
            </span>
            <span
              className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wide ${severityClasses(
                detector.default_severity,
                isDark,
              )}`}
            >
              {(detector.default_severity || "info").toUpperCase()}
            </span>
            {requiresHubble && (
              <span
                className={`inline-block px-2 py-0.5 rounded-full text-[10px] ${
                  isDark
                    ? "bg-indigo-900/40 text-indigo-300 border border-indigo-700"
                    : "bg-indigo-100 text-indigo-800 border border-indigo-200"
                }`}
                title={
                  hubbleBlocked
                    ? "Hubble is not available on this cluster."
                    : "Requires Cilium Hubble."
                }
              >
                Needs Hubble
              </span>
            )}
            {recentlySaved && (
              <span
                className={`inline-flex items-center gap-1 text-[11px] transition-opacity ${
                  isDark ? "text-green-400" : "text-green-600"
                }`}
                data-testid={`saved-indicator-${detector.id}`}
              >
                <CheckCircle className="w-3 h-3" />
                Saved
              </span>
            )}
          </div>

          {detector.description && (
            <p
              className={`mt-1 text-xs ${
                isDark ? "text-gray-400" : "text-gray-600"
              }`}
              title={detector.description}
            >
              {detector.description}
            </p>
          )}

          <p
            className={`mt-1 text-[11px] font-mono ${
              isDark ? "text-gray-500" : "text-gray-400"
            }`}
          >
            {detector.id}
          </p>

          {hubbleBlocked && (
            <p
              className={`mt-1 text-[11px] italic ${
                isDark ? "text-gray-500" : "text-gray-500"
              }`}
            >
              skipped — needs Hubble
            </p>
          )}

          {rowError && (
            <p
              className={`mt-1 text-xs ${
                isDark ? "text-red-300" : "text-red-700"
              }`}
            >
              {rowError}
            </p>
          )}
        </div>
      </div>
    </li>
  );
};

const DetectorModal = ({
  isOpen,
  onClose,
  isDark,
  canWrite,
  detectors,
  hubbleStatus,
  pending,
  rowErrors,
  recentlySaved,
  onToggle,
  onBulkEnable,
  onBulkDisable,
  onResetDefaults,
  bulkRunning,
}) => {
  const dialogRef = useRef(null);
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState({}); // category -> bool

  useModalA11y({ isOpen, onClose, dialogRef });

  // Reset transient UI state each time the modal opens.
  useEffect(() => {
    if (isOpen) {
      setQuery("");
      setCollapsed({});
    }
  }, [isOpen]);

  const hubbleAvailable = !!hubbleStatus?.available;

  const grouped = useMemo(() => {
    const visible = detectors.filter((d) => matchesQuery(d, query));
    const map = new Map();
    visible.forEach((d) => {
      const cat = d.category || "other";
      if (!map.has(cat)) map.set(cat, []);
      map.get(cat).push(d);
    });
    // Sort categories alphabetically; within each, sort by title.
    return Array.from(map.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([cat, items]) => {
        const total = detectors.filter(
          (d) => (d.category || "other") === cat,
        ).length;
        const enabledCount = detectors.filter(
          (d) => (d.category || "other") === cat && d.enabled,
        ).length;
        const sortedItems = items.slice().sort((a, b) =>
          friendlyTitle(a).localeCompare(friendlyTitle(b), undefined, {
            sensitivity: "base",
          }),
        );
        return { category: cat, items: sortedItems, total, enabledCount };
      });
  }, [detectors, query]);

  const totalEnabled = detectors.filter((d) => d.enabled).length;

  if (!isOpen) return null;

  const titleId = "advice-detector-modal-title";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      data-testid="advice-detector-modal"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 transition-opacity"
        onClick={onClose}
        data-testid="advice-detector-modal-backdrop"
        aria-hidden="true"
      />

      {/* Dialog */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`relative w-full max-w-2xl max-h-[85vh] flex flex-col rounded-lg shadow-xl ${
          isDark ? "bg-gray-800 text-gray-100" : "bg-white text-gray-900"
        }`}
      >
        {/* Header */}
        <div
          className={`flex items-center justify-between px-5 py-3 border-b ${
            isDark ? "border-gray-700" : "border-gray-200"
          }`}
        >
          <div className="flex items-center gap-2">
            <Lightbulb
              className={`w-5 h-5 ${isDark ? "text-yellow-400" : "text-yellow-500"}`}
            />
            <h3 id={titleId} className="text-base font-semibold">
              Manage AI Advice detectors
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className={`p-1 rounded ${
              isDark
                ? "hover:bg-gray-700 text-gray-300"
                : "hover:bg-gray-100 text-gray-500"
            }`}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Controls */}
        <div
          className={`px-5 py-3 border-b space-y-3 ${
            isDark ? "border-gray-700" : "border-gray-200"
          }`}
        >
          {/* Search */}
          <div className="relative">
            <Search
              className={`absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 ${
                isDark ? "text-gray-500" : "text-gray-400"
              }`}
              aria-hidden="true"
            />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search detectors by name, category, severity…"
              aria-label="Search detectors"
              className={`w-full pl-8 pr-3 py-2 text-sm rounded-md border focus:outline-none focus:ring-2 focus:ring-purple-500 ${
                isDark
                  ? "bg-gray-900 border-gray-600 text-gray-100 placeholder-gray-500"
                  : "bg-white border-gray-300 text-gray-900 placeholder-gray-400"
              }`}
            />
          </div>

          {/* Bulk actions + Hubble status */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onBulkEnable}
              disabled={!canWrite || bulkRunning}
              className={`inline-flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-md border transition-colors ${
                isDark
                  ? "border-gray-600 text-gray-200 hover:bg-gray-700 disabled:opacity-50"
                  : "border-gray-300 text-gray-700 hover:bg-gray-100 disabled:opacity-50"
              }`}
            >
              <ToggleRight className="w-3.5 h-3.5" />
              Enable all
            </button>
            <button
              type="button"
              onClick={onBulkDisable}
              disabled={!canWrite || bulkRunning}
              className={`inline-flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-md border transition-colors ${
                isDark
                  ? "border-gray-600 text-gray-200 hover:bg-gray-700 disabled:opacity-50"
                  : "border-gray-300 text-gray-700 hover:bg-gray-100 disabled:opacity-50"
              }`}
            >
              <ToggleLeft className="w-3.5 h-3.5" />
              Disable all
            </button>
            <button
              type="button"
              onClick={onResetDefaults}
              disabled={!canWrite || bulkRunning}
              className={`inline-flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-md border transition-colors ${
                isDark
                  ? "border-gray-600 text-gray-200 hover:bg-gray-700 disabled:opacity-50"
                  : "border-gray-300 text-gray-700 hover:bg-gray-100 disabled:opacity-50"
              }`}
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Reset to defaults
            </button>

            <div className="ml-auto flex items-center gap-2 text-xs">
              <span
                aria-hidden="true"
                className={`inline-block w-2 h-2 rounded-full ${
                  hubbleAvailable ? "bg-green-500" : "bg-amber-500"
                }`}
              />
              <span className={isDark ? "text-gray-400" : "text-gray-600"}>
                {hubbleAvailable
                  ? `Hubble: connected — ${hubbleStatus?.flow_count ?? 0} recent flows`
                  : "Hubble: not configured"}
              </span>
            </div>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          {grouped.length === 0 ? (
            <div
              className={`py-10 text-center text-sm ${
                isDark ? "text-gray-400" : "text-gray-500"
              }`}
            >
              No detectors match your search.
            </div>
          ) : (
            <ul
              data-testid="advice-detector-list"
              className="divide-y divide-transparent"
            >
              {grouped.map(({ category, items, total, enabledCount }) => {
                const isCollapsed = !!collapsed[category];
                return (
                  <li key={category} data-testid={`category-group-${category}`}>
                    <button
                      type="button"
                      onClick={() =>
                        setCollapsed((prev) => ({
                          ...prev,
                          [category]: !prev[category],
                        }))
                      }
                      aria-expanded={!isCollapsed}
                      className={`w-full flex items-center justify-between px-5 py-2 text-left text-xs font-semibold uppercase tracking-wide ${
                        isDark
                          ? "bg-gray-900/50 text-gray-300 hover:bg-gray-900"
                          : "bg-gray-50 text-gray-700 hover:bg-gray-100"
                      }`}
                    >
                      <span className="flex items-center gap-2">
                        {isCollapsed ? (
                          <ChevronRight className="w-3.5 h-3.5" />
                        ) : (
                          <ChevronDown className="w-3.5 h-3.5" />
                        )}
                        {humanizeCategory(category)}
                      </span>
                      <span
                        className={`text-[11px] font-normal normal-case ${
                          isDark ? "text-gray-400" : "text-gray-500"
                        }`}
                      >
                        ({enabledCount} of {total} enabled)
                      </span>
                    </button>
                    {!isCollapsed && (
                      <ul
                        className={`divide-y ${
                          isDark ? "divide-gray-700" : "divide-gray-200"
                        }`}
                      >
                        {items.map((d) => (
                          <DetectorRow
                            key={d.id}
                            detector={d}
                            isDark={isDark}
                            canWrite={canWrite}
                            pending={!!pending[d.id]}
                            rowError={rowErrors[d.id]}
                            recentlySaved={!!recentlySaved[d.id]}
                            hubbleAvailable={hubbleAvailable}
                            onToggle={onToggle}
                          />
                        ))}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Footer */}
        <div
          className={`flex items-center justify-between px-5 py-3 border-t ${
            isDark ? "border-gray-700" : "border-gray-200"
          }`}
        >
          <div
            className={`text-xs ${isDark ? "text-gray-400" : "text-gray-600"}`}
          >
            {totalEnabled} of {detectors.length} detector
            {detectors.length === 1 ? "" : "s"} enabled
          </div>
          <button
            type="button"
            onClick={onClose}
            className={`px-3 py-1.5 text-sm rounded-md ${
              isDark
                ? "bg-gray-700 hover:bg-gray-600 text-gray-100"
                : "bg-gray-100 hover:bg-gray-200 text-gray-800"
            }`}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

/* -------------------------------------------------------------------------- */
/* Outer component                                                            */
/* -------------------------------------------------------------------------- */

const AdviceDetectorSettings = ({ isDark = false, onError, onSuccess }) => {
  const canWrite = useCanWrite();

  const [detectors, setDetectors] = useState([]);
  const [hubbleStatus, setHubbleStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [rowErrors, setRowErrors] = useState({});
  const [pending, setPending] = useState({});
  const [recentlySaved, setRecentlySaved] = useState({}); // {id: true}
  const [bulkRunning, setBulkRunning] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);

  const savedTimers = useRef({});

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setLoading(true);
        const data = await api.getAdviceDetectors();
        if (cancelled) return;
        const sorted = (data?.detectors || []).slice().sort((a, b) => {
          const ai = (a.id || "").toLowerCase();
          const bi = (b.id || "").toLowerCase();
          return ai < bi ? -1 : ai > bi ? 1 : 0;
        });
        setDetectors(sorted);
        setHubbleStatus(data?.hubble_status || null);
        setLoadError(null);
      } catch (err) {
        if (cancelled) return;
        const msg = "Failed to load advice detectors";
        setLoadError(msg);
        if (onError) onError(msg);
        console.error("Error loading advice detectors:", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [onError]);

  // Clean up "Saved" indicator timers on unmount.
  useEffect(() => {
    const timers = savedTimers.current;
    return () => {
      Object.values(timers).forEach((t) => clearTimeout(t));
    };
  }, []);

  const flashSaved = (id) => {
    setRecentlySaved((prev) => ({ ...prev, [id]: true }));
    if (savedTimers.current[id]) {
      clearTimeout(savedTimers.current[id]);
    }
    savedTimers.current[id] = setTimeout(() => {
      setRecentlySaved((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      delete savedTimers.current[id];
    }, 2000);
  };

  // Single-detector toggle with optimistic update + rollback.
  const setDetectorEnabled = async (detector, newEnabled) => {
    if (!canWrite) return false;
    if (detector.enabled === newEnabled) return true;

    setDetectors((prev) =>
      prev.map((d) =>
        d.id === detector.id ? { ...d, enabled: newEnabled } : d,
      ),
    );
    setRowErrors((prev) => {
      const next = { ...prev };
      delete next[detector.id];
      return next;
    });
    setPending((prev) => ({ ...prev, [detector.id]: true }));

    try {
      await api.setAdviceDetectorEnabled(detector.id, newEnabled);
      flashSaved(detector.id);
      if (onSuccess) {
        onSuccess(
          `Detector "${detector.id}" ${newEnabled ? "enabled" : "disabled"}.`,
        );
      }
      return true;
    } catch (err) {
      setDetectors((prev) =>
        prev.map((d) =>
          d.id === detector.id ? { ...d, enabled: detector.enabled } : d,
        ),
      );
      setRowErrors((prev) => ({
        ...prev,
        [detector.id]: err?.message || "Failed to update detector",
      }));
      console.error("Error toggling detector:", err);
      return false;
    } finally {
      setPending((prev) => {
        const next = { ...prev };
        delete next[detector.id];
        return next;
      });
    }
  };

  const handleToggle = (detector) => {
    if (pending[detector.id]) return;
    setDetectorEnabled(detector, !detector.enabled);
  };

  const handleBulk = async (targetState) => {
    if (!canWrite || bulkRunning) return;
    setBulkRunning(true);
    try {
      // Snapshot the current list so we can iterate predictably.
      const snapshot = detectors.slice();
      for (const d of snapshot) {
        if (d.enabled === targetState) continue;
        // eslint-disable-next-line no-await-in-loop
        await setDetectorEnabled(d, targetState);
      }
    } finally {
      setBulkRunning(false);
    }
  };

  const handleBulkEnable = () => handleBulk(true);
  const handleBulkDisable = () => handleBulk(false);
  // Defaults = all enabled (matches backend default state).
  const handleResetDefaults = () => handleBulk(true);

  const totalEnabled = detectors.filter((d) => d.enabled).length;
  const hubbleAvailable = !!hubbleStatus?.available;

  return (
    <div>
      <div className="mb-4 flex items-center">
        <Lightbulb
          className={`w-5 h-5 mr-2 ${isDark ? "text-yellow-400" : "text-yellow-500"}`}
        />
        <h2
          className={`text-lg font-semibold ${
            isDark ? "text-gray-100" : "text-gray-900"
          }`}
        >
          AI Advice — Detector Settings
        </h2>
      </div>
      <p
        className={`text-sm mb-4 ${isDark ? "text-gray-400" : "text-gray-600"}`}
      >
        Choose which AI Advice detectors run during scans. Disabled detectors
        are skipped entirely.
      </p>

      {/* Summary card with manage button */}
      <div
        className={`p-4 border rounded-md flex flex-wrap items-center gap-4 ${
          isDark
            ? "bg-gray-800/50 border-gray-700"
            : "bg-gray-50 border-gray-200"
        }`}
      >
        <div className="flex-1 min-w-[200px]">
          {loading ? (
            <div
              className={`text-sm ${isDark ? "text-gray-400" : "text-gray-500"}`}
            >
              Loading detectors…
            </div>
          ) : (
            <>
              <div
                className={`text-sm font-medium ${
                  isDark ? "text-gray-100" : "text-gray-900"
                }`}
              >
                {totalEnabled} of {detectors.length} detector
                {detectors.length === 1 ? "" : "s"} enabled
              </div>
              <div className="mt-1 flex items-center gap-2 text-xs">
                <span
                  aria-hidden="true"
                  className={`inline-block w-2 h-2 rounded-full ${
                    hubbleAvailable ? "bg-green-500" : "bg-amber-500"
                  }`}
                />
                <span className={isDark ? "text-gray-400" : "text-gray-600"}>
                  {hubbleAvailable
                    ? `Hubble: connected — ${hubbleStatus?.flow_count ?? 0} recent flows`
                    : "Hubble: not configured (Layer-2 detectors will be skipped)"}
                </span>
              </div>
            </>
          )}
        </div>
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          disabled={!!loadError}
          className={`inline-flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors ${
            isDark
              ? "bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-50"
              : "bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-50"
          }`}
        >
          <Lightbulb className="w-4 h-4" />
          Manage detectors
        </button>
      </div>

      {loadError && (
        <div
          className={`mt-4 p-3 border rounded-md flex items-center ${
            isDark
              ? "bg-red-900/30 border-red-700 text-red-200"
              : "bg-red-50 border-red-200 text-red-800"
          }`}
        >
          <AlertTriangle className="w-4 h-4 mr-2" />
          <span className="text-sm">{loadError}</span>
        </div>
      )}

      <DetectorModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        isDark={isDark}
        canWrite={canWrite}
        detectors={detectors}
        hubbleStatus={hubbleStatus}
        pending={pending}
        rowErrors={rowErrors}
        recentlySaved={recentlySaved}
        onToggle={handleToggle}
        onBulkEnable={handleBulkEnable}
        onBulkDisable={handleBulkDisable}
        onResetDefaults={handleResetDefaults}
        bulkRunning={bulkRunning}
      />
    </div>
  );
};

export default AdviceDetectorSettings;

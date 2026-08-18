import React, { useState } from "react";
import {
  AlertTriangle,
  AlertCircle,
  Info,
  ChevronDown,
  ChevronRight,
  Trash2,
  RotateCcw,
} from "lucide-react";
import { api } from "../services/api";
import SolutionMarkdown from "./SolutionMarkdown";

/**
 * A single advice finding card.
 *
 * Collapsed by default — shows severity badge, namespace chip, detector chip,
 * category chip, confidence, title, resource line, plus the dismiss/restore
 * affordance. Clicking the header (or pressing Space/Enter on it) expands to
 * reveal summary, recommended_change, explanation, and evidence toggle.
 *
 * The LLM explanation is fetched lazily on first expand — the scan endpoint
 * persists `explanation: null` to avoid paying LLM cost at scan time. We cache
 * the result locally and bubble the populated finding back up to the parent
 * via `onExplained` so the panel's canonical findings state stays in sync.
 */
const AdviceFindingCard = ({
  finding,
  isDark = false,
  canWrite = true,
  onDismiss,
  onRestore,
  onExplained,
}) => {
  const [expanded, setExpanded] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  // Local cache of an explanation we fetched on demand. Lets a collapse +
  // re-expand cycle render the existing content without a re-fetch even if
  // the parent prop hasn't been refreshed yet.
  const [cachedExplanation, setCachedExplanation] = useState(
    finding.explanation || null,
  );
  const [explanationLoading, setExplanationLoading] = useState(false);
  const [explanationFetched, setExplanationFetched] = useState(
    !!finding.explanation,
  );

  const panelId = `advice-finding-details-${finding.id}`;

  const getSeverityColor = (severity) => {
    switch ((severity || "").toLowerCase()) {
      case "high":
        return isDark
          ? "bg-red-900/50 text-red-300 border-red-700"
          : "bg-red-100 text-red-800 border-red-300";
      case "medium":
        return isDark
          ? "bg-yellow-900/50 text-yellow-300 border-yellow-700"
          : "bg-amber-100 text-amber-800 border-amber-300";
      case "low":
        return isDark
          ? "bg-blue-900/50 text-blue-300 border-blue-700"
          : "bg-blue-100 text-blue-800 border-blue-300";
      case "info":
      default:
        return isDark
          ? "bg-gray-700 text-gray-300 border-gray-600"
          : "bg-gray-100 text-gray-700 border-gray-300";
    }
  };

  const getSeverityIcon = (severity) => {
    switch ((severity || "").toLowerCase()) {
      case "high":
      case "medium":
        return <AlertTriangle className="w-4 h-4" />;
      case "low":
        return <AlertCircle className="w-4 h-4" />;
      case "info":
      default:
        return <Info className="w-4 h-4" />;
    }
  };

  const handleDismiss = async (e) => {
    if (e) e.stopPropagation();
    if (!onDismiss || busy) return;
    setBusy(true);
    try {
      await onDismiss(finding);
    } finally {
      setBusy(false);
    }
  };

  const handleRestore = async (e) => {
    if (e) e.stopPropagation();
    if (!onRestore || busy) return;
    setBusy(true);
    try {
      await onRestore(finding);
    } finally {
      setBusy(false);
    }
  };

  const fetchExplanation = async () => {
    if (explanationFetched || explanationLoading) return;
    setExplanationLoading(true);
    try {
      const updated = await api.explainAdviceFinding(finding.id);
      const newExplanation = updated?.explanation || null;
      setCachedExplanation(newExplanation);
      setExplanationFetched(true);
      if (onExplained && updated) {
        onExplained(updated);
      }
    } catch (err) {
      // Mark as fetched so we don't spin again on re-expand; surface the
      // existing fallback copy in the explanation slot.
      console.error("Failed to fetch advice explanation:", err);
      setExplanationFetched(true);
    } finally {
      setExplanationLoading(false);
    }
  };

  const handleToggleExpand = () => {
    const willExpand = !expanded;
    setExpanded(willExpand);
    if (willExpand && !cachedExplanation && !explanationFetched) {
      fetchExplanation();
    }
  };

  const confidencePct =
    typeof finding.confidence === "number"
      ? Math.round(finding.confidence * 100)
      : null;

  const dismissed = !!finding.dismissed;

  return (
    <div
      data-testid="advice-finding-card"
      className={`rounded-lg border shadow-sm transition-opacity ${
        dismissed ? "opacity-60" : "opacity-100"
      } ${isDark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"}`}
    >
      <div className="p-4">
        {/* Clickable header (collapsed summary). The entire header is one
            button so keyboard focus + Space/Enter naturally toggles. */}
        <button
          type="button"
          onClick={handleToggleExpand}
          aria-expanded={expanded}
          aria-controls={panelId}
          className={`w-full text-left rounded-md focus:outline-none focus:ring-2 ${
            isDark
              ? "focus:ring-blue-500"
              : "focus:ring-blue-400"
          }`}
        >
          {/* Chip row: severity + ns + detector + category + dismissed + confidence */}
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span
              className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-medium border ${getSeverityColor(
                finding.severity,
              )}`}
            >
              {getSeverityIcon(finding.severity)}
              <span className="ml-1">
                {(finding.severity || "info").toUpperCase()}
              </span>
            </span>

            {finding.namespace && (
              <span
                className={`inline-block px-2 py-0.5 rounded font-mono text-xs ${
                  isDark
                    ? "bg-gray-700 text-gray-300 border border-gray-600"
                    : "bg-gray-100 text-gray-700 border border-gray-200"
                }`}
                title="Namespace"
              >
                ns: {finding.namespace}
              </span>
            )}

            <span
              className={`inline-block px-2 py-0.5 rounded font-mono text-xs ${
                isDark
                  ? "bg-gray-700 text-gray-300 border border-gray-600"
                  : "bg-gray-100 text-gray-700 border border-gray-200"
              }`}
              title="Detector identifier"
            >
              {finding.detector_id}
            </span>

            {finding.category && (
              <span
                className={`inline-block px-2 py-0.5 rounded text-xs ${
                  isDark
                    ? "bg-indigo-900/40 text-indigo-300"
                    : "bg-indigo-100 text-indigo-800"
                }`}
              >
                {finding.category}
              </span>
            )}

            {dismissed && (
              <span
                className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                  isDark
                    ? "bg-gray-700 text-gray-400 border border-gray-600"
                    : "bg-gray-200 text-gray-600 border border-gray-300"
                }`}
              >
                Dismissed
              </span>
            )}

            {confidencePct !== null && (
              <span
                className={`ml-auto text-xs ${
                  isDark ? "text-gray-400" : "text-gray-500"
                }`}
              >
                confidence: {confidencePct}%
              </span>
            )}

            {/* Chevron disclosure indicator */}
            <span
              aria-hidden="true"
              className={`ml-1 inline-flex items-center ${
                isDark ? "text-gray-400" : "text-gray-500"
              }`}
            >
              {expanded ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
            </span>
          </div>

          {/* Title */}
          <h3
            className={`text-base font-semibold mb-1 ${
              isDark ? "text-gray-100" : "text-gray-900"
            }`}
          >
            {finding.title}
          </h3>

          {/* Resource line */}
          <p
            className={`text-sm ${
              isDark ? "text-gray-400" : "text-gray-600"
            }`}
          >
            <span className="font-medium">
              {finding.resource_kind}/{finding.resource_name}
            </span>
          </p>
        </button>

        {/* Expanded details panel */}
        {expanded && (
          <div id={panelId} className="mt-3">
            {/* Summary */}
            {finding.summary && (
              <p
                className={`text-sm mb-3 ${
                  isDark ? "text-gray-300" : "text-gray-700"
                }`}
              >
                {finding.summary}
              </p>
            )}

            {/* Recommended change callout */}
            {finding.recommended_change && (
              <div
                className={`mb-3 rounded-md border-l-4 px-3 py-2 ${
                  isDark
                    ? "bg-blue-900/20 border-blue-500 text-blue-100"
                    : "bg-blue-50 border-blue-400 text-blue-900"
                }`}
              >
                <div
                  className={`text-xs font-semibold mb-1 ${
                    isDark ? "text-blue-300" : "text-blue-700"
                  }`}
                >
                  Recommended change
                </div>
                <div className="text-sm whitespace-pre-wrap">
                  {finding.recommended_change}
                </div>
              </div>
            )}

            {/* Explanation (markdown, lazily fetched) */}
            <div className="mb-3">
              <div
                className={`text-xs font-semibold uppercase tracking-wide mb-1 ${
                  isDark ? "text-gray-400" : "text-gray-500"
                }`}
              >
                Explanation
              </div>
              {explanationLoading ? (
                <div
                  data-testid="advice-explanation-loading"
                  className={`flex items-center text-sm ${
                    isDark ? "text-gray-400" : "text-gray-500"
                  }`}
                >
                  <div
                    className={`w-3.5 h-3.5 mr-2 border-2 border-t-transparent rounded-full animate-spin ${
                      isDark ? "border-blue-400" : "border-blue-500"
                    }`}
                  />
                  Generating explanation…
                </div>
              ) : cachedExplanation ? (
                <div
                  className={`rounded-md px-3 py-2 ${
                    isDark ? "bg-gray-900/40" : "bg-gray-50"
                  }`}
                >
                  <SolutionMarkdown
                    content={cachedExplanation}
                    isDark={isDark}
                  />
                </div>
              ) : (
                <p
                  className={`text-sm italic ${
                    isDark ? "text-gray-500" : "text-gray-500"
                  }`}
                >
                  No explanation generated for this finding.
                </p>
              )}
            </div>

            {/* Evidence (collapsible) */}
            <div className="mb-3">
              <button
                type="button"
                onClick={() => setEvidenceOpen((v) => !v)}
                className={`inline-flex items-center text-xs font-medium ${
                  isDark
                    ? "text-gray-300 hover:text-gray-100"
                    : "text-gray-600 hover:text-gray-900"
                }`}
              >
                {evidenceOpen ? (
                  <ChevronDown className="w-4 h-4 mr-1" />
                ) : (
                  <ChevronRight className="w-4 h-4 mr-1" />
                )}
                {evidenceOpen ? "Hide evidence" : "Show evidence"}
              </button>
              {evidenceOpen && (
                <pre
                  data-testid="advice-evidence"
                  className={`mt-2 text-xs rounded p-3 overflow-x-auto whitespace-pre-wrap break-words ${
                    isDark
                      ? "bg-gray-900 text-gray-300 border border-gray-700"
                      : "bg-gray-50 text-gray-800 border border-gray-200"
                  }`}
                >
                  {JSON.stringify(finding.evidence || {}, null, 2)}
                </pre>
              )}
            </div>

            {/* Footer: actions */}
            {canWrite && (onDismiss || onRestore) && (
              <div className="flex justify-end pt-2 border-t border-dashed border-gray-300 dark:border-gray-700">
                {!dismissed && onDismiss && (
                  <button
                    type="button"
                    onClick={handleDismiss}
                    disabled={busy}
                    className={`inline-flex items-center px-3 py-1.5 text-xs font-medium rounded-md border transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                      isDark
                        ? "border-gray-600 bg-gray-700 hover:bg-gray-600 text-gray-200"
                        : "border-gray-300 bg-white hover:bg-gray-50 text-gray-700"
                    }`}
                  >
                    <Trash2 className="w-3.5 h-3.5 mr-1" />
                    Dismiss
                  </button>
                )}
                {dismissed && onRestore && (
                  <button
                    type="button"
                    onClick={handleRestore}
                    disabled={busy}
                    className={`inline-flex items-center px-3 py-1.5 text-xs font-medium rounded-md border transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                      isDark
                        ? "border-gray-600 bg-gray-700 hover:bg-gray-600 text-gray-200"
                        : "border-gray-300 bg-white hover:bg-gray-50 text-gray-700"
                    }`}
                  >
                    <RotateCcw className="w-3.5 h-3.5 mr-1" />
                    Restore
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default AdviceFindingCard;

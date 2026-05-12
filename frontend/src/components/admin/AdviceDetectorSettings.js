import React, { useEffect, useState } from 'react';
import { Lightbulb, AlertTriangle } from 'lucide-react';
import { api } from '../../services/api';
import { useCanWrite } from '../../contexts/AuthContext';

/**
 * AdviceDetectorSettings — admin panel section to enable/disable AI Advice
 * detectors and surface Hubble (Layer-2) availability.
 *
 * Renders the seven shipped detectors sorted by id; toggling a row optimistically
 * updates state and rolls back on failure. Layer-2 detectors are annotated
 * with a "Requires Hubble" badge; when Hubble is unavailable they're additionally
 * flagged as "skipped — needs Hubble" but the toggle remains interactive so
 * operators can pre-enable.
 */
const severityClasses = (severity, isDark) => {
  switch ((severity || '').toLowerCase()) {
    case 'high':
      return isDark
        ? 'bg-red-900/50 text-red-300 border border-red-700'
        : 'bg-red-100 text-red-800 border border-red-300';
    case 'medium':
      return isDark
        ? 'bg-yellow-900/50 text-yellow-300 border border-yellow-700'
        : 'bg-amber-100 text-amber-800 border border-amber-300';
    case 'low':
      return isDark
        ? 'bg-blue-900/50 text-blue-300 border border-blue-700'
        : 'bg-blue-100 text-blue-800 border border-blue-300';
    case 'info':
    default:
      return isDark
        ? 'bg-gray-700 text-gray-300 border border-gray-600'
        : 'bg-gray-100 text-gray-700 border border-gray-300';
  }
};

const AdviceDetectorSettings = ({ isDark = false, onError, onSuccess }) => {
  const canWrite = useCanWrite();

  const [detectors, setDetectors] = useState([]);
  const [hubbleStatus, setHubbleStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [rowErrors, setRowErrors] = useState({}); // {detectorId: errorString}
  const [pending, setPending] = useState({}); // {detectorId: boolean}

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setLoading(true);
        const data = await api.getAdviceDetectors();
        if (cancelled) return;
        const sorted = (data?.detectors || []).slice().sort((a, b) => {
          const ai = (a.id || '').toLowerCase();
          const bi = (b.id || '').toLowerCase();
          return ai < bi ? -1 : ai > bi ? 1 : 0;
        });
        setDetectors(sorted);
        setHubbleStatus(data?.hubble_status || null);
        setLoadError(null);
      } catch (err) {
        if (cancelled) return;
        const msg = 'Failed to load advice detectors';
        setLoadError(msg);
        if (onError) onError(msg);
        console.error('Error loading advice detectors:', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [onError]);

  const hubbleAvailable = !!hubbleStatus?.available;

  const handleToggle = async (detector) => {
    if (!canWrite || pending[detector.id]) return;
    const newEnabled = !detector.enabled;

    // Optimistic update.
    setDetectors((prev) =>
      prev.map((d) => (d.id === detector.id ? { ...d, enabled: newEnabled } : d)),
    );
    setRowErrors((prev) => {
      const next = { ...prev };
      delete next[detector.id];
      return next;
    });
    setPending((prev) => ({ ...prev, [detector.id]: true }));

    try {
      await api.setAdviceDetectorEnabled(detector.id, newEnabled);
      if (onSuccess) {
        onSuccess(
          `Detector "${detector.id}" ${newEnabled ? 'enabled' : 'disabled'}.`,
        );
      }
    } catch (err) {
      // Roll back.
      setDetectors((prev) =>
        prev.map((d) =>
          d.id === detector.id ? { ...d, enabled: detector.enabled } : d,
        ),
      );
      setRowErrors((prev) => ({
        ...prev,
        [detector.id]: err?.message || 'Failed to update detector',
      }));
      console.error('Error toggling detector:', err);
    } finally {
      setPending((prev) => {
        const next = { ...prev };
        delete next[detector.id];
        return next;
      });
    }
  };

  return (
    <div>
      <div className="mb-4 flex items-center">
        <Lightbulb
          className={`w-5 h-5 mr-2 ${isDark ? 'text-yellow-400' : 'text-yellow-500'}`}
        />
        <h2
          className={`text-lg font-semibold ${
            isDark ? 'text-gray-100' : 'text-gray-900'
          }`}
        >
          AI Advice — Detector Settings
        </h2>
      </div>
      <p
        className={`text-sm mb-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}
      >
        Enable or disable individual AI Advice detectors. Disabled detectors are
        skipped during scans.
      </p>

      {/* Hubble status card */}
      <div
        className={`mb-4 p-3 border rounded-md flex items-start ${
          isDark
            ? 'bg-gray-800/50 border-gray-700'
            : 'bg-gray-50 border-gray-200'
        }`}
      >
        <span
          aria-hidden="true"
          className={`inline-block w-2.5 h-2.5 rounded-full mt-1.5 mr-3 ${
            hubbleAvailable ? 'bg-green-500' : 'bg-amber-500'
          }`}
        />
        <div className="flex-1">
          <div
            className={`text-sm font-medium ${
              isDark ? 'text-gray-200' : 'text-gray-800'
            }`}
          >
            {hubbleAvailable
              ? `Hubble: connected — ${hubbleStatus?.flow_count ?? 0} recent flows`
              : 'Hubble: not configured'}
          </div>
          {hubbleStatus?.reason && (
            <div
              className={`text-xs mt-1 ${
                isDark ? 'text-gray-400' : 'text-gray-500'
              }`}
            >
              {hubbleStatus.reason}
            </div>
          )}
        </div>
      </div>

      {/* Load error */}
      {loadError && (
        <div
          className={`mb-4 p-3 border rounded-md flex items-center ${
            isDark
              ? 'bg-red-900/30 border-red-700 text-red-200'
              : 'bg-red-50 border-red-200 text-red-800'
          }`}
        >
          <AlertTriangle className="w-4 h-4 mr-2" />
          <span className="text-sm">{loadError}</span>
        </div>
      )}

      {/* Detector list */}
      {loading ? (
        <div
          className={`py-6 text-center text-sm ${
            isDark ? 'text-gray-400' : 'text-gray-500'
          }`}
        >
          Loading detectors…
        </div>
      ) : detectors.length === 0 && !loadError ? (
        <div
          className={`py-6 text-center text-sm ${
            isDark ? 'text-gray-400' : 'text-gray-500'
          }`}
        >
          No detectors available.
        </div>
      ) : (
        <ul
          data-testid="advice-detector-list"
          className={`divide-y border rounded-md ${
            isDark
              ? 'divide-gray-700 border-gray-700'
              : 'divide-gray-200 border-gray-200'
          }`}
        >
          {detectors.map((d) => {
            const rowError = rowErrors[d.id];
            const requiresHubble = !!d.requires_hubble;
            const skippedNeedsHubble = requiresHubble && !hubbleAvailable;
            return (
              <li
                key={d.id}
                className={`px-4 py-3 ${
                  isDark ? 'hover:bg-gray-800/40' : 'hover:bg-gray-50'
                }`}
              >
                <div className="flex items-start gap-3">
                  {/* Toggle (iOS-style via Tailwind, no new dep). */}
                  <label
                    className={`relative inline-flex items-center cursor-pointer mt-0.5 ${
                      !canWrite ? 'cursor-not-allowed opacity-60' : ''
                    }`}
                    title={
                      canWrite
                        ? d.enabled
                          ? 'Click to disable'
                          : 'Click to enable'
                        : 'You do not have permission'
                    }
                  >
                    <input
                      type="checkbox"
                      className="sr-only peer"
                      checked={!!d.enabled}
                      disabled={!canWrite || !!pending[d.id]}
                      onChange={() => handleToggle(d)}
                      aria-label={`Toggle detector ${d.id}`}
                    />
                    <div
                      className={`w-9 h-5 rounded-full transition-colors peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-offset-1 peer-focus:ring-purple-500 ${
                        d.enabled
                          ? isDark
                            ? 'bg-purple-600'
                            : 'bg-purple-600'
                          : isDark
                            ? 'bg-gray-600'
                            : 'bg-gray-300'
                      } after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-transform ${
                        d.enabled ? 'after:translate-x-4' : ''
                      }`}
                    />
                  </label>

                  <div className="flex-1 min-w-0">
                    {/* Top line: id, chips */}
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`font-mono text-sm ${
                          isDark ? 'text-gray-100' : 'text-gray-900'
                        }`}
                      >
                        {d.id}
                      </span>
                      {d.category && (
                        <span
                          className={`inline-block px-2 py-0.5 rounded-full text-xs ${
                            isDark
                              ? 'bg-gray-700 text-gray-300 border border-gray-600'
                              : 'bg-gray-100 text-gray-700 border border-gray-200'
                          }`}
                        >
                          {d.category}
                        </span>
                      )}
                      <span
                        className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${severityClasses(
                          d.default_severity,
                          isDark,
                        )}`}
                      >
                        {(d.default_severity || 'info').toUpperCase()}
                      </span>
                      {requiresHubble && (
                        <span
                          className={`inline-block px-2 py-0.5 rounded-full text-xs ${
                            isDark
                              ? 'bg-indigo-900/40 text-indigo-300 border border-indigo-700'
                              : 'bg-indigo-100 text-indigo-800 border border-indigo-200'
                          }`}
                          title="Requires Cilium Hubble to be configured"
                        >
                          Requires Hubble
                        </span>
                      )}
                    </div>

                    {/* Description */}
                    {d.description && (
                      <p
                        className={`mt-1 text-sm truncate ${
                          isDark ? 'text-gray-400' : 'text-gray-600'
                        }`}
                        title={d.description}
                      >
                        {d.description}
                      </p>
                    )}

                    {/* Skipped annotation */}
                    {skippedNeedsHubble && (
                      <p
                        className={`mt-1 text-xs italic ${
                          isDark ? 'text-gray-500' : 'text-gray-500'
                        }`}
                      >
                        skipped — needs Hubble
                      </p>
                    )}

                    {/* Row error */}
                    {rowError && (
                      <p
                        className={`mt-1 text-xs ${
                          isDark ? 'text-red-300' : 'text-red-700'
                        }`}
                      >
                        {rowError}
                      </p>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

export default AdviceDetectorSettings;

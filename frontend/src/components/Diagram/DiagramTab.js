import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { AlertTriangle, Network, RefreshCw } from 'lucide-react';
import TopologyGraph from './TopologyGraph';
import { api } from '../../services/api';

const WORKLOAD_KINDS = ['Deployment', 'StatefulSet', 'DaemonSet', 'Job', 'CronJob'];

const DiagramTab = ({ isDark = false }) => {
  const [mode, setMode] = useState('namespace');
  const [namespaces, setNamespaces] = useState([]);
  const [namespace, setNamespace] = useState('');
  const [kind, setKind] = useState('Deployment');
  const [workloadName, setWorkloadName] = useState('');
  const [diagram, setDiagram] = useState(null);
  const [loading, setLoading] = useState(false);
  const [nsLoading, setNsLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setNsLoading(true);
        const res = await api.getDiagramNamespaces();
        if (cancelled) return;
        const list = res?.namespaces || [];
        setNamespaces(list);
        if (list.length > 0) {
          setNamespace((prev) => prev || list[0]);
        }
      } catch (err) {
        if (!cancelled) setError(`Failed to load namespaces: ${err.message || 'unknown error'}`);
      } finally {
        if (!cancelled) setNsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const fetchDiagram = useCallback(async () => {
    if (!namespace) {
      setDiagram(null);
      return;
    }
    if (mode === 'workload' && !workloadName.trim()) {
      setDiagram(null);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const res =
        mode === 'namespace'
          ? await api.getDiagramNamespace(namespace)
          : await api.getDiagramWorkload(namespace, kind, workloadName.trim());
      setDiagram(res);
    } catch (err) {
      setError(`Failed to load diagram: ${err.message || 'unknown error'}`);
      setDiagram(null);
    } finally {
      setLoading(false);
    }
  }, [mode, namespace, kind, workloadName]);

  useEffect(() => {
    if (mode === 'namespace') {
      fetchDiagram();
    } else {
      // In workload mode we don't auto-fetch on every keystroke; user clicks Render.
      setDiagram(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, namespace]);

  const counts = useMemo(() => {
    if (!diagram) return null;
    return {
      nodes: (diagram.nodes || []).length,
      edges: (diagram.edges || []).length,
      groups: (diagram.groups || []).length,
    };
  }, [diagram]);

  const inputBase = isDark
    ? 'bg-gray-800 border-gray-600 text-gray-200 placeholder-gray-500'
    : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400';

  const tabBtnBase = 'px-3 py-1.5 text-sm font-medium rounded-md border transition-colors';
  const tabBtnActive = isDark
    ? 'bg-blue-900/40 border-blue-700 text-blue-200'
    : 'bg-blue-50 border-blue-300 text-blue-700';
  const tabBtnIdle = isDark
    ? 'bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700'
    : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50';

  return (
    <div className="p-4">
      {/* Controls */}
      <div className={`mb-4 rounded-lg border p-4 ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
        <div className="flex flex-wrap items-end gap-3">
          {/* Mode switch */}
          <div className="flex items-center space-x-2" role="tablist" aria-label="Diagram mode">
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'namespace'}
              onClick={() => setMode('namespace')}
              className={`${tabBtnBase} ${mode === 'namespace' ? tabBtnActive : tabBtnIdle}`}
            >
              Namespace
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'workload'}
              onClick={() => setMode('workload')}
              className={`${tabBtnBase} ${mode === 'workload' ? tabBtnActive : tabBtnIdle}`}
            >
              Workload
            </button>
          </div>

          {/* Namespace dropdown */}
          <div className="flex flex-col">
            <label htmlFor="diagram-namespace" className={`text-xs font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              Namespace
            </label>
            <select
              id="diagram-namespace"
              value={namespace}
              onChange={(e) => setNamespace(e.target.value)}
              disabled={nsLoading}
              className={`px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${inputBase}`}
            >
              {namespaces.length === 0 && (
                <option value="">{nsLoading ? 'Loading…' : 'No namespaces'}</option>
              )}
              {namespaces.map((ns) => (
                <option key={ns} value={ns}>
                  {ns}
                </option>
              ))}
            </select>
          </div>

          {/* Workload-specific controls */}
          {mode === 'workload' && (
            <>
              <div className="flex flex-col">
                <label htmlFor="diagram-kind" className={`text-xs font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  Kind
                </label>
                <select
                  id="diagram-kind"
                  value={kind}
                  onChange={(e) => setKind(e.target.value)}
                  className={`px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${inputBase}`}
                >
                  {WORKLOAD_KINDS.map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col">
                <label htmlFor="diagram-name" className={`text-xs font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  Name
                </label>
                <input
                  id="diagram-name"
                  type="text"
                  value={workloadName}
                  onChange={(e) => setWorkloadName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') fetchDiagram();
                  }}
                  placeholder="workload name"
                  className={`w-56 px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${inputBase}`}
                />
              </div>
              <button
                type="button"
                onClick={fetchDiagram}
                disabled={!namespace || !workloadName.trim() || loading}
                className={`px-4 py-2 text-sm font-medium rounded-md border focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed ${
                  isDark
                    ? 'bg-blue-900/40 border-blue-700 text-blue-200 hover:bg-blue-800/50'
                    : 'bg-blue-50 border-blue-300 text-blue-700 hover:bg-blue-100'
                }`}
              >
                Render
              </button>
            </>
          )}

          {/* Refresh button (namespace mode) */}
          {mode === 'namespace' && (
            <button
              type="button"
              onClick={fetchDiagram}
              disabled={!namespace || loading}
              title="Refresh diagram"
              className={`flex items-center px-3 py-2 text-sm font-medium rounded-md border focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed ${
                isDark
                  ? 'bg-gray-800 border-gray-700 text-gray-200 hover:bg-gray-700'
                  : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
              }`}
            >
              <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          )}

          {/* Counts */}
          {counts && (
            <div className={`ml-auto text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              {counts.nodes} nodes · {counts.edges} edges · {counts.groups} groups
            </div>
          )}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className={`mb-4 flex items-start rounded-md border px-4 py-3 ${isDark ? 'bg-red-900/30 border-red-700 text-red-200' : 'bg-red-50 border-red-200 text-red-800'}`}>
          <AlertTriangle className="w-4 h-4 mt-0.5 mr-2 flex-shrink-0" />
          <span className="text-sm">{error}</span>
        </div>
      )}

      {/* Graph viewport */}
      <div
        className={`relative rounded-lg border overflow-hidden ${
          isDark ? 'bg-gray-900 border-gray-700' : 'bg-white border-gray-200'
        }`}
        style={{ height: '70vh', minHeight: 500 }}
      >
        {loading && (
          <div className={`absolute inset-0 z-10 flex items-center justify-center ${isDark ? 'bg-gray-900/70' : 'bg-white/70'}`}>
            <div className="flex items-center space-x-2">
              <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              <span className={`text-sm ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>Loading diagram…</span>
            </div>
          </div>
        )}

        {!diagram && !loading ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-6">
            <Network className={`w-10 h-10 mb-3 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
            <h3 className={`text-base font-medium ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>
              {mode === 'workload' && (!workloadName.trim())
                ? 'Enter a workload name to render its topology'
                : 'No diagram'}
            </h3>
            <p className={`text-sm mt-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              {mode === 'namespace'
                ? 'Select a namespace to render its resource topology.'
                : 'Pick a kind and enter a workload name, then click Render.'}
            </p>
          </div>
        ) : (
          diagram && <TopologyGraph data={diagram} isDark={isDark} />
        )}
      </div>
    </div>
  );
};

export default DiagramTab;

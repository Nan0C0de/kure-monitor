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
  const [workloadNames, setWorkloadNames] = useState([]);
  const [workloadsLoading, setWorkloadsLoading] = useState(false);
  const [diagram, setDiagram] = useState(null);
  const [loading, setLoading] = useState(false);
  const [nsLoading, setNsLoading] = useState(false);
  const [error, setError] = useState('');

  // Roles mode state
  const [roleScope, setRoleScope] = useState('namespace'); // 'namespace' | 'cluster'
  const [rolesData, setRolesData] = useState({ cluster_roles: [], roles: [] });
  const [rolesLoading, setRolesLoading] = useState(false);
  const [roleNamespace, setRoleNamespace] = useState('');
  const [roleName, setRoleName] = useState('');
  const [clusterRoleName, setClusterRoleName] = useState('');

  useEffect(() => {
    let cancelled = false;
    const filterKind = mode === 'workload' ? kind : undefined;
    (async () => {
      try {
        setNsLoading(true);
        const res = await api.getDiagramNamespaces(filterKind);
        if (cancelled) return;
        const list = res?.namespaces || [];
        setNamespaces(list);
        setNamespace((prev) => (list.includes(prev) ? prev : list[0] || ''));
      } catch (err) {
        if (!cancelled) setError(`Failed to load namespaces: ${err.message || 'unknown error'}`);
      } finally {
        if (!cancelled) setNsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mode, kind]);

  // Load workload names when in workload mode and ns/kind change.
  useEffect(() => {
    if (mode !== 'workload' || !namespace) {
      setWorkloadNames([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        setWorkloadsLoading(true);
        const res = await api.getDiagramWorkloads(namespace, kind);
        if (cancelled) return;
        const list = res?.workloads || [];
        setWorkloadNames(list);
        setWorkloadName((prev) => (list.includes(prev) ? prev : list[0] || ''));
      } catch (err) {
        if (!cancelled) {
          setWorkloadNames([]);
          setWorkloadName('');
          setError(`Failed to load workloads: ${err.message || 'unknown error'}`);
        }
      } finally {
        if (!cancelled) setWorkloadsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mode, namespace, kind]);

  // Lazy-load the roles list the first time the user enters Roles mode.
  // Tracked via a ref so we don't restart the in-flight request when our own
  // setState calls trigger re-renders.
  const rolesLoadedRef = React.useRef(false);
  useEffect(() => {
    if (mode !== 'roles') return;
    if (rolesLoadedRef.current) return;
    rolesLoadedRef.current = true;

    let cancelled = false;
    (async () => {
      try {
        setRolesLoading(true);
        const res = await api.getDiagramRoles();
        if (cancelled) return;
        const next = {
          cluster_roles: res?.cluster_roles || [],
          roles: res?.roles || [],
        };
        setRolesData(next);
        // Default selections so the user sees something immediately.
        if (next.cluster_roles.length > 0) {
          setClusterRoleName((prev) => prev || next.cluster_roles[0].name);
        }
        if (next.roles.length > 0) {
          setRoleNamespace((prev) => prev || next.roles[0].namespace);
          setRoleName((prev) => prev || next.roles[0].name);
        }
      } catch (err) {
        if (!cancelled) {
          setError(`Failed to load roles: ${err.message || 'unknown error'}`);
          // Allow a retry after failure.
          rolesLoadedRef.current = false;
        }
      } finally {
        if (!cancelled) setRolesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mode]);

  // Namespaces that contain at least one Role.
  const roleNamespaces = useMemo(() => {
    const set = new Set();
    (rolesData.roles || []).forEach((r) => set.add(r.namespace));
    return Array.from(set).sort();
  }, [rolesData]);

  // Roles in the currently-selected namespace.
  const rolesInNamespace = useMemo(() => {
    return (rolesData.roles || [])
      .filter((r) => r.namespace === roleNamespace)
      .map((r) => r.name)
      .sort();
  }, [rolesData, roleNamespace]);

  // Keep the role selection consistent with the chosen namespace.
  useEffect(() => {
    if (mode !== 'roles' || roleScope !== 'namespace') return;
    if (rolesInNamespace.length === 0) {
      if (roleName !== '') setRoleName('');
      return;
    }
    if (!rolesInNamespace.includes(roleName)) {
      setRoleName(rolesInNamespace[0]);
    }
  }, [mode, roleScope, rolesInNamespace, roleName]);

  const fetchDiagram = useCallback(async () => {
    if (mode === 'roles') {
      setLoading(true);
      setError('');
      try {
        let res;
        if (roleScope === 'cluster') {
          if (!clusterRoleName) {
            setDiagram(null);
            return;
          }
          res = await api.getDiagramClusterRole(clusterRoleName);
        } else {
          if (!roleNamespace || !roleName) {
            setDiagram(null);
            return;
          }
          res = await api.getDiagramRole(roleNamespace, roleName);
        }
        setDiagram(res);
      } catch (err) {
        setError(`Failed to load diagram: ${err.message || 'unknown error'}`);
        setDiagram(null);
      } finally {
        setLoading(false);
      }
      return;
    }

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
  }, [mode, namespace, kind, workloadName, roleScope, roleNamespace, roleName, clusterRoleName]);

  useEffect(() => {
    if (mode === 'namespace') {
      fetchDiagram();
    } else if (mode === 'roles') {
      // Auto-fetch when the role selection is complete.
      if (
        (roleScope === 'cluster' && clusterRoleName) ||
        (roleScope === 'namespace' &&
          roleNamespace &&
          roleName &&
          rolesInNamespace.includes(roleName))
      ) {
        fetchDiagram();
      } else {
        setDiagram(null);
      }
    } else if (mode === 'workload') {
      // Auto-fetch when the workload selection is complete and consistent.
      if (namespace && workloadName && workloadNames.includes(workloadName)) {
        fetchDiagram();
      } else {
        setDiagram(null);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    mode,
    namespace,
    kind,
    workloadName,
    workloadNames,
    roleScope,
    roleNamespace,
    roleName,
    clusterRoleName,
    rolesInNamespace,
  ]);

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

  const labelClass = `text-xs font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`;
  const selectClass = `px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${inputBase}`;

  const renderEmptyState = () => {
    let title = 'No diagram';
    let body = 'Select a namespace to render its resource topology.';
    if (mode === 'workload') {
      title = !workloadName.trim() ? 'Enter a workload name to render its topology' : 'No diagram';
      body = 'Pick a kind and enter a workload name, then click Render.';
    } else if (mode === 'roles') {
      if (rolesLoading) {
        title = 'Loading roles…';
        body = 'Fetching the cluster\'s roles and cluster roles.';
      } else if (
        (roleScope === 'cluster' && (rolesData.cluster_roles || []).length === 0) ||
        (roleScope === 'namespace' && (rolesData.roles || []).length === 0)
      ) {
        title = 'No roles found';
        body =
          roleScope === 'cluster'
            ? 'No ClusterRoles are visible to kure-monitor.'
            : 'No namespaced Roles are visible to kure-monitor.';
      } else {
        title = 'Select a role';
        body =
          roleScope === 'cluster'
            ? 'Pick a ClusterRole to render its RBAC graph.'
            : 'Pick a namespace and Role to render its RBAC graph.';
      }
    }
    return (
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-6">
        <Network className={`w-10 h-10 mb-3 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
        <h3 className={`text-base font-medium ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>
          {title}
        </h3>
        <p className={`text-sm mt-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{body}</p>
      </div>
    );
  };

  return (
    <div className="p-4">
      {/* Controls */}
      <div
        className={`mb-4 rounded-lg border p-4 ${
          isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'
        }`}
      >
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
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'roles'}
              onClick={() => setMode('roles')}
              className={`${tabBtnBase} ${mode === 'roles' ? tabBtnActive : tabBtnIdle}`}
            >
              Roles
            </button>
          </div>

          {/* Namespace dropdown (namespace + workload modes) */}
          {(mode === 'namespace' || mode === 'workload') && (
            <div className="flex flex-col">
              <label htmlFor="diagram-namespace" className={labelClass}>
                Namespace
              </label>
              <select
                id="diagram-namespace"
                value={namespace}
                onChange={(e) => setNamespace(e.target.value)}
                disabled={nsLoading}
                className={selectClass}
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
          )}

          {/* Workload-specific controls */}
          {mode === 'workload' && (
            <>
              <div className="flex flex-col">
                <label htmlFor="diagram-kind" className={labelClass}>
                  Kind
                </label>
                <select
                  id="diagram-kind"
                  value={kind}
                  onChange={(e) => setKind(e.target.value)}
                  className={selectClass}
                >
                  {WORKLOAD_KINDS.map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col">
                <label htmlFor="diagram-name" className={labelClass}>
                  Name
                </label>
                <select
                  id="diagram-name"
                  value={workloadName}
                  onChange={(e) => setWorkloadName(e.target.value)}
                  disabled={workloadsLoading || workloadNames.length === 0}
                  className={selectClass}
                >
                  {workloadNames.length === 0 && (
                    <option value="">
                      {workloadsLoading ? 'Loading…' : `No ${kind}s in namespace`}
                    </option>
                  )}
                  {workloadNames.map((wn) => (
                    <option key={wn} value={wn}>
                      {wn}
                    </option>
                  ))}
                </select>
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

          {/* Roles-specific controls */}
          {mode === 'roles' && (
            <>
              <div
                className="flex items-center space-x-2"
                role="tablist"
                aria-label="Role scope"
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={roleScope === 'namespace'}
                  onClick={() => setRoleScope('namespace')}
                  className={`${tabBtnBase} ${
                    roleScope === 'namespace' ? tabBtnActive : tabBtnIdle
                  }`}
                >
                  Namespace Roles
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={roleScope === 'cluster'}
                  onClick={() => setRoleScope('cluster')}
                  className={`${tabBtnBase} ${
                    roleScope === 'cluster' ? tabBtnActive : tabBtnIdle
                  }`}
                >
                  ClusterRoles
                </button>
              </div>

              {roleScope === 'namespace' ? (
                <>
                  <div className="flex flex-col">
                    <label htmlFor="diagram-role-namespace" className={labelClass}>
                      Namespace
                    </label>
                    <select
                      id="diagram-role-namespace"
                      value={roleNamespace}
                      onChange={(e) => setRoleNamespace(e.target.value)}
                      disabled={rolesLoading || roleNamespaces.length === 0}
                      className={selectClass}
                    >
                      {roleNamespaces.length === 0 && (
                        <option value="">
                          {rolesLoading ? 'Loading…' : 'No namespaces with roles'}
                        </option>
                      )}
                      {roleNamespaces.map((ns) => (
                        <option key={ns} value={ns}>
                          {ns}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="flex flex-col">
                    <label htmlFor="diagram-role-name" className={labelClass}>
                      Role
                    </label>
                    <select
                      id="diagram-role-name"
                      value={roleName}
                      onChange={(e) => setRoleName(e.target.value)}
                      disabled={rolesLoading || rolesInNamespace.length === 0}
                      className={selectClass}
                    >
                      {rolesInNamespace.length === 0 && (
                        <option value="">
                          {rolesLoading ? 'Loading…' : 'No roles in namespace'}
                        </option>
                      )}
                      {rolesInNamespace.map((rn) => (
                        <option key={rn} value={rn}>
                          {rn}
                        </option>
                      ))}
                    </select>
                  </div>
                </>
              ) : (
                <div className="flex flex-col">
                  <label htmlFor="diagram-clusterrole-name" className={labelClass}>
                    ClusterRole
                  </label>
                  <select
                    id="diagram-clusterrole-name"
                    value={clusterRoleName}
                    onChange={(e) => setClusterRoleName(e.target.value)}
                    disabled={rolesLoading || (rolesData.cluster_roles || []).length === 0}
                    className={selectClass}
                  >
                    {(rolesData.cluster_roles || []).length === 0 && (
                      <option value="">
                        {rolesLoading ? 'Loading…' : 'No cluster roles'}
                      </option>
                    )}
                    {(rolesData.cluster_roles || []).map((cr) => (
                      <option key={cr.name} value={cr.name}>
                        {cr.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </>
          )}

          {/* Refresh button (auto-fetch modes) */}
          {(mode === 'namespace' || mode === 'roles') && (
            <button
              type="button"
              onClick={fetchDiagram}
              disabled={
                loading ||
                (mode === 'namespace' && !namespace) ||
                (mode === 'roles' &&
                  ((roleScope === 'cluster' && !clusterRoleName) ||
                    (roleScope === 'namespace' && (!roleNamespace || !roleName))))
              }
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
        <div
          className={`mb-4 flex items-start rounded-md border px-4 py-3 ${
            isDark ? 'bg-red-900/30 border-red-700 text-red-200' : 'bg-red-50 border-red-200 text-red-800'
          }`}
        >
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
          <div
            className={`absolute inset-0 z-10 flex items-center justify-center ${
              isDark ? 'bg-gray-900/70' : 'bg-white/70'
            }`}
          >
            <div className="flex items-center space-x-2">
              <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded animate-spin" />
              <span className={`text-sm ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
                Loading diagram…
              </span>
            </div>
          </div>
        )}

        {!diagram && !loading
          ? renderEmptyState()
          : diagram && <TopologyGraph data={diagram} isDark={isDark} />}
      </div>
    </div>
  );
};

export default DiagramTab;

import React, { useEffect, useState } from "react";
import { RotateCcw } from "lucide-react";
import { api } from "../services/api";

/**
 * Cascading scope picker: namespace -> workload kind -> workload name.
 *
 * NOTE: The diagram API exposes namespaces (`getDiagramNamespaces`) and
 * workloads filtered by namespace + kind (`getDiagramWorkloads`), but there
 * is currently no endpoint that lists pods filtered by their owning workload.
 * The backend `POST /api/advice/scan` accepts `pod_name` (with workload_kind
 * and workload_name), but until a "pods by workload" endpoint exists we
 * limit the UI to namespace + workload scoping. Pod scoping intentionally
 * skipped in v1 — see PROCESS notes in the spec.
 */
const WORKLOAD_KINDS = ["Deployment", "StatefulSet", "DaemonSet"];

const AdviceScopePicker = ({
  scope,
  onChange,
  isDark = false,
  disabled = false,
}) => {
  const [namespaces, setNamespaces] = useState([]);
  const [namespacesLoading, setNamespacesLoading] = useState(false);
  const [workloads, setWorkloads] = useState([]);
  const [workloadsLoading, setWorkloadsLoading] = useState(false);

  // Load namespaces once.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setNamespacesLoading(true);
        const res = await api.getDiagramNamespaces();
        if (cancelled) return;
        setNamespaces(res?.namespaces || []);
      } catch (err) {
        if (!cancelled) {
          console.error("Failed to load namespaces:", err);
          setNamespaces([]);
        }
      } finally {
        if (!cancelled) setNamespacesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Load workloads when namespace + kind are both set.
  useEffect(() => {
    if (!scope.namespace || !scope.workload_kind) {
      setWorkloads([]);
      return undefined;
    }
    let cancelled = false;
    (async () => {
      try {
        setWorkloadsLoading(true);
        const res = await api.getDiagramWorkloads(
          scope.namespace,
          scope.workload_kind,
        );
        if (cancelled) return;
        setWorkloads(res?.workloads || []);
      } catch (err) {
        if (!cancelled) {
          console.error("Failed to load workloads:", err);
          setWorkloads([]);
        }
      } finally {
        if (!cancelled) setWorkloadsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [scope.namespace, scope.workload_kind]);

  const handleNamespaceChange = (e) => {
    const value = e.target.value || undefined;
    // Narrowing namespace resets workload selection.
    onChange({
      namespace: value,
      workload_kind: undefined,
      workload_name: undefined,
      pod_name: undefined,
    });
  };

  const handleKindChange = (e) => {
    const value = e.target.value || undefined;
    onChange({
      ...scope,
      workload_kind: value,
      workload_name: undefined,
      pod_name: undefined,
    });
  };

  const handleWorkloadChange = (e) => {
    const value = e.target.value || undefined;
    onChange({
      ...scope,
      workload_name: value,
      pod_name: undefined,
    });
  };

  const handleReset = () => {
    onChange({
      namespace: undefined,
      workload_kind: undefined,
      workload_name: undefined,
      pod_name: undefined,
    });
  };

  const selectClasses = `block w-full px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed ${
    isDark
      ? "bg-gray-800 border-gray-600 text-gray-200"
      : "bg-white border-gray-300 text-gray-900"
  }`;
  const labelClasses = `block text-xs font-medium mb-1 ${
    isDark ? "text-gray-300" : "text-gray-700"
  }`;

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
      <div>
        <label htmlFor="advice-scope-namespace" className={labelClasses}>
          Namespace
        </label>
        <select
          id="advice-scope-namespace"
          className={selectClasses}
          value={scope.namespace || ""}
          onChange={handleNamespaceChange}
          disabled={disabled || namespacesLoading}
        >
          <option value="">
            {namespacesLoading ? "Loading…" : "All namespaces"}
          </option>
          {namespaces.map((ns) => (
            <option key={ns} value={ns}>
              {ns}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="advice-scope-kind" className={labelClasses}>
          Workload kind
        </label>
        <select
          id="advice-scope-kind"
          className={selectClasses}
          value={scope.workload_kind || ""}
          onChange={handleKindChange}
          disabled={disabled || !scope.namespace}
        >
          <option value="">Any kind</option>
          {WORKLOAD_KINDS.map((kind) => (
            <option key={kind} value={kind}>
              {kind}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="advice-scope-workload" className={labelClasses}>
          Workload
        </label>
        <select
          id="advice-scope-workload"
          className={selectClasses}
          value={scope.workload_name || ""}
          onChange={handleWorkloadChange}
          disabled={disabled || !scope.workload_kind}
        >
          <option value="">
            {workloadsLoading
              ? "Loading…"
              : !scope.workload_kind
                ? "Select kind first"
                : workloads.length === 0
                  ? "No workloads"
                  : "All workloads"}
          </option>
          {workloads.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>

      <div>
        <button
          type="button"
          onClick={handleReset}
          disabled={disabled}
          className={`inline-flex items-center justify-center w-full px-3 py-2 text-sm font-medium rounded-md border transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
            isDark
              ? "border-gray-600 bg-gray-800 hover:bg-gray-700 text-gray-200"
              : "border-gray-300 bg-white hover:bg-gray-50 text-gray-700"
          }`}
          title="Reset scope to all namespaces"
        >
          <RotateCcw className="w-4 h-4 mr-1" />
          Reset
        </button>
      </div>
    </div>
  );
};

export default AdviceScopePicker;

import React, { useCallback, useMemo, useState, useEffect } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  Panel,
  ReactFlowProvider,
  useReactFlow,
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from '@dagrejs/dagre';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { nodeTypes } from './nodeTypes';
import ManifestModal from '../ManifestModal';
import RbacSummaryModal from './RbacSummaryModal';
import { api } from '../../services/api';

const SYNTHESIZED_KINDS = new Set(['Permission', 'Subject:User', 'Subject:Group']);

const NODE_WIDTH = 200;
const NODE_HEIGHT = 70;

const EDGE_STYLE = {
  owns: {
    stroke: '#475569',
    strokeWidth: 1.5,
    strokeDasharray: undefined,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#475569' },
    animated: false,
  },
  selects: {
    stroke: '#64748b',
    strokeWidth: 1.5,
    strokeDasharray: '6 4',
    markerEnd: { type: MarkerType.ArrowClosed, color: '#64748b' },
    animated: false,
  },
  routes: {
    stroke: '#2563eb',
    strokeWidth: 2,
    strokeDasharray: undefined,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#2563eb' },
    animated: false,
  },
  mounts: {
    stroke: '#6b7280',
    strokeWidth: 1.5,
    strokeDasharray: '2 3',
    markerEnd: { type: MarkerType.ArrowClosed, color: '#6b7280' },
    animated: false,
  },
  scales: {
    stroke: '#16a34a',
    strokeWidth: 2,
    strokeDasharray: undefined,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#16a34a' },
    animated: false,
  },
  policy: {
    stroke: '#ea580c',
    strokeWidth: 1.5,
    strokeDasharray: '6 4',
    markerEnd: { type: MarkerType.ArrowClosed, color: '#ea580c' },
    animated: false,
  },
  bound: {
    stroke: '#1d4ed8',
    strokeWidth: 1.75,
    strokeDasharray: undefined,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#1d4ed8' },
    animated: false,
  },
  refs: {
    stroke: '#d97706',
    strokeWidth: 1.75,
    strokeDasharray: '6 4',
    markerEnd: { type: MarkerType.ArrowClosed, color: '#d97706' },
    animated: false,
  },
  grants: {
    stroke: '#059669',
    strokeWidth: 1.75,
    strokeDasharray: undefined,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#059669' },
    animated: false,
  },
};

const layoutWithDagre = (rfNodes, rfEdges) => {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 40, ranksep: 60, marginx: 20, marginy: 20 });

  rfNodes.forEach((node) => {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });
  rfEdges.forEach((edge) => {
    g.setEdge(edge.source, edge.target);
  });

  dagre.layout(g);

  return rfNodes.map((node) => {
    const pos = g.node(node.id);
    if (!pos) return node;
    return {
      ...node,
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
    };
  });
};

const buildGraphElements = (response, isDark, collapsedGroups) => {
  if (!response) return { nodes: [], edges: [] };

  const groups = response.groups || [];
  const collapsedNodeIds = new Set();
  const groupByCollapsedId = new Map();

  groups.forEach((g) => {
    if (collapsedGroups.has(g.id)) {
      g.node_ids.forEach((nid) => collapsedNodeIds.add(nid));
      groupByCollapsedId.set(g.id, g);
    }
  });

  const visibleNodes = (response.nodes || []).filter((n) => !collapsedNodeIds.has(n.id));

  const rfNodes = visibleNodes.map((n) => ({
    id: n.id,
    type: 'resource',
    position: { x: 0, y: 0 },
    data: {
      kind: n.kind,
      name: n.name,
      namespace: n.namespace,
      status: n.status,
      metadata: n.metadata || {},
      isDark,
      raw: n,
    },
  }));

  groupByCollapsedId.forEach((g) => {
    rfNodes.push({
      id: `__collapsed__${g.id}`,
      type: 'collapsedGroup',
      position: { x: 0, y: 0 },
      data: {
        groupId: g.id,
        label: g.label,
        count: g.node_ids.length,
        isDark,
      },
    });
  });

  const remap = (id) => {
    if (!collapsedNodeIds.has(id)) return id;
    for (const [gid, g] of groupByCollapsedId) {
      if (g.node_ids.includes(id)) return `__collapsed__${gid}`;
    }
    return id;
  };

  const edgeSet = new Set();
  const rfEdges = [];
  (response.edges || []).forEach((e, idx) => {
    const src = remap(e.source);
    const tgt = remap(e.target);
    if (src === tgt) return;
    const style = EDGE_STYLE[e.type] || EDGE_STYLE.owns;
    const key = `${src}|${tgt}|${e.type}`;
    if (edgeSet.has(key)) return;
    edgeSet.add(key);
    rfEdges.push({
      id: `e-${idx}-${src}-${tgt}-${e.type}`,
      source: src,
      target: tgt,
      type: 'default',
      animated: style.animated,
      style: {
        stroke: style.stroke,
        strokeWidth: style.strokeWidth,
        strokeDasharray: style.strokeDasharray,
      },
      markerEnd: style.markerEnd,
      data: { edgeType: e.type },
    });
  });

  return { nodes: layoutWithDagre(rfNodes, rfEdges), edges: rfEdges };
};

const Legend = ({ isDark, groups, collapsedGroups, onToggleGroup }) => {
  const items = [
    { type: 'owns', label: 'owns', color: '#475569', dashed: false },
    { type: 'selects', label: 'selects', color: '#64748b', dashed: true },
    { type: 'routes', label: 'routes', color: '#2563eb', dashed: false },
    { type: 'mounts', label: 'mounts', color: '#6b7280', dotted: true },
    { type: 'scales', label: 'scales', color: '#16a34a', dashed: false },
    { type: 'policy', label: 'policy', color: '#ea580c', dashed: true },
    { type: 'bound', label: 'bound', color: '#1d4ed8', dashed: false },
    { type: 'refs', label: 'refs', color: '#d97706', dashed: true },
    { type: 'grants', label: 'grants', color: '#059669', dashed: false },
  ];
  return (
    <div
      className={`text-xs rounded-sm border shadow-sm px-3 py-2 ${
        isDark ? 'bg-gray-800 border-gray-700 text-gray-200' : 'bg-white border-gray-200 text-gray-700'
      }`}
    >
      <div className="font-semibold mb-1">Edge types</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        {items.map((it) => (
          <div key={it.type} className="flex items-center space-x-2">
            <svg width="28" height="8">
              <line
                x1="0"
                y1="4"
                x2="28"
                y2="4"
                stroke={it.color}
                strokeWidth="2"
                strokeDasharray={it.dotted ? '2 3' : it.dashed ? '6 4' : undefined}
              />
            </svg>
            <span>{it.label}</span>
          </div>
        ))}
      </div>
      {groups && groups.length > 0 && (
        <>
          <div className="font-semibold mt-2 mb-1">Groups</div>
          <div className="flex flex-col space-y-1 max-h-40 overflow-y-auto">
            {groups.map((g) => {
              const collapsed = collapsedGroups.has(g.id);
              const Icon = collapsed ? ChevronRight : ChevronDown;
              return (
                <button
                  key={g.id}
                  onClick={() => onToggleGroup(g.id)}
                  className={`flex items-center space-x-1 text-left hover:underline ${
                    isDark ? 'text-gray-300' : 'text-gray-600'
                  }`}
                  title={collapsed ? 'Expand group' : 'Collapse group'}
                >
                  <Icon className="w-3 h-3" />
                  <span className="truncate">
                    {g.label} ({g.node_ids.length})
                  </span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
};

const computeFocusedSet = (focusedEdgeId, nodes, edges) => {
  if (!focusedEdgeId) return { focusedNodeIds: null, focusedEdgeIds: null };
  const clicked = edges.find((e) => e.id === focusedEdgeId);
  if (!clicked) return { focusedNodeIds: null, focusedEdgeIds: null };

  const outgoing = new Map();
  const incoming = new Map();
  edges.forEach((e) => {
    if (!outgoing.has(e.source)) outgoing.set(e.source, []);
    outgoing.get(e.source).push(e);
    if (!incoming.has(e.target)) incoming.set(e.target, []);
    incoming.get(e.target).push(e);
  });

  const focusedNodeIds = new Set();
  const focusedEdgeIds = new Set([clicked.id]);

  // Forward BFS from clicked.target along outgoing edges (descendants).
  const fwdQueue = [clicked.target];
  focusedNodeIds.add(clicked.source);
  focusedNodeIds.add(clicked.target);
  while (fwdQueue.length) {
    const id = fwdQueue.shift();
    const outs = outgoing.get(id) || [];
    for (const e of outs) {
      if (focusedEdgeIds.has(e.id)) continue;
      focusedEdgeIds.add(e.id);
      if (!focusedNodeIds.has(e.target)) {
        focusedNodeIds.add(e.target);
        fwdQueue.push(e.target);
      }
    }
  }

  // Backward BFS from clicked.source along incoming edges (ancestors).
  const backQueue = [clicked.source];
  while (backQueue.length) {
    const id = backQueue.shift();
    const ins = incoming.get(id) || [];
    for (const e of ins) {
      if (focusedEdgeIds.has(e.id)) continue;
      focusedEdgeIds.add(e.id);
      if (!focusedNodeIds.has(e.source)) {
        focusedNodeIds.add(e.source);
        backQueue.push(e.source);
      }
    }
  }

  return { focusedNodeIds, focusedEdgeIds };
};

const Inner = ({ data, isDark }) => {
  const [collapsedGroups, setCollapsedGroups] = useState(new Set());
  const [focusedEdgeId, setFocusedEdgeId] = useState(null);
  const [modalState, setModalState] = useState({
    isOpen: false,
    namespace: '',
    kind: '',
    name: '',
    manifest: '',
    loading: false,
    infoMessage: '',
  });
  const [rbacModalState, setRbacModalState] = useState({
    isOpen: false,
    kind: '',
    name: '',
    namespace: '',
    metadata: null,
  });
  const { fitView } = useReactFlow();

  const { nodes: baseNodes, edges: baseEdges } = useMemo(
    () => buildGraphElements(data, isDark, collapsedGroups),
    [data, isDark, collapsedGroups]
  );

  // Clear focus if the focused edge no longer exists after data/collapse refresh.
  useEffect(() => {
    if (focusedEdgeId && !baseEdges.some((e) => e.id === focusedEdgeId)) {
      setFocusedEdgeId(null);
    }
  }, [baseEdges, focusedEdgeId]);

  const { focusedNodeIds, focusedEdgeIds } = useMemo(
    () => computeFocusedSet(focusedEdgeId, baseNodes, baseEdges),
    [focusedEdgeId, baseNodes, baseEdges]
  );

  const nodes = useMemo(() => {
    if (!focusedNodeIds) return baseNodes;
    return baseNodes.map((n) => {
      if (focusedNodeIds.has(n.id)) {
        return { ...n, style: { ...(n.style || {}), opacity: 1 }, zIndex: 1 };
      }
      return { ...n, style: { ...(n.style || {}), opacity: 0.15 }, zIndex: 0 };
    });
  }, [baseNodes, focusedNodeIds]);

  const edges = useMemo(() => {
    if (!focusedEdgeIds) return baseEdges;
    return baseEdges.map((e) => {
      if (e.id === focusedEdgeId) {
        const baseStrokeWidth = e.style?.strokeWidth || 1.5;
        return {
          ...e,
          style: { ...(e.style || {}), opacity: 1, strokeWidth: baseStrokeWidth + 1.5 },
          zIndex: 2,
        };
      }
      if (focusedEdgeIds.has(e.id)) {
        return { ...e, style: { ...(e.style || {}), opacity: 1 }, zIndex: 1 };
      }
      return { ...e, style: { ...(e.style || {}), opacity: 0.15 }, zIndex: 0 };
    });
  }, [baseEdges, focusedEdgeIds, focusedEdgeId]);

  useEffect(() => {
    const t = setTimeout(() => {
      try {
        fitView({ padding: 0.2, duration: 200 });
      } catch {
        // ignore
      }
    }, 50);
    return () => clearTimeout(t);
  }, [baseNodes, fitView]);

  const handleToggleGroup = useCallback((groupId) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  }, []);

  const handleNodeClick = useCallback(async (_evt, node) => {
    if (node.type === 'collapsedGroup') {
      handleToggleGroup(node.data.groupId);
      return;
    }
    const { kind, name, namespace, metadata } = node.data;

    // Synthesized RBAC nodes have no real K8s manifest; show a summary instead.
    if (SYNTHESIZED_KINDS.has(kind)) {
      setRbacModalState({
        isOpen: true,
        kind,
        name,
        namespace: namespace || '',
        metadata: metadata || {},
      });
      return;
    }

    const isDerivedSecret = kind === 'Secret' && metadata?.derived === true;

    setModalState({
      isOpen: true,
      namespace,
      kind,
      name,
      manifest: '',
      loading: !isDerivedSecret,
      infoMessage: isDerivedSecret
        ? 'Secret manifest not available — kure-monitor has no read access to Secrets by design.'
        : '',
    });

    if (isDerivedSecret) return;

    try {
      const res = await api.getResourceManifest(namespace, kind, name);
      setModalState((s) =>
        s.namespace === namespace && s.kind === kind && s.name === name
          ? { ...s, loading: false, manifest: res.manifest || '', infoMessage: '' }
          : s
      );
    } catch (err) {
      const is403 = err?.status === 403;
      const msg = is403
        ? 'Secret manifest not available — kure-monitor has no read access to Secrets by design.'
        : `Failed to load manifest: ${err.message || 'unknown error'}`;
      setModalState((s) =>
        s.namespace === namespace && s.kind === kind && s.name === name
          ? { ...s, loading: false, manifest: '', infoMessage: msg }
          : s
      );
    }
  }, [handleToggleGroup]);

  const closeModal = useCallback(() => {
    setModalState((s) => ({ ...s, isOpen: false }));
  }, []);

  const closeRbacModal = useCallback(() => {
    setRbacModalState((s) => ({ ...s, isOpen: false }));
  }, []);

  const handleEdgeClick = useCallback((_evt, edge) => {
    setFocusedEdgeId((prev) => (prev === edge.id ? null : edge.id));
  }, []);

  const handlePaneClick = useCallback(() => {
    setFocusedEdgeId(null);
  }, []);

  const groups = data?.groups || [];

  return (
    <>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        onPaneClick={handlePaneClick}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        minZoom={0.1}
        maxZoom={2}
      >
        <Background color={isDark ? '#374151' : '#e5e7eb'} gap={16} />
        <Controls showInteractive={false} />
        <Panel position="top-right">
          <Legend
            isDark={isDark}
            groups={groups}
            collapsedGroups={collapsedGroups}
            onToggleGroup={handleToggleGroup}
          />
        </Panel>
      </ReactFlow>
      <ManifestModal
        isOpen={modalState.isOpen}
        onClose={closeModal}
        podName={modalState.name}
        namespace={modalState.namespace}
        manifest={modalState.manifest}
        solution={null}
        isDark={isDark}
        aiEnabled={false}
        title={`${modalState.kind} Manifest`}
        subtitle={modalState.namespace ? `${modalState.namespace}/${modalState.name}` : modalState.name}
        infoMessage={modalState.infoMessage}
        loading={modalState.loading}
      />
      <RbacSummaryModal
        isOpen={rbacModalState.isOpen}
        onClose={closeRbacModal}
        kind={rbacModalState.kind}
        name={rbacModalState.name}
        namespace={rbacModalState.namespace}
        metadata={rbacModalState.metadata}
        isDark={isDark}
      />
    </>
  );
};

const TopologyGraph = ({ data, isDark = false }) => {
  return (
    <div className={`w-full h-full ${isDark ? 'bg-gray-900' : 'bg-white'}`}>
      <ReactFlowProvider>
        <Inner data={data} isDark={isDark} />
      </ReactFlowProvider>
    </div>
  );
};

export default TopologyGraph;

import React from 'react';

const noop = () => {};

export const Position = {
  Top: 'top',
  Bottom: 'bottom',
  Left: 'left',
  Right: 'right',
};

export const MarkerType = {
  Arrow: 'arrow',
  ArrowClosed: 'arrowclosed',
};

export const Handle = ({ type, position, ...rest }) =>
  React.createElement('div', { 'data-testid': `handle-${type}-${position}`, ...rest });

export const Background = () => React.createElement('div', { 'data-testid': 'rf-background' });
export const Controls = () => React.createElement('div', { 'data-testid': 'rf-controls' });
export const Panel = ({ children }) =>
  React.createElement('div', { 'data-testid': 'rf-panel' }, children);

export const ReactFlowProvider = ({ children }) =>
  React.createElement('div', { 'data-testid': 'rf-provider' }, children);

export const useReactFlow = () => ({
  fitView: noop,
  getNodes: () => [],
  getEdges: () => [],
});

const ReactFlow = ({
  nodes = [],
  edges = [],
  nodeTypes = {},
  onNodeClick,
  onEdgeClick,
  onPaneClick,
  children,
}) => {
  const handlePaneClick = (evt) => {
    if (onPaneClick) onPaneClick(evt);
  };
  return React.createElement(
    'div',
    { 'data-testid': 'react-flow', onClick: handlePaneClick },
    React.createElement(
      'div',
      { 'data-testid': 'rf-edges' },
      edges.map((e) => {
        const handleEdgeClick = (evt) => {
          evt.stopPropagation();
          if (onEdgeClick) onEdgeClick(evt, e);
        };
        return React.createElement('div', {
          key: e.id,
          'data-testid': `edge-${e.data?.edgeType || 'unknown'}`,
          'data-edge-id': e.id,
          'data-source': e.source,
          'data-target': e.target,
          'data-opacity': e.style?.opacity != null ? String(e.style.opacity) : '1',
          'data-stroke-width': e.style?.strokeWidth != null ? String(e.style.strokeWidth) : '',
          onClick: handleEdgeClick,
        });
      })
    ),
    React.createElement(
      'div',
      { 'data-testid': 'rf-nodes' },
      nodes.map((n) => {
        const Comp = nodeTypes[n.type];
        const handleClick = (evt) => {
          evt.stopPropagation();
          if (onNodeClick) onNodeClick(evt, n);
        };
        return React.createElement(
          'div',
          {
            key: n.id,
            'data-testid': `node-${n.id}`,
            'data-kind': n.data?.kind,
            'data-opacity': n.style?.opacity != null ? String(n.style.opacity) : '1',
            onClick: handleClick,
          },
          Comp ? React.createElement(Comp, { data: n.data }) : null
        );
      })
    ),
    children
  );
};

export default ReactFlow;

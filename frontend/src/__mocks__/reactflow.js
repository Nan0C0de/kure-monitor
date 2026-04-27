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

const ReactFlow = ({ nodes = [], edges = [], nodeTypes = {}, onNodeClick, children }) => {
  return React.createElement(
    'div',
    { 'data-testid': 'react-flow' },
    React.createElement(
      'div',
      { 'data-testid': 'rf-edges' },
      edges.map((e) =>
        React.createElement('div', {
          key: e.id,
          'data-testid': `edge-${e.data?.edgeType || 'unknown'}`,
          'data-source': e.source,
          'data-target': e.target,
        })
      )
    ),
    React.createElement(
      'div',
      { 'data-testid': 'rf-nodes' },
      nodes.map((n) => {
        const Comp = nodeTypes[n.type];
        const handleClick = (evt) => {
          if (onNodeClick) onNodeClick(evt, n);
        };
        return React.createElement(
          'div',
          {
            key: n.id,
            'data-testid': `node-${n.id}`,
            'data-kind': n.data?.kind,
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

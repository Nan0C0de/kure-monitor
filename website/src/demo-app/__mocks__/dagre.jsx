const makeGraph = () => {
  const nodes = new Map();
  const edges = [];
  return {
    setDefaultEdgeLabel: () => {},
    setGraph: () => {},
    setNode: (id, attrs) => {
      nodes.set(id, { ...attrs, x: 0, y: 0 });
    },
    setEdge: (s, t) => {
      edges.push([s, t]);
    },
    node: (id) => nodes.get(id),
  };
};

const dagre = {
  graphlib: { Graph: function Graph() { return makeGraph(); } },
  layout: () => {},
};

module.exports = dagre;
module.exports.default = dagre;

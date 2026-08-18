import React from 'react';

const ReactMarkdown = ({ children }) => {
  return React.createElement('div', { 'data-testid': 'react-markdown' }, children);
};

export default ReactMarkdown;
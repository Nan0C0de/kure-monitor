import React from 'react';

// Known icons that other tests directly assert on via data-testid.
const EXPLICIT = {
  ChevronDown: 'chevron-down',
  ChevronRight: 'chevron-right',
  FileText: 'file-text',
  X: 'x',
  AlertCircle: 'alert-circle',
  Activity: 'activity',
  CheckCircle: 'check-circle',
  Clock: 'clock',
};

const iconFor = (testId) => (props) =>
  React.createElement('div', { ...props, 'data-testid': testId });

// A Proxy returns a generic stub for any icon name we don't explicitly list,
// which avoids "Element type is invalid" when components use uncommon icons.
const handler = {
  get(_target, prop) {
    if (prop === '__esModule') return true;
    if (typeof prop !== 'string') return undefined;
    if (EXPLICIT[prop]) return iconFor(EXPLICIT[prop]);
    // Convert e.g. "UserPlus" -> "user-plus"
    const kebab = prop.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase();
    return iconFor(kebab);
  },
};

module.exports = new Proxy({}, handler);

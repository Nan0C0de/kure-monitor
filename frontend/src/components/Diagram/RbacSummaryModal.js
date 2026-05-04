import React from 'react';
import { X, Key, User, Users } from 'lucide-react';

/**
 * Modal that summarizes synthesized RBAC nodes (Permission, Subject:User,
 * Subject:Group). These nodes have no real Kubernetes manifest, so we render
 * the data we already have from `node.metadata` instead of fetching anything.
 */
const RbacSummaryModal = ({
  isOpen,
  onClose,
  kind,
  name,
  namespace,
  metadata,
  isDark = false,
}) => {
  if (!isOpen) return null;

  const md = metadata || {};
  const isPermission = kind === 'Permission';
  const isSubject = kind === 'Subject:User' || kind === 'Subject:Group';

  const HeaderIcon = isPermission ? Key : kind === 'Subject:Group' ? Users : User;

  const subtitle = namespace && namespace !== '--' ? `${namespace}/${name}` : name;

  const badgeBase = isDark
    ? 'inline-block text-xs font-medium px-2 py-0.5 rounded border bg-gray-800 border-gray-600 text-gray-100'
    : 'inline-block text-xs font-medium px-2 py-0.5 rounded border bg-gray-100 border-gray-300 text-gray-800';

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto" role="dialog" aria-modal="true">
      <div className="flex items-center justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
        <div
          className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"
          onClick={onClose}
        />
        <div
          className={`inline-block align-bottom rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-2xl sm:w-full ${
            isDark ? 'bg-gray-800' : 'bg-white'
          }`}
        >
          <div className={`px-4 pt-5 pb-4 sm:p-6 sm:pb-4 ${isDark ? 'bg-gray-800' : 'bg-white'}`}>
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-start space-x-2">
                <HeaderIcon className={`w-5 h-5 mt-0.5 ${isDark ? 'text-gray-200' : 'text-gray-700'}`} />
                <div>
                  <h3
                    className={`text-lg leading-6 font-medium ${
                      isDark ? 'text-gray-100' : 'text-gray-900'
                    }`}
                  >
                    {kind}
                  </h3>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    {subtitle}
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                aria-label="Close"
                className={`inline-flex items-center justify-center w-8 h-8 focus:outline-none ${
                  isDark ? 'text-gray-500 hover:text-gray-400' : 'text-gray-400 hover:text-gray-500'
                }`}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {isSubject && (
              <div
                className={`rounded-md border px-4 py-3 text-sm ${
                  isDark
                    ? 'bg-blue-900/30 border-blue-700 text-blue-200'
                    : 'bg-blue-50 border-blue-200 text-blue-800'
                }`}
              >
                <p className="mb-2">
                  This is a synthesized RBAC subject — it represents a{' '}
                  <strong>{kind === 'Subject:User' ? 'User' : 'Group'}</strong> referenced by a
                  RoleBinding or ClusterRoleBinding. It is not a real Kubernetes object, so there
                  is no manifest to display.
                </p>
                <div className="mt-3 grid grid-cols-[6rem_1fr] gap-y-1">
                  <span className="font-semibold">Kind:</span>
                  <span>{kind === 'Subject:User' ? 'User' : 'Group'}</span>
                  <span className="font-semibold">Name:</span>
                  <span className="font-mono break-all">{name}</span>
                </div>
              </div>
            )}

            {isPermission && (
              <div className={`text-sm ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>
                <p className={`mb-3 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                  Synthesized permission node — represents one (apiGroup, resource) entry granted
                  by the role.
                </p>
                <div className="grid grid-cols-[8rem_1fr] gap-y-2 mb-4">
                  <span className="font-semibold">API group:</span>
                  <span className="font-mono break-all">
                    {md.apiGroup === '' ? '"" (core)' : md.apiGroup || '—'}
                  </span>
                  <span className="font-semibold">Resource:</span>
                  <span className="font-mono break-all">{md.resource || '—'}</span>
                </div>

                <div className="mb-3">
                  <div
                    className={`font-semibold mb-1 ${isDark ? 'text-gray-200' : 'text-gray-800'}`}
                  >
                    Verbs
                  </div>
                  {Array.isArray(md.verbs) && md.verbs.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {md.verbs.map((v) => (
                        <span key={v} className={badgeBase} data-testid={`verb-${v}`}>
                          {v}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <span className={isDark ? 'text-gray-400' : 'text-gray-500'}>—</span>
                  )}
                </div>

                {Array.isArray(md.resourceNames) && md.resourceNames.length > 0 && (
                  <div className="mb-3">
                    <div
                      className={`font-semibold mb-1 ${
                        isDark ? 'text-gray-200' : 'text-gray-800'
                      }`}
                    >
                      Resource names
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {md.resourceNames.map((n) => (
                        <span key={n} className={`${badgeBase} font-mono`}>
                          {n}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {Array.isArray(md.nonResourceURLs) && md.nonResourceURLs.length > 0 && (
                  <div className="mb-3">
                    <div
                      className={`font-semibold mb-1 ${
                        isDark ? 'text-gray-200' : 'text-gray-800'
                      }`}
                    >
                      Non-resource URLs
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {md.nonResourceURLs.map((u) => (
                        <span key={u} className={`${badgeBase} font-mono`}>
                          {u}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div
            className={`px-4 py-3 sm:px-6 sm:flex sm:justify-end ${
              isDark ? 'bg-gray-900' : 'bg-gray-50'
            }`}
          >
            <button
              type="button"
              onClick={onClose}
              className="inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-blue-600 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RbacSummaryModal;

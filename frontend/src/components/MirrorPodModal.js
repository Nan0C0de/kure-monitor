import React, { useState, useEffect, useRef, useCallback } from 'react';
import { X, RefreshCw, CheckCircle, XCircle, Clock, Trash2, AlertCircle, FlaskConical, FileEdit } from 'lucide-react';
import { api } from '../services/api';

const POLL_INTERVAL = 5000;

const formatTimeRemaining = (expiresAt) => {
  if (!expiresAt) return '--:--';
  const remaining = Math.max(0, Math.floor((new Date(expiresAt) - Date.now()) / 1000));
  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
};

const PhaseIndicator = ({ phase }) => {
  if (!phase) return null;

  const lower = phase.toLowerCase();
  if (lower === 'running' || lower === 'succeeded') {
    return <CheckCircle className="w-5 h-5 text-green-500" />;
  }
  if (lower === 'pending') {
    return <RefreshCw className="w-5 h-5 text-yellow-500 animate-spin" />;
  }
  // Failed, CrashLoopBackOff, etc.
  return <XCircle className="w-5 h-5 text-red-500" />;
};

const MirrorPodModal = ({ isOpen, onClose, pod, isDark = false, defaultTTL = 180 }) => {
  // States: confirm | loading-manifest | edit | deploying | running | result | deleted | error
  const [stage, setStage] = useState('confirm');
  const [mirrorId, setMirrorId] = useState(null);
  const [mirrorInfo, setMirrorInfo] = useState(null);
  const [error, setError] = useState(null);
  const [timeRemaining, setTimeRemaining] = useState('');
  const [editedManifest, setEditedManifest] = useState('');
  const [manifestExplanation, setManifestExplanation] = useState('');
  const [useCustomManifest, setUseCustomManifest] = useState(false);
  const pollRef = useRef(null);
  const countdownRef = useRef(null);

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setStage('confirm');
      setMirrorId(null);
      setMirrorInfo(null);
      setError(null);
      setTimeRemaining('');
      setEditedManifest('');
      setManifestExplanation('');
      setUseCustomManifest(false);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (countdownRef.current) clearInterval(countdownRef.current);
    };
  }, [isOpen]);

  const pollStatus = useCallback(async (id) => {
    try {
      const status = await api.getMirrorStatus(id);
      setMirrorInfo(status);

      const phase = (status.phase || '').toLowerCase();

      if (phase === 'running' || phase === 'succeeded') {
        setStage('result');
        if (pollRef.current) clearInterval(pollRef.current);
      } else if (
        phase === 'failed' ||
        phase === 'crashloopbackoff' ||
        phase === 'error'
      ) {
        setStage('result');
        if (pollRef.current) clearInterval(pollRef.current);
      }
      // else still pending, keep polling
    } catch (err) {
      // If 404, mirror was likely deleted (TTL expired)
      if (err.message && err.message.includes('404')) {
        setStage('deleted');
        if (pollRef.current) clearInterval(pollRef.current);
        if (countdownRef.current) clearInterval(countdownRef.current);
      }
    }
  }, []);

  const handleEditManifest = async () => {
    setStage('loading-manifest');
    setError(null);

    try {
      const preview = await api.previewMirrorPod(pod.id);
      setEditedManifest(preview.fixed_manifest || '');
      setManifestExplanation(preview.explanation || '');
      setStage('edit');
    } catch (err) {
      setError(err.message || 'Failed to generate manifest preview');
      setStage('error');
    }
  };

  const handleDeployEdited = () => {
    setUseCustomManifest(true);
    handleDeploy(editedManifest);
  };

  const handleDeploy = async (manifest = null) => {
    setStage('deploying');
    setError(null);

    try {
      const result = await api.deployMirrorPod(pod.id, defaultTTL, manifest);
      setMirrorId(result.mirror_id);
      setMirrorInfo(result);
      setStage('running');

      // Start polling for status
      pollRef.current = setInterval(() => {
        pollStatus(result.mirror_id);
      }, POLL_INTERVAL);

      // Start countdown timer
      if (result.created_at) {
        const expiresAt = new Date(new Date(result.created_at).getTime() + (result.ttl_seconds || defaultTTL) * 1000).toISOString();
        setMirrorInfo(prev => ({ ...prev, expires_at: expiresAt }));

        countdownRef.current = setInterval(() => {
          const remaining = Math.max(0, Math.floor((new Date(expiresAt) - Date.now()) / 1000));
          setTimeRemaining(formatTimeRemaining(expiresAt));
          if (remaining <= 0) {
            if (countdownRef.current) clearInterval(countdownRef.current);
            // Give a moment for the backend to clean up, then check
            setTimeout(() => pollStatus(result.mirror_id), 2000);
          }
        }, 1000);
      }

      // Do an immediate poll
      pollStatus(result.mirror_id);
    } catch (err) {
      setError(err.message || 'Failed to deploy mirror pod');
      setStage('error');
    }
  };

  const handleDelete = async () => {
    if (!mirrorId) return;
    try {
      await api.deleteMirrorPod(mirrorId);
      setStage('deleted');
      if (pollRef.current) clearInterval(pollRef.current);
      if (countdownRef.current) clearInterval(countdownRef.current);
    } catch (err) {
      setError(err.message || 'Failed to delete mirror pod');
    }
  };

  const handleClose = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (countdownRef.current) clearInterval(countdownRef.current);
    onClose();
  };

  if (!isOpen) return null;

  const phase = (mirrorInfo?.phase || '').toLowerCase();
  const isSuccess = phase === 'running' || phase === 'succeeded';
  const isFailed = phase === 'failed' || phase === 'crashloopbackoff' || phase === 'error';

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
        {/* Overlay */}
        <div
          className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"
          onClick={handleClose}
        ></div>

        {/* Modal */}
        <div className={`inline-block align-bottom rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:w-full ${
          stage === 'edit' || stage === 'loading-manifest' ? 'sm:max-w-3xl' : 'sm:max-w-lg'
        } ${isDark ? 'bg-gray-800' : 'bg-white'}`}>
          <div className={`px-4 pt-5 pb-4 sm:p-6 sm:pb-4 ${isDark ? 'bg-gray-800' : 'bg-white'}`}>
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center">
                <FlaskConical className="w-5 h-5 text-purple-600 mr-2" />
                <h3 className={`text-lg leading-6 font-medium ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>
                  Test Fix
                </h3>
              </div>
              <button
                onClick={handleClose}
                className={`inline-flex items-center justify-center w-8 h-8 focus:outline-none ${isDark ? 'text-gray-500 hover:text-gray-400' : 'text-gray-400 hover:text-gray-500'}`}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Confirm stage */}
            {stage === 'confirm' && (
              <div>
                <p className={`text-sm mb-4 ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                  Deploy a temporary mirror pod with the AI-generated fix applied to{' '}
                  <span className={`font-medium ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>{pod.pod_name}</span>?
                </p>
                <p className={`text-sm mb-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  The mirror pod will auto-delete after{' '}
                  <span className="font-medium">{defaultTTL} seconds</span>.
                </p>
                <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                  This creates a temporary copy in the <span className="font-mono">{pod.namespace}</span> namespace
                  to verify the fix works without modifying the original pod.
                </p>
              </div>
            )}

            {/* Loading manifest stage */}
            {stage === 'loading-manifest' && (
              <div className="flex items-center justify-center py-8">
                <RefreshCw className="w-6 h-6 text-blue-500 animate-spin mr-3" />
                <span className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Generating fixed manifest...</span>
              </div>
            )}

            {/* Edit manifest stage */}
            {stage === 'edit' && (
              <div className="space-y-3">
                <p className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                  Review and edit the AI-generated fixed manifest before deploying.
                </p>
                {manifestExplanation && (
                  <div className={`rounded-md p-3 ${isDark ? 'bg-blue-900/30 border border-blue-700' : 'bg-blue-50 border border-blue-200'}`}>
                    <p className={`text-sm ${isDark ? 'text-blue-300' : 'text-blue-700'}`}>{manifestExplanation}</p>
                  </div>
                )}
                <textarea
                  value={editedManifest}
                  onChange={(e) => setEditedManifest(e.target.value)}
                  className={`w-full rounded-md border bg-gray-900 text-gray-100 p-4 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${isDark ? 'border-gray-600' : 'border-gray-300'}`}
                  style={{
                    fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace',
                    height: '400px',
                    resize: 'vertical',
                  }}
                  spellCheck={false}
                />
              </div>
            )}

            {/* Deploying stage */}
            {stage === 'deploying' && (
              <div className="flex items-center justify-center py-8">
                <RefreshCw className="w-6 h-6 text-blue-500 animate-spin mr-3" />
                <span className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Creating mirror pod...</span>
              </div>
            )}

            {/* Running stage */}
            {stage === 'running' && mirrorInfo && (
              <div className="space-y-4">
                <div className={`rounded-md p-4 ${isDark ? 'bg-gray-900' : 'bg-gray-50'}`}>
                  <dl className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <dt className={`font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Pod Name</dt>
                      <dd className={`font-mono text-xs ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>{mirrorInfo.mirror_pod_name}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className={`font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Namespace</dt>
                      <dd className={isDark ? 'text-gray-200' : 'text-gray-900'}>{mirrorInfo.namespace}</dd>
                    </div>
                    <div className="flex items-center justify-between">
                      <dt className={`font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Phase</dt>
                      <dd className="flex items-center gap-2">
                        <PhaseIndicator phase={mirrorInfo.phase} />
                        <span className={isDark ? 'text-gray-200' : 'text-gray-900'}>{mirrorInfo.phase || 'Pending'}</span>
                      </dd>
                    </div>
                    <div className="flex items-center justify-between">
                      <dt className={`font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Time Remaining</dt>
                      <dd className={`flex items-center gap-1 ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>
                        <Clock className={`w-4 h-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                        {timeRemaining || formatTimeRemaining(mirrorInfo.expires_at)}
                      </dd>
                    </div>
                  </dl>
                </div>

                {/* Events */}
                {mirrorInfo.events && mirrorInfo.events.length > 0 && (
                  <div>
                    <h4 className={`text-sm font-medium mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Events</h4>
                    <div className="max-h-40 overflow-y-auto space-y-1">
                      {mirrorInfo.events.map((event, index) => (
                        <div key={index} className="flex items-start gap-2 text-xs">
                          <span className={`px-1.5 py-0.5 rounded shrink-0 ${
                            event.type === 'Warning'
                              ? isDark ? 'bg-red-900/50 text-red-300' : 'bg-red-100 text-red-700'
                              : isDark ? 'bg-blue-900/50 text-blue-300' : 'bg-blue-100 text-blue-700'
                          }`}>
                            {event.type || 'Normal'}
                          </span>
                          <span className={isDark ? 'text-gray-400' : 'text-gray-600'}>{event.message || event.reason}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Result stage */}
            {stage === 'result' && mirrorInfo && (
              <div className="space-y-4">
                {isSuccess && (
                  <div className={`rounded-md p-4 ${isDark ? 'bg-green-900/30 border border-green-700' : 'bg-green-50 border border-green-200'}`}>
                    <div className="flex items-center mb-2">
                      <CheckCircle className="w-5 h-5 text-green-500 mr-2" />
                      <span className={`text-sm font-medium ${isDark ? 'text-green-300' : 'text-green-800'}`}>Fix appears to be working!</span>
                    </div>
                    <p className={`text-sm ${isDark ? 'text-green-400' : 'text-green-700'}`}>
                      The mirror pod started successfully. The AI-generated fix resolved the issue.
                    </p>
                  </div>
                )}

                {isFailed && (
                  <div className={`rounded-md p-4 ${isDark ? 'bg-red-900/30 border border-red-700' : 'bg-red-50 border border-red-200'}`}>
                    <div className="flex items-center mb-2">
                      <XCircle className="w-5 h-5 text-red-500 mr-2" />
                      <span className={`text-sm font-medium ${isDark ? 'text-red-300' : 'text-red-800'}`}>The fix didn't resolve the issue</span>
                    </div>
                    <p className={`text-sm ${isDark ? 'text-red-400' : 'text-red-700'}`}>
                      Mirror pod failed with: <span className="font-mono">{mirrorInfo.phase}</span>
                    </p>
                  </div>
                )}

                {/* Mirror info summary */}
                <div className={`rounded-md p-4 ${isDark ? 'bg-gray-900' : 'bg-gray-50'}`}>
                  <dl className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <dt className={`font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Pod Name</dt>
                      <dd className={`font-mono text-xs ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>{mirrorInfo.mirror_pod_name}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className={`font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Namespace</dt>
                      <dd className={isDark ? 'text-gray-200' : 'text-gray-900'}>{mirrorInfo.namespace}</dd>
                    </div>
                    <div className="flex items-center justify-between">
                      <dt className={`font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Phase</dt>
                      <dd className="flex items-center gap-2">
                        <PhaseIndicator phase={mirrorInfo.phase} />
                        <span className={isDark ? 'text-gray-200' : 'text-gray-900'}>{mirrorInfo.phase}</span>
                      </dd>
                    </div>
                  </dl>
                </div>

                {/* Events */}
                {mirrorInfo.events && mirrorInfo.events.length > 0 && (
                  <div>
                    <h4 className={`text-sm font-medium mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Events</h4>
                    <div className="max-h-40 overflow-y-auto space-y-1">
                      {mirrorInfo.events.map((event, index) => (
                        <div key={index} className="flex items-start gap-2 text-xs">
                          <span className={`px-1.5 py-0.5 rounded shrink-0 ${
                            event.type === 'Warning'
                              ? isDark ? 'bg-red-900/50 text-red-300' : 'bg-red-100 text-red-700'
                              : isDark ? 'bg-blue-900/50 text-blue-300' : 'bg-blue-100 text-blue-700'
                          }`}>
                            {event.type || 'Normal'}
                          </span>
                          <span className={isDark ? 'text-gray-400' : 'text-gray-600'}>{event.message || event.reason}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Deleted stage */}
            {stage === 'deleted' && (
              <div className={`rounded-md p-4 ${isDark ? 'bg-gray-900 border border-gray-700' : 'bg-gray-50 border border-gray-200'}`}>
                <div className="flex items-center">
                  <CheckCircle className={`w-5 h-5 mr-2 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                  <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Mirror pod was cleaned up.</span>
                </div>
              </div>
            )}

            {/* Error stage */}
            {stage === 'error' && (
              <div className={`rounded-md p-4 ${isDark ? 'bg-red-900/30 border border-red-700' : 'bg-red-50 border border-red-200'}`}>
                <div className="flex items-center">
                  <AlertCircle className="w-5 h-5 text-red-500 mr-2" />
                  <span className={`text-sm ${isDark ? 'text-red-300' : 'text-red-700'}`}>{error || 'An error occurred'}</span>
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className={`px-4 py-3 sm:px-6 sm:flex sm:justify-between ${isDark ? 'bg-gray-900' : 'bg-gray-50'}`}>
            <div>
              {(stage === 'running' || stage === 'result') && stage !== 'deleted' && (
                <button
                  type="button"
                  onClick={handleDelete}
                  className={`inline-flex items-center px-4 py-2 shadow-sm text-sm font-medium rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 ${isDark ? 'border border-red-700 text-red-300 bg-red-900/40 hover:bg-red-900/60' : 'border border-red-300 text-red-700 bg-red-50 hover:bg-red-100'}`}
                >
                  <Trash2 className="w-4 h-4 mr-2" />
                  Delete Now
                </button>
              )}
            </div>
            <div className="flex gap-2">
              {stage === 'confirm' && (
                <>
                  <button
                    type="button"
                    className={`inline-flex justify-center rounded-md border shadow-sm px-4 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 ${
                      isDark
                        ? 'border-gray-600 bg-gray-700 text-gray-300 hover:bg-gray-600'
                        : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                    }`}
                    onClick={handleClose}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className={`inline-flex items-center justify-center rounded-md border shadow-sm px-4 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 ${
                      isDark
                        ? 'border-gray-600 bg-gray-700 text-gray-300 hover:bg-gray-600'
                        : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                    }`}
                    onClick={handleEditManifest}
                  >
                    <FileEdit className="w-4 h-4 mr-2" />
                    Edit Manifest
                  </button>
                  <button
                    type="button"
                    className="inline-flex items-center justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-purple-600 text-sm font-medium text-white hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500"
                    onClick={() => handleDeploy()}
                  >
                    <FlaskConical className="w-4 h-4 mr-2" />
                    Deploy
                  </button>
                </>
              )}
              {stage === 'edit' && (
                <>
                  <button
                    type="button"
                    className={`inline-flex justify-center rounded-md border shadow-sm px-4 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 ${
                      isDark
                        ? 'border-gray-600 bg-gray-700 text-gray-300 hover:bg-gray-600'
                        : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                    }`}
                    onClick={() => setStage('confirm')}
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    className="inline-flex items-center justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-blue-600 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                    onClick={handleDeployEdited}
                  >
                    <FlaskConical className="w-4 h-4 mr-2" />
                    Deploy This
                  </button>
                </>
              )}
              {stage !== 'confirm' && stage !== 'edit' && (
                <button
                  type="button"
                  className="inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-blue-600 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                  onClick={handleClose}
                >
                  Close
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MirrorPodModal;

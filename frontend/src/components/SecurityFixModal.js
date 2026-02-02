import React, { useState, useEffect, useRef, useCallback } from 'react';
import { X, Copy, Download, RefreshCw, Sparkles, FileText, AlertCircle } from 'lucide-react';
import { api } from '../services/api';

const SecurityFixModal = ({ isOpen, onClose, finding, isDark = false, aiEnabled = false }) => {
  const [manifest, setManifest] = useState('');
  const [fixData, setFixData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(null);
  const [viewMode, setViewMode] = useState('diff'); // 'diff', 'original', 'fixed'
  const textareaRef = useRef(null);

  const loadManifestAndFix = useCallback(async () => {
    if (!finding?.id) return;

    setLoading(true);
    setError(null);

    try {
      // Load manifest
      const manifestData = await api.getSecurityFindingManifest(finding.id);
      setManifest(manifestData.manifest || '');

      // Auto-generate fix if AI is enabled and manifest exists
      if (aiEnabled && manifestData.manifest) {
        setGenerating(true);
        try {
          const fix = await api.generateSecurityFix(finding.id);
          setFixData(fix);
        } catch (fixErr) {
          console.error('Failed to generate fix:', fixErr);
          setFixData({
            diff: [],
            fixed_manifest: '',
            explanation: finding.remediation,
            is_fallback: true
          });
        } finally {
          setGenerating(false);
        }
      }
    } catch (err) {
      console.error('Failed to load manifest:', err);
      setError('Failed to load manifest');
    } finally {
      setLoading(false);
    }
  }, [finding, aiEnabled]);

  useEffect(() => {
    if (isOpen && finding) {
      setManifest('');
      setFixData(null);
      setViewMode('diff');
      loadManifestAndFix();
    }
  }, [isOpen, finding, loadManifestAndFix]);

  const handleRetry = async () => {
    if (!finding?.id || generating) return;

    setGenerating(true);
    setError(null);

    try {
      const fix = await api.generateSecurityFix(finding.id);
      setFixData(fix);
    } catch (err) {
      console.error('Failed to generate fix:', err);
      setError('Failed to generate AI fix');
    } finally {
      setGenerating(false);
    }
  };

  const getCurrentContent = () => {
    if (viewMode === 'original') return manifest;
    if (viewMode === 'fixed' && fixData?.fixed_manifest) return fixData.fixed_manifest;
    return manifest;
  };

  const handleCopy = async () => {
    const content = viewMode === 'diff' && fixData?.fixed_manifest
      ? fixData.fixed_manifest
      : getCurrentContent();
    try {
      await navigator.clipboard.writeText(content || '');
    } catch {
      if (textareaRef.current) {
        textareaRef.current.select();
        document.execCommand('copy');
      }
    }
  };

  const handleDownload = () => {
    const content = viewMode === 'diff' && fixData?.fixed_manifest
      ? fixData.fixed_manifest
      : getCurrentContent();
    const suffix = viewMode === 'original' ? '' : '-fixed';
    const blob = new Blob([content || ''], { type: 'text/yaml' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = `${finding?.resource_name || 'resource'}${suffix}.yaml`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  if (!isOpen) return null;

  const hasDiff = fixData?.diff && fixData.diff.length > 0;
  const hasFixedManifest = fixData?.fixed_manifest;

  const renderDiffView = () => {
    if (!hasDiff) {
      // No diff available - show original manifest with remediation
      if (!manifest) {
        return (
          <div className={`flex items-center justify-center h-full ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
            <FileText className="w-6 h-6 mr-2" />
            <span>No manifest available for this resource</span>
          </div>
        );
      }

      const lines = manifest.split('\n');
      return (
        <pre className="text-sm leading-relaxed">
          {lines.map((line, i) => (
            <div key={i}>
              <span className={`select-none w-8 inline-block text-right mr-4 ${isDark ? 'text-gray-600' : 'text-gray-400'}`}>
                {i + 1}
              </span>
              <span>{line || ' '}</span>
            </div>
          ))}
        </pre>
      );
    }

    let lineNum = 0;
    return (
      <pre className="text-sm leading-relaxed">
        {fixData.diff.map((entry, i) => {
          lineNum++;
          const isAdded = entry.type === 'added';
          const isRemoved = entry.type === 'removed';

          let bgClass = '';
          let textClass = isDark ? 'text-gray-300' : '';
          let prefix = ' ';

          if (isAdded) {
            bgClass = isDark ? 'bg-green-900/40 border-l-4 border-green-500' : 'bg-green-100 border-l-4 border-green-500';
            textClass = isDark ? 'text-green-300 font-medium' : 'text-green-800 font-medium';
            prefix = '+';
          } else if (isRemoved) {
            bgClass = isDark ? 'bg-red-900/40 border-l-4 border-red-500' : 'bg-red-100 border-l-4 border-red-500';
            textClass = isDark ? 'text-red-300 font-medium' : 'text-red-800 font-medium';
            prefix = '-';
          }

          return (
            <div key={i} className={`${bgClass} ${isAdded || isRemoved ? '-ml-1 pl-1' : ''}`}>
              <span className={`select-none w-4 inline-block text-right mr-2 ${
                isAdded ? (isDark ? 'text-green-500' : 'text-green-600') :
                isRemoved ? (isDark ? 'text-red-500' : 'text-red-600') :
                (isDark ? 'text-gray-600' : 'text-gray-400')
              }`}>
                {prefix}
              </span>
              <span className={`select-none w-8 inline-block text-right mr-4 ${isDark ? 'text-gray-600' : 'text-gray-400'}`}>
                {lineNum}
              </span>
              <span className={textClass}>{entry.content || ' '}</span>
            </div>
          );
        })}
      </pre>
    );
  };

  const renderPlainView = (content) => {
    if (!content) {
      return (
        <div className={`flex items-center justify-center h-full ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
          <FileText className="w-6 h-6 mr-2" />
          <span>{viewMode === 'fixed' ? 'No fixed manifest generated yet' : 'No manifest available'}</span>
        </div>
      );
    }

    const lines = content.split('\n');
    return (
      <pre className="text-sm leading-relaxed">
        {lines.map((line, i) => (
          <div key={i}>
            <span className={`select-none w-8 inline-block text-right mr-4 ${isDark ? 'text-gray-600' : 'text-gray-400'}`}>
              {i + 1}
            </span>
            <span>{line || ' '}</span>
          </div>
        ))}
      </pre>
    );
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
        {/* Overlay */}
        <div
          className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"
          onClick={onClose}
        ></div>

        {/* Modal */}
        <div className={`inline-block align-bottom rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-4xl sm:w-full ${
          isDark ? 'bg-gray-800' : 'bg-white'
        }`}>
          <div className={`px-4 pt-5 pb-4 sm:p-6 sm:pb-4 ${isDark ? 'bg-gray-800' : 'bg-white'}`}>
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className={`text-lg leading-6 font-medium ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>
                  Security Fix
                </h3>
                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  {finding?.resource_type}/{finding?.namespace}/{finding?.resource_name}
                  {finding?.title && <span className="ml-2">- {finding.title}</span>}
                </p>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  onClick={handleCopy}
                  className={`inline-flex items-center px-3 py-2 border shadow-sm text-sm leading-4 font-medium rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 ${
                    isDark
                      ? 'border-gray-600 text-gray-300 bg-gray-700 hover:bg-gray-600'
                      : 'border-gray-300 text-gray-700 bg-white hover:bg-gray-50'
                  }`}
                  title="Copy to clipboard"
                >
                  <Copy className="w-4 h-4 mr-1" />
                  Copy
                </button>
                <button
                  onClick={handleDownload}
                  className={`inline-flex items-center px-3 py-2 border shadow-sm text-sm leading-4 font-medium rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 ${
                    isDark
                      ? 'border-gray-600 text-gray-300 bg-gray-700 hover:bg-gray-600'
                      : 'border-gray-300 text-gray-700 bg-white hover:bg-gray-50'
                  }`}
                  title="Download YAML file"
                >
                  <Download className="w-4 h-4 mr-1" />
                  Download
                </button>
                <button
                  onClick={onClose}
                  className={`inline-flex items-center justify-center w-8 h-8 ${isDark ? 'text-gray-500 hover:text-gray-400' : 'text-gray-400 hover:text-gray-500'} focus:outline-none`}
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* View mode tabs */}
            <div className="flex space-x-1 mb-3">
              {['diff', 'original', 'fixed'].map((mode) => (
                <button
                  key={mode}
                  onClick={() => setViewMode(mode)}
                  className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                    viewMode === mode
                      ? isDark
                        ? 'bg-blue-600 text-white'
                        : 'bg-blue-100 text-blue-700'
                      : isDark
                        ? 'text-gray-400 hover:text-gray-200 hover:bg-gray-700'
                        : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  {mode === 'diff' ? 'Diff' : mode === 'original' ? 'Original' : 'Fixed'}
                </button>
              ))}
            </div>

            {/* Legend */}
            {viewMode === 'diff' && hasDiff && (
              <div className={`mb-3 flex items-center text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                <Sparkles className="w-4 h-4 mr-2 text-blue-500" />
                <span className={`inline-block w-3 h-3 rounded mr-1 ${isDark ? 'bg-green-900/40 border border-green-500' : 'bg-green-100 border border-green-300'}`}></span>
                <span className="mr-3">Added</span>
                <span className={`inline-block w-3 h-3 rounded mr-1 ${isDark ? 'bg-red-900/40 border border-red-500' : 'bg-red-100 border border-red-300'}`}></span>
                <span>Removed</span>
              </div>
            )}

            {/* Content */}
            <div className="mt-2 relative">
              {/* Loading / Generating overlay */}
              {(loading || generating) && (
                <div className={`absolute inset-0 z-10 flex items-center justify-center rounded-md ${
                  isDark ? 'bg-gray-800/80' : 'bg-white/80'
                }`}>
                  <div className="flex items-center space-x-3">
                    <RefreshCw className="w-5 h-5 animate-spin text-blue-500" />
                    <span className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                      {loading ? 'Loading manifest...' : 'Generating AI fix...'}
                    </span>
                  </div>
                </div>
              )}

              <div
                className={`w-full h-96 p-4 border rounded-md overflow-auto ${
                  isDark
                    ? 'border-gray-600 bg-gray-900'
                    : 'border-gray-300 bg-gray-50'
                }`}
                style={{ fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace' }}
              >
                {error ? (
                  <div className="flex items-center text-red-500">
                    <AlertCircle className="w-5 h-5 mr-2" />
                    <span>{error}</span>
                  </div>
                ) : viewMode === 'diff' ? (
                  renderDiffView()
                ) : (
                  renderPlainView(getCurrentContent())
                )}
              </div>

              <textarea
                ref={textareaRef}
                value={getCurrentContent() || ''}
                readOnly
                className="sr-only"
                tabIndex={-1}
              />
            </div>

            {/* Explanation section */}
            {fixData?.explanation && !fixData.is_fallback && (
              <div className={`mt-4 p-3 rounded-md ${isDark ? 'bg-blue-900/30 border border-blue-700' : 'bg-blue-50 border border-blue-200'}`}>
                <h4 className={`text-sm font-semibold mb-1 flex items-center ${isDark ? 'text-blue-300' : 'text-blue-700'}`}>
                  <Sparkles className="w-4 h-4 mr-1" />
                  AI Explanation
                </h4>
                <p className={`text-sm ${isDark ? 'text-blue-200' : 'text-blue-600'}`}>
                  {fixData.explanation}
                </p>
              </div>
            )}

            {/* Fallback remediation */}
            {(!fixData || fixData.is_fallback) && !generating && finding?.remediation && (
              <div className={`mt-4 p-3 rounded-md ${isDark ? 'bg-gray-700 border border-gray-600' : 'bg-gray-100 border border-gray-200'}`}>
                <h4 className={`text-sm font-semibold mb-1 ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
                  Remediation
                </h4>
                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                  {finding.remediation}
                </p>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className={`px-4 py-3 sm:px-6 sm:flex sm:justify-between ${isDark ? 'bg-gray-900' : 'bg-gray-50'}`}>
            <div>
              {manifest && (
                <button
                  type="button"
                  onClick={handleRetry}
                  disabled={generating || !aiEnabled}
                  className={`inline-flex items-center px-4 py-2 border shadow-sm text-sm font-medium rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed ${
                    isDark
                      ? 'border-blue-700 text-blue-300 bg-blue-900/50 hover:bg-blue-800/50'
                      : 'border-blue-300 text-blue-700 bg-blue-50 hover:bg-blue-100'
                  }`}
                  title={!aiEnabled ? 'AI provider not configured' : 'Retry AI fix generation'}
                >
                  <RefreshCw className={`w-4 h-4 mr-2 ${generating ? 'animate-spin' : ''}`} />
                  {generating ? 'Generating...' : 'Retry AI'}
                </button>
              )}
            </div>
            <div>
              <button
                type="button"
                className="inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-blue-600 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                onClick={onClose}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SecurityFixModal;

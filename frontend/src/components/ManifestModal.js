import React, { useRef, useMemo } from 'react';
import { X, Copy, Download, RefreshCw, Sparkles } from 'lucide-react';

// Keywords to look for in AI solutions that indicate manifest changes
const MANIFEST_KEYWORDS = [
  // Resource management
  'resources', 'limits', 'requests', 'memory', 'cpu',
  // Container configuration
  'image', 'imagePullPolicy', 'command', 'args', 'env', 'envFrom',
  // Security
  'securityContext', 'runAsNonRoot', 'runAsUser', 'readOnlyRootFilesystem',
  'allowPrivilegeEscalation', 'capabilities', 'privileged',
  // Health checks
  'livenessProbe', 'readinessProbe', 'startupProbe', 'httpGet', 'tcpSocket', 'exec',
  'initialDelaySeconds', 'periodSeconds', 'timeoutSeconds', 'failureThreshold',
  // Volumes
  'volumes', 'volumeMounts', 'persistentVolumeClaim', 'configMap', 'secret',
  'emptyDir', 'hostPath',
  // Pod spec
  'restartPolicy', 'nodeSelector', 'affinity', 'tolerations', 'serviceAccountName',
  'imagePullSecrets', 'hostNetwork', 'hostPID', 'dnsPolicy',
  // Container ports
  'ports', 'containerPort', 'protocol',
  // Labels and annotations
  'labels', 'annotations',
];

// Extract keywords from AI solution that are relevant to manifest changes
const extractHighlightKeywords = (solution) => {
  if (!solution) return new Set();

  const keywords = new Set();
  const lowerSolution = solution.toLowerCase();

  // Check for each manifest keyword in the solution
  MANIFEST_KEYWORDS.forEach(keyword => {
    if (lowerSolution.includes(keyword.toLowerCase())) {
      keywords.add(keyword.toLowerCase());
    }
  });

  // Also look for common patterns in AI suggestions
  const patterns = [
    /add\s+(?:a\s+)?(\w+)/gi,
    /set\s+(?:the\s+)?(\w+)/gi,
    /configure\s+(?:the\s+)?(\w+)/gi,
    /update\s+(?:the\s+)?(\w+)/gi,
    /change\s+(?:the\s+)?(\w+)/gi,
    /specify\s+(?:the\s+)?(\w+)/gi,
    /missing\s+(\w+)/gi,
    /`([^`]+)`/g, // Code blocks often contain field names
  ];

  patterns.forEach(pattern => {
    let match;
    while ((match = pattern.exec(solution)) !== null) {
      const word = match[1].toLowerCase();
      if (word.length > 2 && !['the', 'pod', 'container', 'kubernetes', 'yaml', 'manifest'].includes(word)) {
        keywords.add(word);
      }
    }
  });

  return keywords;
};

// Check if a line should be highlighted based on keywords
const shouldHighlightLine = (line, keywords) => {
  if (keywords.size === 0) return false;

  const lowerLine = line.toLowerCase();

  for (const keyword of keywords) {
    // Match the keyword as a key in YAML (e.g., "resources:" or "  resources:")
    if (lowerLine.includes(keyword + ':') || lowerLine.includes(keyword + ' :')) {
      return true;
    }
    // Match the keyword as a value assignment
    if (lowerLine.includes(': ' + keyword) || lowerLine.includes(':' + keyword)) {
      return true;
    }
  }

  return false;
};

const ManifestModal = ({
  isOpen,
  onClose,
  podName,
  namespace,
  manifest,
  solution,
  isFallbackSolution,
  onRetrySolution,
  isRetrying
}) => {
  const contentRef = useRef(null);

  // Extract keywords to highlight from the solution
  const highlightKeywords = useMemo(() => {
    return extractHighlightKeywords(solution);
  }, [solution]);

  // Parse and highlight manifest lines
  const highlightedLines = useMemo(() => {
    if (!manifest) return [];

    const lines = manifest.split('\n');
    return lines.map((line, index) => ({
      number: index + 1,
      content: line,
      highlighted: !isFallbackSolution && shouldHighlightLine(line, highlightKeywords)
    }));
  }, [manifest, highlightKeywords, isFallbackSolution]);

  if (!isOpen) return null;

  const handleCopyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(manifest || '');
    } catch (err) {
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = manifest || '';
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
    }
  };

  const handleDownload = () => {
    const blob = new Blob([manifest], { type: 'text/yaml' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = `${podName}-manifest.yaml`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  const hasHighlights = highlightedLines.some(line => line.highlighted);

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
        {/* Background overlay */}
        <div
          className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"
          onClick={onClose}
        ></div>

        {/* Modal panel */}
        <div className="inline-block align-bottom bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-4xl sm:w-full">
          <div className="bg-white px-4 pt-5 pb-4 sm:p-6 sm:pb-4">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-lg leading-6 font-medium text-gray-900">
                  Pod Manifest
                </h3>
                <p className="text-sm text-gray-500">
                  {namespace}/{podName}
                </p>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  onClick={handleCopyToClipboard}
                  className="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                  title="Copy to clipboard"
                >
                  <Copy className="w-4 h-4 mr-1" />
                  Copy
                </button>
                <button
                  onClick={handleDownload}
                  className="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                  title="Download YAML file"
                >
                  <Download className="w-4 h-4 mr-1" />
                  Download
                </button>
                <button
                  onClick={onClose}
                  className="inline-flex items-center justify-center w-8 h-8 text-gray-400 hover:text-gray-500 focus:outline-none"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Legend for highlights */}
            {hasHighlights && (
              <div className="mb-3 flex items-center text-sm text-gray-600">
                <Sparkles className="w-4 h-4 mr-2 text-green-600" />
                <span>
                  <span className="inline-block w-3 h-3 bg-green-100 border border-green-300 rounded mr-1"></span>
                  Highlighted lines indicate areas to review based on the AI solution
                </span>
              </div>
            )}

            {/* Content - Highlighted YAML */}
            <div className="mt-4">
              <div
                ref={contentRef}
                className="w-full h-96 p-4 border border-gray-300 rounded-md bg-gray-50 overflow-auto"
                style={{ fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace' }}
              >
                {manifest ? (
                  <pre className="text-sm leading-relaxed">
                    {highlightedLines.map((line) => (
                      <div
                        key={line.number}
                        className={`${
                          line.highlighted
                            ? 'bg-green-100 border-l-4 border-green-500 -ml-2 pl-2'
                            : ''
                        }`}
                      >
                        <span className="text-gray-400 select-none w-8 inline-block text-right mr-4">
                          {line.number}
                        </span>
                        <span className={line.highlighted ? 'text-green-800 font-medium' : ''}>
                          {line.content || ' '}
                        </span>
                      </div>
                    ))}
                  </pre>
                ) : (
                  <span className="text-gray-500"># No manifest available</span>
                )}
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="bg-gray-50 px-4 py-3 sm:px-6 sm:flex sm:justify-between">
            {/* Left side - Retry AI button (only shown when fallback) */}
            <div>
              {isFallbackSolution && onRetrySolution && (
                <button
                  type="button"
                  onClick={onRetrySolution}
                  disabled={isRetrying}
                  className="inline-flex items-center px-4 py-2 border border-blue-300 shadow-sm text-sm font-medium rounded-md text-blue-700 bg-blue-50 hover:bg-blue-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Retry AI to get better solution and manifest highlights"
                >
                  <RefreshCw className={`w-4 h-4 mr-2 ${isRetrying ? 'animate-spin' : ''}`} />
                  {isRetrying ? 'Retrying AI...' : 'Retry AI'}
                </button>
              )}
            </div>

            {/* Right side - Close button */}
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

export default ManifestModal;

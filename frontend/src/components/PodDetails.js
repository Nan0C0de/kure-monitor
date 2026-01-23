import React, { useState } from 'react';
import { FileText, RefreshCw, Copy, Check, Terminal } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { api } from '../services/api';

// Failure reasons where app logs would be useful (container actually runs/crashes)
const APP_CRASH_REASONS = ['CrashLoopBackOff', 'Error', 'OOMKilled'];

// Code block component with copy button - defined as standalone component
const CodeBlock = ({ code, language }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  return (
    <div className="relative group my-3">
      {language && (
        <div className="absolute top-0 left-0 px-2 py-1 text-xs text-gray-400 bg-gray-700 rounded-tl rounded-br">
          {language}
        </div>
      )}
      <button
        onClick={handleCopy}
        className="absolute top-2 right-2 p-1.5 rounded bg-gray-700 hover:bg-gray-600 text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity"
        title="Copy code"
      >
        {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
      </button>
      <pre className="bg-gray-800 text-gray-100 p-4 pt-8 rounded overflow-x-auto text-xs leading-relaxed whitespace-pre-wrap break-words">
        <code>{code}</code>
      </pre>
    </div>
  );
};

const PodDetails = ({ pod, onViewManifest, onViewLogs, onSolutionUpdated, aiEnabled = false }) => {
  const [isRetrying, setIsRetrying] = useState(false);

  // Check if logs viewing is available (only for app crashes, not config issues)
  const canViewLogs = APP_CRASH_REASONS.includes(pod.failure_reason);

  // Check if solution is a fallback (AI unavailable)
  const isFallbackSolution = pod.solution && (
    pod.solution.includes('AI solution temporarily unavailable') ||
    pod.solution.includes('Failed to generate AI solution') ||
    pod.solution.includes('Basic troubleshooting')
  );

  const handleRetrySolution = async () => {
    setIsRetrying(true);
    try {
      const updatedPod = await api.retrySolution(pod.id);
      if (onSolutionUpdated) {
        onSolutionUpdated(updatedPod);
      }
    } catch (error) {
      console.error('Failed to retry solution:', error);
    } finally {
      setIsRetrying(false);
    }
  };
  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Get error message from various sources
  const getErrorMessage = () => {
    // Primary: pod failure message
    if (pod.failure_message && pod.failure_message.trim()) {
      return pod.failure_message;
    }
    
    // Fallback: container status message
    if (pod.container_statuses) {
      for (const container of pod.container_statuses) {
        if (container.message && container.message.trim()) {
          return container.message;
        }
      }
    }
    
    // Fallback: recent warning events
    if (pod.events) {
      const warningEvents = pod.events.filter(e => e.type === 'Warning' && e.message);
      if (warningEvents.length > 0) {
        return warningEvents[0].message;
      }
    }
    
    // Last resort: generic message
    return `Pod is in ${pod.failure_reason} state. Check events and container statuses for more details.`;
  };

  return (
    <div className="space-y-4 overflow-hidden w-full">
      {/* Pod Details */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <h4 className="font-medium text-gray-900 mb-2">Pod Details</h4>
          <dl className="space-y-1 text-sm">
            <div className="flex">
              <dt className="font-medium text-gray-600 w-24">Node:</dt>
              <dd className="text-gray-900">{pod.node_name || 'N/A'}</dd>
            </div>
            <div className="flex">
              <dt className="font-medium text-gray-600 w-24">Phase:</dt>
              <dd className="text-gray-900">{pod.phase}</dd>
            </div>
            <div className="flex">
              <dt className="font-medium text-gray-600 w-24">Created:</dt>
              <dd className="text-gray-900">{formatTimestamp(pod.creation_timestamp)}</dd>
            </div>
          </dl>
        </div>
        <div>
          <h4 className="font-medium text-gray-900 mb-2">Error Details</h4>
          <dl className="space-y-1 text-sm">
            <div className="flex">
              <dt className="font-medium text-gray-600 w-24">Reason:</dt>
              <dd className="text-gray-900">{pod.failure_reason}</dd>
            </div>
            <div>
              <dt className="font-medium text-gray-600">Message:</dt>
              <dd className="text-gray-900 text-xs bg-gray-100 p-2 rounded mt-1 break-words">
                {getErrorMessage()}
              </dd>
            </div>
          </dl>
        </div>
      </div>

      {/* Container Statuses */}
      {pod.container_statuses && pod.container_statuses.length > 0 && (
        <div>
          <h4 className="font-medium text-gray-900 mb-2">Container Status</h4>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-100">
                  <th className="px-3 py-2 text-left">Name</th>
                  <th className="px-3 py-2 text-left">Image</th>
                  <th className="px-3 py-2 text-left">State</th>
                  <th className="px-3 py-2 text-left">Restarts</th>
                </tr>
              </thead>
              <tbody>
                {pod.container_statuses.map((container, index) => (
                  <tr key={index} className="border-t border-gray-200">
                    <td className="px-3 py-2">{container.name}</td>
                    <td className="px-3 py-2 font-mono text-xs">{container.image}</td>
                    <td className="px-3 py-2">
                      <span className={`px-2 py-1 rounded text-xs ${
                        container.state === 'running' ? 'bg-green-100 text-green-800' :
                        container.state === 'waiting' ? 'bg-yellow-100 text-yellow-800' :
                        'bg-red-100 text-red-800'
                      }`}>
                        {container.state}
                      </span>
                    </td>
                    <td className="px-3 py-2">{container.restart_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Events */}
      {pod.events && pod.events.length > 0 && (
        <div>
          <h4 className="font-medium text-gray-900 mb-2">Recent Events</h4>
          <div className="space-y-2">
            {pod.events.slice(0, 3).map((event, index) => (
              <div key={index} className="flex items-start space-x-2">
                <span className={`px-2 py-1 rounded text-xs ${
                  event.type === 'Warning' ? 'bg-red-100 text-red-800' : 'bg-blue-100 text-blue-800'
                }`}>
                  {event.type}
                </span>
                <div className="flex-1">
                  <div className="text-sm font-medium">{event.reason}</div>
                  <div className="text-xs text-gray-600">{event.message}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Complete Solution */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center space-x-2">
            <h4 className="font-medium text-gray-900">AI-Generated Solution</h4>
            <button
              onClick={handleRetrySolution}
              disabled={isRetrying || !aiEnabled}
              className="inline-flex items-center px-2 py-1 text-xs font-medium text-blue-700 bg-blue-100 border border-blue-300 rounded hover:bg-blue-200 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
              title={!aiEnabled ? 'AI provider not configured' : 'Retry AI Solution'}
            >
              <RefreshCw className={`w-3 h-3 mr-1 ${isRetrying ? 'animate-spin' : ''}`} />
              {isRetrying ? 'Retrying...' : 'Retry AI'}
            </button>
          </div>
          <div className="flex items-center space-x-2">
            {canViewLogs && (
              <button
                onClick={onViewLogs}
                className="inline-flex items-center px-3 py-1 border border-green-300 rounded-md text-sm text-green-700 bg-green-50 hover:bg-green-100 focus:outline-none focus:ring-2 focus:ring-green-500"
                title="View Live Logs - See what's causing the crash"
              >
                <Terminal className="w-4 h-4 mr-2" />
                Live Logs
              </button>
            )}
            <button
              onClick={onViewManifest}
              className="inline-flex items-center px-3 py-1 border border-gray-300 rounded-md text-sm text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
              title="View Pod Manifest"
            >
              <FileText className="w-4 h-4 mr-2" />
              View Manifest
            </button>
          </div>
        </div>
        <div className={`rounded p-4 text-sm overflow-hidden ${
          isFallbackSolution
            ? 'bg-yellow-50 border border-yellow-200'
            : 'bg-blue-50 border border-blue-200'
        }`}>
          <div className="solution-content">
            <ReactMarkdown
              components={{
                // Handle pre/code blocks
                pre: ({ children }) => {
                  const codeChild = React.Children.toArray(children).find(
                    child => React.isValidElement(child) && child.type === 'code'
                  );
                  if (codeChild && React.isValidElement(codeChild)) {
                    const className = codeChild.props.className || '';
                    const language = className.replace('language-', '');
                    const codeText = String(codeChild.props.children || '').replace(/\n$/, '');
                    return <CodeBlock code={codeText} language={language} />;
                  }
                  return <pre className="bg-gray-800 text-gray-100 p-4 rounded overflow-x-auto text-xs my-3">{children}</pre>;
                },
                // Inline code as bold
                code: ({ inline, className, children }) => {
                  if (className?.startsWith('language-')) {
                    return <code className={className}>{children}</code>;
                  }
                  return <strong className="font-semibold text-gray-900">{children}</strong>;
                },
                // Style other elements
                p: ({ children }) => <p className="my-2 text-gray-700">{children}</p>,
                h1: ({ children }) => <h1 className="text-lg font-bold text-gray-900 mt-4 mb-2">{children}</h1>,
                h2: ({ children }) => <h2 className="text-base font-bold text-gray-900 mt-4 mb-2">{children}</h2>,
                h3: ({ children }) => <h3 className="text-sm font-bold text-gray-900 mt-3 mb-2">{children}</h3>,
                ul: ({ children }) => <ul className="list-disc list-inside my-2 space-y-1">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal list-inside my-2 space-y-1">{children}</ol>,
                li: ({ children }) => <li className="text-gray-700">{children}</li>,
                strong: ({ children }) => <strong className="font-semibold text-gray-900">{children}</strong>,
                a: ({ href, children }) => <a href={href} className="text-blue-600 hover:underline">{children}</a>,
              }}
            >
              {pod.solution}
            </ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PodDetails;

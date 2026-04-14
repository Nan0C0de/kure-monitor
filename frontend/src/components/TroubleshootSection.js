import React, { useState } from 'react';
import { Wand2, RefreshCw } from 'lucide-react';
import SolutionMarkdown from './SolutionMarkdown';
import { api } from '../services/api';

const ELIGIBLE_REASONS = ['CrashLoopBackOff', 'OOMKilled'];

const formatRelativeTime = (timestamp) => {
  if (!timestamp) return '';
  const then = new Date(timestamp).getTime();
  if (isNaN(then)) return '';
  const diffMs = Date.now() - then;
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 5) return 'just now';
  if (diffSec < 60) return `${diffSec} seconds ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin} minute${diffMin === 1 ? '' : 's'} ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} hour${diffHr === 1 ? '' : 's'} ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay} day${diffDay === 1 ? '' : 's'} ago`;
};

const SkeletonBars = ({ isDark }) => {
  const barColor = isDark ? 'bg-gray-700' : 'bg-gray-200';
  return (
    <div className="space-y-2" data-testid="troubleshoot-skeleton">
      <div className={`h-4 rounded animate-pulse ${barColor} w-3/4`} />
      <div className={`h-4 rounded animate-pulse ${barColor} w-full`} />
      <div className={`h-4 rounded animate-pulse ${barColor} w-5/6`} />
    </div>
  );
};

const TroubleshootSection = ({ pod, isDark = false, aiEnabled = false, onLogAwareSolutionUpdated, canWrite = true }) => {
  const [solution, setSolution] = useState(pod.log_aware_solution || null);
  const [generatedAt, setGeneratedAt] = useState(pod.log_aware_solution_generated_at || null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  // Eligibility — all three must be true
  if (pod.logs_captured !== true) return null;
  if (!ELIGIBLE_REASONS.includes(pod.failure_reason)) return null;
  if (aiEnabled !== true) return null;

  const runGenerate = async (regenerate) => {
    setError(null);
    setIsLoading(true);
    if (regenerate) {
      // Clear local solution so skeleton shows during regeneration
      setSolution(null);
    }
    try {
      const response = regenerate
        ? await api.regenerateLogAwareSolution(pod.id)
        : await api.generateLogAwareSolution(pod.id);
      setSolution(response.solution);
      setGeneratedAt(response.generated_at);
      if (onLogAwareSolutionUpdated) {
        onLogAwareSolutionUpdated(pod.id, response.solution, response.generated_at);
      }
    } catch (err) {
      console.error('Failed to generate log-aware solution:', err);
      setError("Couldn't generate. Click to retry.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleTroubleshoot = () => runGenerate(false);
  const handleRegenerate = () => runGenerate(true);

  const cardClasses = isDark
    ? 'bg-indigo-900/30 border border-indigo-700'
    : 'bg-indigo-50 border border-indigo-200';
  const badgeClasses = isDark
    ? 'bg-indigo-900/50 text-indigo-300 border-indigo-700'
    : 'bg-indigo-100 text-indigo-800 border-indigo-300';
  const troubleshootButtonClasses = isDark
    ? 'text-indigo-300 bg-indigo-900/40 border border-indigo-700 hover:bg-indigo-900/60'
    : 'text-indigo-700 bg-indigo-100 border border-indigo-300 hover:bg-indigo-200';
  const mutedTextClasses = isDark ? 'text-gray-400' : 'text-gray-500';
  const errorTextClasses = isDark ? 'text-gray-400' : 'text-gray-500';

  const showEmptyState = !solution && !isLoading;
  const showResult = !!solution && !isLoading;

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center space-x-2">
          <h4 className={`font-medium ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Log-Aware Troubleshoot</h4>
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${badgeClasses}`}
          >
            Log-aware analysis
          </span>
        </div>
        {showEmptyState && canWrite && (
          <button
            onClick={handleTroubleshoot}
            disabled={isLoading}
            className={`inline-flex items-center px-3 py-1 text-xs font-medium rounded focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed ${troubleshootButtonClasses}`}
            title="Generate a log-aware AI solution"
          >
            <Wand2 className="w-3.5 h-3.5 mr-1" />
            Troubleshoot
          </button>
        )}
        {isLoading && (
          <div className={`inline-flex items-center px-3 py-1 text-xs font-medium rounded ${troubleshootButtonClasses} opacity-75`}>
            <RefreshCw className="w-3.5 h-3.5 mr-1 animate-spin" />
            Analyzing logs…
          </div>
        )}
      </div>

      <div className={`rounded p-4 text-sm overflow-hidden ${cardClasses}`}>
        {showEmptyState && (
          <div>
            <p className={mutedTextClasses}>
              Get a deeper diagnosis based on the crashed container's logs.
            </p>
            {error && (
              <p className={`mt-2 text-xs ${errorTextClasses}`}>
                {error}
              </p>
            )}
          </div>
        )}

        {isLoading && <SkeletonBars isDark={isDark} />}

        {showResult && (
          <>
            <div className="solution-content">
              <SolutionMarkdown content={solution} isDark={isDark} />
            </div>
            <div className="flex items-center justify-between mt-3">
              {generatedAt ? (
                <span className={`text-xs ${mutedTextClasses}`}>
                  Generated {formatRelativeTime(generatedAt)}
                </span>
              ) : <span />}
              {canWrite && (
              <button
                onClick={handleRegenerate}
                disabled={isLoading}
                className={`inline-flex items-center px-3 py-1 text-xs font-medium rounded focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed ${troubleshootButtonClasses}`}
                title="Regenerate log-aware solution"
              >
                <RefreshCw className="w-3.5 h-3.5 mr-1" />
                Regenerate
              </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default TroubleshootSection;

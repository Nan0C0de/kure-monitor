import React, { useState, useEffect } from 'react';
import { Clock, EyeOff, Save } from 'lucide-react';
import { api } from '../../services/api';

const toMinutes = (value, unit) => {
  switch (unit) {
    case 'minutes': return value;
    case 'hours': return value * 60;
    case 'days': return value * 1440;
    default: return value;
  }
};

const getMaxValue = (unit) => {
  switch (unit) {
    case 'minutes': return 43200;
    case 'hours': return 720;
    case 'days': return 30;
    default: return 43200;
  }
};

const RetentionSettings = ({ isDark, onError, onSuccess }) => {
  // History retention state (stored as minutes in backend)
  const [retentionEnabled, setRetentionEnabled] = useState(false);
  const [retentionValue, setRetentionValue] = useState(7);
  const [retentionUnit, setRetentionUnit] = useState('days');
  const [retentionDirty, setRetentionDirty] = useState(false);

  // Ignored retention state (stored as minutes in backend)
  const [ignoredRetentionEnabled, setIgnoredRetentionEnabled] = useState(false);
  const [ignoredRetentionValue, setIgnoredRetentionValue] = useState(7);
  const [ignoredRetentionUnit, setIgnoredRetentionUnit] = useState('days');
  const [ignoredRetentionDirty, setIgnoredRetentionDirty] = useState(false);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [retentionData, ignoredRetentionData] = await Promise.all([
          api.getHistoryRetention().catch(() => ({ minutes: 0 })),
          api.getIgnoredRetention().catch(() => ({ minutes: 0 }))
        ]);

        const mins = retentionData.minutes || 0;
        if (mins > 0) {
          setRetentionEnabled(true);
          if (mins % 1440 === 0) {
            setRetentionValue(mins / 1440);
            setRetentionUnit('days');
          } else if (mins % 60 === 0) {
            setRetentionValue(mins / 60);
            setRetentionUnit('hours');
          } else {
            setRetentionValue(mins);
            setRetentionUnit('minutes');
          }
        } else {
          setRetentionEnabled(false);
          setRetentionValue(7);
          setRetentionUnit('days');
        }

        const ignoredMins = ignoredRetentionData.minutes || 0;
        if (ignoredMins > 0) {
          setIgnoredRetentionEnabled(true);
          if (ignoredMins % 1440 === 0) {
            setIgnoredRetentionValue(ignoredMins / 1440);
            setIgnoredRetentionUnit('days');
          } else if (ignoredMins % 60 === 0) {
            setIgnoredRetentionValue(ignoredMins / 60);
            setIgnoredRetentionUnit('hours');
          } else {
            setIgnoredRetentionValue(ignoredMins);
            setIgnoredRetentionUnit('minutes');
          }
        } else {
          setIgnoredRetentionEnabled(false);
          setIgnoredRetentionValue(7);
          setIgnoredRetentionUnit('days');
        }

        setRetentionDirty(false);
        setIgnoredRetentionDirty(false);
      } catch (err) {
        onError('Failed to load retention settings');
        console.error('Error loading retention settings:', err);
      }
    };
    loadData();
  }, [onError]);

  const handleRetentionSave = async (enabled, value, unit) => {
    try {
      const minutes = enabled ? toMinutes(value, unit) : 0;
      if (enabled && (minutes < 1 || minutes > 43200)) {
        onError('Retention must be between 1 minute and 30 days');
        return;
      }
      await api.setHistoryRetention(minutes);
      if (!enabled) {
        onSuccess('History auto-delete disabled.');
      } else {
        onSuccess(`Resolved pods will be auto-deleted after ${value} ${unit}.`);
      }
    } catch (err) {
      onError('Failed to update retention setting');
      console.error('Error updating retention:', err);
    }
  };

  const handleIgnoredRetentionSave = async (enabled, value, unit) => {
    try {
      const minutes = enabled ? toMinutes(value, unit) : 0;
      if (enabled && (minutes < 1 || minutes > 43200)) {
        onError('Retention must be between 1 minute and 30 days');
        return;
      }
      await api.setIgnoredRetention(minutes);
      if (!enabled) {
        onSuccess('Ignored pods auto-delete disabled.');
      } else {
        onSuccess(`Ignored pods will be auto-deleted after ${value} ${unit}.`);
      }
    } catch (err) {
      onError('Failed to update ignored retention setting');
      console.error('Error updating ignored retention:', err);
    }
  };

  return (
    <div className="space-y-8">
      {/* History Retention */}
      <div>
        <div className="mb-4 flex items-center">
          <Clock className="w-5 h-5 text-green-500 mr-2" />
          <h2 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>History Retention</h2>
        </div>
        <p className={`text-sm mb-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
          Automatically delete resolved pods from history after a set period. Ignored pods are not affected by this setting.
        </p>

        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={retentionEnabled}
              onChange={(e) => {
                const enabled = e.target.checked;
                setRetentionEnabled(enabled);
                if (!enabled) {
                  handleRetentionSave(false, retentionValue, retentionUnit);
                  setRetentionDirty(false);
                } else {
                  setRetentionDirty(true);
                }
              }}
              className="h-4 w-4 text-green-600 rounded border-gray-300 focus:ring-green-500"
            />
            <span className={`text-sm font-medium ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              Auto-delete resolved pods after
            </span>
          </label>

          <input
            type="number"
            min={1}
            max={getMaxValue(retentionUnit)}
            value={retentionValue}
            disabled={!retentionEnabled}
            onChange={(e) => {
              const val = parseInt(e.target.value) || 1;
              setRetentionValue(val);
              setRetentionDirty(true);
            }}
            onBlur={() => {
              const clamped = Math.max(1, Math.min(retentionValue, getMaxValue(retentionUnit)));
              setRetentionValue(clamped);
            }}
            className={`w-20 px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-green-500 disabled:opacity-50 ${
              isDark ? 'bg-gray-700 border-gray-600 text-gray-200' : 'bg-white border-gray-300 text-gray-900'
            }`}
          />

          <select
            value={retentionUnit}
            disabled={!retentionEnabled}
            onChange={(e) => {
              const newUnit = e.target.value;
              const maxVal = newUnit === 'minutes' ? 43200 : newUnit === 'hours' ? 720 : 30;
              const clamped = Math.min(retentionValue, maxVal);
              setRetentionUnit(newUnit);
              setRetentionValue(clamped);
              setRetentionDirty(true);
            }}
            className={`px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-green-500 disabled:opacity-50 ${
              isDark ? 'bg-gray-700 border-gray-600 text-gray-200' : 'bg-white border-gray-300 text-gray-900'
            }`}
          >
            <option value="minutes">minutes</option>
            <option value="hours">hours</option>
            <option value="days">days</option>
          </select>

          {retentionEnabled && retentionDirty && (
            <button
              onClick={() => {
                const clamped = Math.max(1, Math.min(retentionValue, getMaxValue(retentionUnit)));
                setRetentionValue(clamped);
                handleRetentionSave(true, clamped, retentionUnit);
                setRetentionDirty(false);
              }}
              className="inline-flex items-center px-3 py-2 text-sm font-medium text-white bg-green-600 border border-transparent rounded-md shadow-sm hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500"
            >
              <Save className="w-4 h-4 mr-1" />
              Save
            </button>
          )}
        </div>

        {retentionEnabled && (
          <div className={`mt-3 text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
            The cleanup runs every minute. Resolved pods older than the configured period will be permanently deleted.
          </div>
        )}
      </div>

      {/* Ignored Pods Retention */}
      <div>
        <div className="mb-4 flex items-center">
          <EyeOff className="w-5 h-5 text-gray-500 mr-2" />
          <h2 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Ignored Pods Retention</h2>
        </div>
        <p className={`text-sm mb-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
          Automatically delete ignored pods after a set period.
        </p>

        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={ignoredRetentionEnabled}
              onChange={(e) => {
                const enabled = e.target.checked;
                setIgnoredRetentionEnabled(enabled);
                if (!enabled) {
                  handleIgnoredRetentionSave(false, ignoredRetentionValue, ignoredRetentionUnit);
                  setIgnoredRetentionDirty(false);
                } else {
                  setIgnoredRetentionDirty(true);
                }
              }}
              className="h-4 w-4 text-gray-600 rounded border-gray-300 focus:ring-gray-500"
            />
            <span className={`text-sm font-medium ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              Auto-delete ignored pods after
            </span>
          </label>

          <input
            type="number"
            min={1}
            max={getMaxValue(ignoredRetentionUnit)}
            value={ignoredRetentionValue}
            disabled={!ignoredRetentionEnabled}
            onChange={(e) => {
              const val = parseInt(e.target.value) || 1;
              setIgnoredRetentionValue(val);
              setIgnoredRetentionDirty(true);
            }}
            onBlur={() => {
              const clamped = Math.max(1, Math.min(ignoredRetentionValue, getMaxValue(ignoredRetentionUnit)));
              setIgnoredRetentionValue(clamped);
            }}
            className={`w-20 px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-gray-500 focus:border-gray-500 disabled:opacity-50 ${
              isDark ? 'bg-gray-700 border-gray-600 text-gray-200' : 'bg-white border-gray-300 text-gray-900'
            }`}
          />

          <select
            value={ignoredRetentionUnit}
            disabled={!ignoredRetentionEnabled}
            onChange={(e) => {
              const newUnit = e.target.value;
              const maxVal = newUnit === 'minutes' ? 43200 : newUnit === 'hours' ? 720 : 30;
              const clamped = Math.min(ignoredRetentionValue, maxVal);
              setIgnoredRetentionUnit(newUnit);
              setIgnoredRetentionValue(clamped);
              setIgnoredRetentionDirty(true);
            }}
            className={`px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-gray-500 focus:border-gray-500 disabled:opacity-50 ${
              isDark ? 'bg-gray-700 border-gray-600 text-gray-200' : 'bg-white border-gray-300 text-gray-900'
            }`}
          >
            <option value="minutes">minutes</option>
            <option value="hours">hours</option>
            <option value="days">days</option>
          </select>

          {ignoredRetentionEnabled && ignoredRetentionDirty && (
            <button
              onClick={() => {
                const clamped = Math.max(1, Math.min(ignoredRetentionValue, getMaxValue(ignoredRetentionUnit)));
                setIgnoredRetentionValue(clamped);
                handleIgnoredRetentionSave(true, clamped, ignoredRetentionUnit);
                setIgnoredRetentionDirty(false);
              }}
              className="inline-flex items-center px-3 py-2 text-sm font-medium text-white bg-green-600 border border-transparent rounded-md shadow-sm hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500"
            >
              <Save className="w-4 h-4 mr-1" />
              Save
            </button>
          )}
        </div>

        {ignoredRetentionEnabled && (
          <div className={`mt-3 text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
            The cleanup runs every minute. Ignored pods older than the configured period will be permanently deleted.
          </div>
        )}
      </div>
    </div>
  );
};

export default RetentionSettings;

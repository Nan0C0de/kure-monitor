import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';
import {
  Box,
  Layers,
  Server,
  Network,
  Globe,
  Settings as SettingsIcon,
  Lock,
  Database,
  User,
  Users,
  TrendingUp,
  Shield,
  ShieldCheck,
  Key,
  Link as LinkIcon,
  RefreshCw,
  Calendar,
  Briefcase,
  HelpCircle,
} from 'lucide-react';

const KIND_STYLE = {
  Deployment:              { icon: Layers,       light: 'bg-blue-50 border-blue-300 text-blue-900',           dark: 'bg-blue-900/40 border-blue-700 text-blue-100' },
  StatefulSet:             { icon: Layers,       light: 'bg-blue-50 border-blue-300 text-blue-900',     dark: 'bg-blue-900/40 border-blue-700 text-blue-100' },
  DaemonSet:               { icon: Layers,       light: 'bg-cyan-50 border-cyan-300 text-cyan-900',           dark: 'bg-cyan-900/40 border-cyan-700 text-cyan-100' },
  ReplicaSet:              { icon: RefreshCw,    light: 'bg-sky-50 border-sky-300 text-sky-900',              dark: 'bg-sky-900/40 border-sky-700 text-sky-100' },
  Pod:                     { icon: Box,          light: 'bg-emerald-50 border-emerald-300 text-emerald-900',  dark: 'bg-emerald-900/40 border-emerald-700 text-emerald-100' },
  Service:                 { icon: Server,       light: 'bg-blue-50 border-blue-300 text-blue-900',     dark: 'bg-blue-900/40 border-blue-700 text-blue-100' },
  Endpoints:               { icon: Network,      light: 'bg-blue-50 border-blue-200 text-blue-800',     dark: 'bg-blue-900/30 border-blue-800 text-blue-200' },
  EndpointSlice:           { icon: Network,      light: 'bg-blue-50 border-blue-200 text-blue-800',     dark: 'bg-blue-900/30 border-blue-800 text-blue-200' },
  Ingress:                 { icon: Globe,        light: 'bg-rose-50 border-rose-300 text-rose-900',           dark: 'bg-rose-900/40 border-rose-700 text-rose-100' },
  ConfigMap:               { icon: SettingsIcon, light: 'bg-yellow-50 border-yellow-300 text-yellow-900',        dark: 'bg-yellow-900/40 border-yellow-700 text-yellow-100' },
  Secret:                  { icon: Lock,         light: 'bg-yellow-50 border-yellow-400 text-yellow-900',     dark: 'bg-yellow-900/40 border-yellow-600 text-yellow-100' },
  PersistentVolumeClaim:   { icon: Database,     light: 'bg-teal-50 border-teal-300 text-teal-900',           dark: 'bg-teal-900/40 border-teal-700 text-teal-100' },
  ServiceAccount:          { icon: User,         light: 'bg-blue-50 border-blue-300 text-blue-900',  dark: 'bg-blue-900/40 border-blue-700 text-blue-100' },
  HorizontalPodAutoscaler: { icon: TrendingUp,   light: 'bg-green-50 border-green-300 text-green-900',        dark: 'bg-green-900/40 border-green-700 text-green-100' },
  NetworkPolicy:           { icon: Shield,       light: 'bg-red-50 border-red-300 text-red-900',     dark: 'bg-red-900/40 border-red-700 text-red-100' },
  Job:                     { icon: Briefcase,    light: 'bg-slate-50 border-slate-300 text-slate-900',        dark: 'bg-slate-800/60 border-slate-600 text-slate-100' },
  CronJob:                 { icon: Calendar,     light: 'bg-stone-50 border-stone-300 text-stone-900',        dark: 'bg-stone-800/60 border-stone-600 text-stone-100' },
  // RBAC kinds
  Role:                    { icon: ShieldCheck,  light: 'bg-yellow-50 border-yellow-400 text-yellow-900',        dark: 'bg-yellow-900/40 border-yellow-600 text-yellow-100' },
  ClusterRole:             { icon: ShieldCheck,  light: 'bg-yellow-100 border-yellow-500 text-yellow-900',       dark: 'bg-yellow-800/50 border-yellow-500 text-yellow-50' },
  RoleBinding:             { icon: LinkIcon,     light: 'bg-blue-50 border-blue-300 text-blue-900',     dark: 'bg-blue-900/40 border-blue-700 text-blue-100' },
  ClusterRoleBinding:      { icon: LinkIcon,     light: 'bg-blue-100 border-blue-400 text-blue-900',    dark: 'bg-blue-800/50 border-blue-500 text-blue-50' },
  'Subject:User':          { icon: User,         light: 'bg-slate-50 border-slate-300 text-slate-900',        dark: 'bg-slate-800/60 border-slate-600 text-slate-100' },
  'Subject:Group':         { icon: Users,        light: 'bg-slate-100 border-slate-400 text-slate-900',       dark: 'bg-slate-700/60 border-slate-500 text-slate-50' },
  Permission:              { icon: Key,          light: 'bg-neutral-50 border-neutral-300 text-neutral-900',  dark: 'bg-neutral-800/60 border-neutral-600 text-neutral-100' },
};

const DEFAULT_STYLE = { icon: HelpCircle, light: 'bg-gray-50 border-gray-300 text-gray-900', dark: 'bg-gray-800 border-gray-600 text-gray-100' };

const buildTooltip = (data) => {
  const lines = [`${data.kind}: ${data.namespace}/${data.name}`];
  if (data.status) lines.push(`Status: ${data.status}`);
  const md = data.metadata || {};
  if (md.image) lines.push(`Image: ${md.image}`);
  if (md.replicas) lines.push(`Replicas: ${md.replicas}`);
  if (md.derived) lines.push('Derived (no read access)');
  if (typeof md.nps_count === 'number' && md.nps_count > 0) {
    lines.push(`NetworkPolicies selecting this: ${md.nps_count}`);
  }
  return lines.join('\n');
};

const ResourceNode = memo(({ data }) => {
  const style = KIND_STYLE[data.kind] || DEFAULT_STYLE;
  const Icon = style.icon;
  const themeClasses = data.isDark ? style.dark : style.light;
  const npsCount = data.metadata?.nps_count || 0;
  const derived = data.metadata?.derived === true;

  return (
    <div
      title={buildTooltip(data)}
      className={`relative rounded-sm border-2 shadow-sm px-3 py-2 min-w-[170px] max-w-[240px] ${themeClasses} ${
        derived ? 'border-dashed' : ''
      }`}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#94a3b8', width: 6, height: 6 }} />
      <div className="flex items-start space-x-2">
        <Icon className="w-4 h-4 mt-0.5 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="text-[10px] uppercase tracking-wide opacity-70 leading-tight">
            {data.kind}
          </div>
          <div className="text-xs font-semibold truncate leading-tight" title={data.name}>
            {data.name}
          </div>
          {data.status && (
            <div className="text-[10px] opacity-80 truncate leading-tight">
              {data.status}
            </div>
          )}
        </div>
        {npsCount > 0 && (
          <span
            className={`flex items-center space-x-0.5 text-[10px] font-medium px-1.5 py-0.5 rounded border ${
              data.isDark
                ? 'bg-red-900/50 border-red-700 text-red-200'
                : 'bg-red-100 border-red-300 text-red-800'
            }`}
            title={`${npsCount} NetworkPolic${npsCount === 1 ? 'y' : 'ies'} select this resource`}
          >
            <Shield className="w-3 h-3" />
            <span>{npsCount}</span>
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} style={{ background: '#94a3b8', width: 6, height: 6 }} />
    </div>
  );
});

const CollapsedGroupNode = memo(({ data }) => {
  return (
    <div
      onClick={data.onExpand}
      className={`cursor-pointer rounded-sm border-2 border-dashed shadow-sm px-4 py-3 min-w-[180px] text-center ${
        data.isDark
          ? 'bg-gray-800 border-gray-500 text-gray-100 hover:bg-gray-700'
          : 'bg-gray-100 border-gray-400 text-gray-900 hover:bg-gray-200'
      }`}
      title="Click to expand group"
    >
      <Handle type="target" position={Position.Top} style={{ background: '#94a3b8', width: 6, height: 6 }} />
      <div className="text-[10px] uppercase tracking-wide opacity-70">Group (collapsed)</div>
      <div className="text-sm font-semibold truncate">{data.label}</div>
      <div className="text-xs opacity-80 mt-1">{data.count} resource{data.count === 1 ? '' : 's'}</div>
      <Handle type="source" position={Position.Bottom} style={{ background: '#94a3b8', width: 6, height: 6 }} />
    </div>
  );
});

ResourceNode.displayName = 'ResourceNode';
CollapsedGroupNode.displayName = 'CollapsedGroupNode';

export const nodeTypes = {
  resource: ResourceNode,
  collapsedGroup: CollapsedGroupNode,
};

export default nodeTypes;

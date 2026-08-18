export const api = {
  getAuthMe: async () => ({ username: 'demo', role: 'admin' }),
  getConfig: async () => ({ pod_monitoring: true, security_scan: true, diagram: true, ai_advice: true, ai_enabled: true }),
  
  // Pods
  getFailedPods: async () => ([
    {
      id: 1,
      pod_name: 'inventory-sync-deployment-5f9b4c8d-x7qz9',
      namespace: 'production',
      node_name: 'kure-monitor-worker2',
      phase: 'Running',
      failure_reason: 'CrashLoopBackOff',
      status: 'investigating',
      timestamp: new Date().toISOString(),
      solution: `The container \`inventory-sync\` is crashing on startup with an HTTP 401 Unauthorized error when attempting to connect to the upstream inventory service at \`http://inventory-service.default.svc\`.

**Root Cause:** The pod is missing the \`API_TOKEN\` environment variable required for authenticating against the upstream API. Without a valid token, the service receives a 401 response and terminates.

**Recommended Fix:** Add the \`API_TOKEN\` environment variable to the container spec, referencing a Kubernetes Secret that holds the authentication token. Create the secret with:

\`\`\`bash
kubectl create secret generic api-auth-secret --from-literal=token=<your-token> -n production
\`\`\`

Then update the Deployment manifest to inject the secret as an environment variable into the container.`,
      manifest: `apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-sync
  namespace: production
  labels:
    app: inventory-sync
spec:
  replicas: 2
  selector:
    matchLabels:
      app: inventory-sync
  template:
    metadata:
      labels:
        app: inventory-sync
    spec:
      containers:
      - name: inventory-sync
        image: myregistry.io/inventory-sync:v2.1.0
        ports:
        - containerPort: 8080
        env:
        - name: UPSTREAM_API_URL
          value: "http://inventory-service.default.svc"
        - name: API_TOKEN
          valueFrom:
            secretKeyRef:
              name: api-auth-secret
              key: token
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 250m
            memory: 256Mi
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 15
      restartPolicy: Always`,
      container_statuses: [{ name: 'inventory-sync', state: 'waiting', message: 'back-off 5m0s restarting failed container=inventory-sync' }],
      events: [
        { type: "Normal", reason: "Pulling", message: "Pulling image \"myregistry.io/inventory-sync:v2.1.0\"", timestamp: new Date(Date.now() - 3600000).toISOString() },
        { type: "Normal", reason: "Pulled", message: "Successfully pulled image \"myregistry.io/inventory-sync:v2.1.0\"", timestamp: new Date(Date.now() - 3580000).toISOString() },
        { type: "Warning", reason: "BackOff", message: "Back-off restarting failed container inventory-sync", timestamp: new Date(Date.now() - 3500000).toISOString() }
      ],
      logs: `[INFO] Starting inventory sync service v2.1.0...
[INFO] Loading configuration from environment...
[INFO] Attempting to connect to upstream API at http://inventory-service.default.svc...
[ERROR] Request failed! HTTP Status 401 Unauthorized
[ERROR] The authentication token provided is either missing or invalid.
[ERROR] Sync aborted. Process terminating.`
    }
  ]),
  getPodHistory: async () => ([]),
  getIgnoredPods: async () => ([]),
  getHistoryRetention: async () => ({ minutes: 10080 }),
  getIgnoredRetention: async () => ({ minutes: 10080 }),
  updatePodStatus: async (id, status) => ({ id, status }),
  deletePodRecord: async () => ({}),
  retrySolution: async (podId) => {
    return {
      id: podId,
      solution: 'This is a retried solution. Ensure your configurations are correct.',
      timestamp: new Date().toISOString()
    };
  },

  // Mirror Pods
  _mirrorPollCount: 0,
  previewMirrorPod: async (podId) => ({
    fixed_manifest: `apiVersion: v1
kind: Pod
metadata:
  name: mirror-test-inventory-sync
  namespace: production
  labels:
    app: inventory-sync
    kure-mirror: "true"
spec:
  containers:
  - name: inventory-sync
    image: myregistry.io/inventory-sync:v2.1.0
    ports:
    - containerPort: 8080
    env:
    - name: UPSTREAM_API_URL
      value: "http://inventory-service.default.svc"
    - name: API_TOKEN
      valueFrom:
        secretKeyRef:
          name: api-auth-secret
          key: token
    resources:
      requests:
        cpu: 100m
        memory: 128Mi
      limits:
        cpu: 250m
        memory: 256Mi
  restartPolicy: Never`,
    explanation: 'Added the missing API_TOKEN environment variable from the api-auth-secret Secret. The mirror pod uses restartPolicy: Never so it terminates cleanly after the test.'
  }),
  deployMirrorPod: async (podId, ttl, manifest) => {
    api._mirrorPollCount = 0;
    return {
      mirror_id: `mirror-${podId}`,
      mirror_pod_name: `mirror-test-inventory-sync`,
      namespace: 'production',
      phase: 'Pending',
      status: 'pending',
      created_at: new Date().toISOString(),
      ttl_seconds: ttl || 180,
      events: [
        { type: 'Normal', reason: 'Scheduled', message: 'Successfully assigned production/mirror-test-inventory-sync to kure-monitor-worker2' }
      ]
    };
  },
  getMirrorStatus: async (mirrorId) => {
    api._mirrorPollCount = (api._mirrorPollCount || 0) + 1;
    if (api._mirrorPollCount <= 1) {
      return {
        mirror_id: mirrorId,
        mirror_pod_name: 'mirror-test-inventory-sync',
        namespace: 'production',
        phase: 'Pending',
        events: [
          { type: 'Normal', reason: 'Scheduled', message: 'Successfully assigned production/mirror-test-inventory-sync to kure-monitor-worker2' },
          { type: 'Normal', reason: 'Pulling', message: 'Pulling image "myregistry.io/inventory-sync:v2.1.0"' }
        ]
      };
    }
    return {
      mirror_id: mirrorId,
      mirror_pod_name: 'mirror-test-inventory-sync',
      namespace: 'production',
      phase: 'Running',
      events: [
        { type: 'Normal', reason: 'Scheduled', message: 'Successfully assigned production/mirror-test-inventory-sync to kure-monitor-worker2' },
        { type: 'Normal', reason: 'Pulling', message: 'Pulling image "myregistry.io/inventory-sync:v2.1.0"' },
        { type: 'Normal', reason: 'Pulled', message: 'Successfully pulled image "myregistry.io/inventory-sync:v2.1.0"' },
        { type: 'Normal', reason: 'Created', message: 'Created container inventory-sync' },
        { type: 'Normal', reason: 'Started', message: 'Started container inventory-sync' }
      ]
    };
  },
  deleteMirrorPod: async (mirrorId) => ({ success: true }),

  getPodLogs: async (namespace, podName) => {
    return {
      logs: `2026-08-17T10:05:10Z INFO [payment-service] Starting service...
2026-08-17T10:05:11Z INFO [payment-service] Connecting to database at db.internal:5432
2026-08-17T10:05:12Z FATAL [payment-service] Cannot read property "password" of undefined
2026-08-17T10:05:12Z INFO [payment-service] Exiting...`
    };
  },
  getStreamingLogsUrl: () => null, // Just ignore streaming for demo

  // Security
  getSecurityFindings: async () => ([
    {
      id: 1,
      resource_kind: 'Deployment',
      resource_name: 'payment-service',
      namespace: 'production',
      severity: 'critical',
      rule_id: 'KSV013',
      title: 'Container is privileged',
      description: 'Container is running as privileged which can compromise the host.',
      timestamp: new Date().toISOString()
    }
  ]),
  getSecurityFindingManifest: async () => ({
    manifest: `apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
  namespace: production
  labels:
    app: payment-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: payment-service
  template:
    metadata:
      labels:
        app: payment-service
    spec:
      containers:
      - name: payment-service
        image: myregistry.io/payment-service:v1.2.3
        ports:
        - containerPort: 8080
        securityContext:
          privileged: true
        resources:
          requests:
            cpu: 200m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi`,
    solution: `The container is running in privileged mode, which grants it full access to the host's devices and breaks container isolation. This is a critical security risk. Disable privileged mode and add explicit security hardening.`
  }),
  generateSecurityFix: async () => ({
    diff: [
      { type: 'context', content: 'apiVersion: apps/v1' },
      { type: 'context', content: 'kind: Deployment' },
      { type: 'context', content: 'metadata:' },
      { type: 'context', content: '  name: payment-service' },
      { type: 'context', content: '  namespace: production' },
      { type: 'context', content: '  labels:' },
      { type: 'context', content: '    app: payment-service' },
      { type: 'context', content: 'spec:' },
      { type: 'context', content: '  replicas: 3' },
      { type: 'context', content: '  selector:' },
      { type: 'context', content: '    matchLabels:' },
      { type: 'context', content: '      app: payment-service' },
      { type: 'context', content: '  template:' },
      { type: 'context', content: '    metadata:' },
      { type: 'context', content: '      labels:' },
      { type: 'context', content: '        app: payment-service' },
      { type: 'context', content: '    spec:' },
      { type: 'context', content: '      containers:' },
      { type: 'context', content: '      - name: payment-service' },
      { type: 'context', content: '        image: myregistry.io/payment-service:v1.2.3' },
      { type: 'context', content: '        ports:' },
      { type: 'context', content: '        - containerPort: 8080' },
      { type: 'context', content: '        securityContext:' },
      { type: 'removed', content: '          privileged: true' },
      { type: 'added', content: '          # Fix: Disable privileged mode to maintain container isolation' },
      { type: 'added', content: '          privileged: false' },
      { type: 'added', content: '          # Fix: explicitly prevent privilege escalation' },
      { type: 'added', content: '          allowPrivilegeEscalation: false' },
      { type: 'added', content: '          # Fix: enforce running as a non-root user' },
      { type: 'added', content: '          runAsNonRoot: true' },
      { type: 'added', content: '          # Fix: prevent modifications to the container filesystem' },
      { type: 'added', content: '          readOnlyRootFilesystem: true' },
      { type: 'context', content: '        resources:' },
      { type: 'context', content: '          requests:' },
      { type: 'context', content: '            cpu: 200m' },
      { type: 'context', content: '            memory: 256Mi' },
      { type: 'context', content: '          limits:' },
      { type: 'context', content: '            cpu: 500m' },
      { type: 'context', content: '            memory: 512Mi' },
    ],
    fixed_manifest: `apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
  namespace: production
  labels:
    app: payment-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: payment-service
  template:
    metadata:
      labels:
        app: payment-service
    spec:
      containers:
      - name: payment-service
        image: myregistry.io/payment-service:v1.2.3
        ports:
        - containerPort: 8080
        securityContext:
          privileged: false
          allowPrivilegeEscalation: false
          runAsNonRoot: true
          readOnlyRootFilesystem: true
        resources:
          requests:
            cpu: 200m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi`,
    explanation: "The container is running in privileged mode, which grants it full access to the host's devices and breaks container isolation. The fix disables privileged mode, prevents privilege escalation, enforces running as a non-root user, and sets the root filesystem to read-only."
  }),

  // Diagram
  getDiagramNamespaces: async () => ({ namespaces: ['production', 'database', 'default'] }),
  getDiagramWorkloads: async (namespace, kind) => {
    if (kind === 'Deployment') return { workloads: ['frontend', 'payment-service'] };
    if (kind === 'StatefulSet') return { workloads: ['redis-cache'] };
    return { workloads: [] };
  },
  getDiagramNamespace: async (namespace) => ({
    scope: 'namespace',
    root_id: null,
    nodes: [
      { id: 'ing-1', kind: 'Ingress', name: 'frontend-ingress', namespace, status: 'healthy' },
      { id: 'svc-1', kind: 'Service', name: 'frontend-svc', namespace, status: 'healthy' },
      { id: 'dep-1', kind: 'Deployment', name: 'frontend', namespace, status: 'healthy', metadata: { replicas: 2 } },
      { id: 'rs-1', kind: 'ReplicaSet', name: 'frontend-7d9b', namespace },
      { id: 'pod-1', kind: 'Pod', name: 'frontend-7d9b-x1', namespace, status: 'Running' },
      { id: 'pod-2', kind: 'Pod', name: 'frontend-7d9b-y2', namespace, status: 'Running' },
      
      { id: 'svc-2', kind: 'Service', name: 'payment-svc', namespace, status: 'healthy' },
      { id: 'dep-2', kind: 'Deployment', name: 'payment-service', namespace, status: 'degraded', metadata: { replicas: 1 } },
      { id: 'rs-2', kind: 'ReplicaSet', name: 'payment-5c4a', namespace },
      { id: 'pod-3', kind: 'Pod', name: 'payment-5c4a-z1', namespace, status: 'CrashLoopBackOff' },

      { id: 'svc-3', kind: 'Service', name: 'redis-svc', namespace: 'database', status: 'healthy' },
      { id: 'sts-1', kind: 'StatefulSet', name: 'redis-cache', namespace: 'database', status: 'healthy' },
      { id: 'pod-4', kind: 'Pod', name: 'redis-cache-0', namespace: 'database', status: 'Running' },
    ],
    edges: [
      { source: 'ing-1', target: 'svc-1', type: 'routes' },
      { source: 'svc-1', target: 'pod-1', type: 'selects' },
      { source: 'svc-1', target: 'pod-2', type: 'selects' },
      { source: 'dep-1', target: 'rs-1', type: 'owns' },
      { source: 'rs-1', target: 'pod-1', type: 'owns' },
      { source: 'rs-1', target: 'pod-2', type: 'owns' },
      
      { source: 'pod-1', target: 'svc-2', type: 'network' },
      { source: 'pod-2', target: 'svc-2', type: 'network' },
      { source: 'svc-2', target: 'pod-3', type: 'selects' },
      { source: 'dep-2', target: 'rs-2', type: 'owns' },
      { source: 'rs-2', target: 'pod-3', type: 'owns' },

      { source: 'pod-3', target: 'svc-3', type: 'network' },
      { source: 'svc-3', target: 'pod-4', type: 'selects' },
      { source: 'sts-1', target: 'pod-4', type: 'owns' },
    ],
    groups: [
      { id: 'g-frontend', label: 'Frontend App', node_ids: ['dep-1', 'rs-1', 'pod-1', 'pod-2'] },
      { id: 'g-payment', label: 'Payment API', node_ids: ['dep-2', 'rs-2', 'pod-3'] },
      { id: 'g-redis', label: 'Redis Cache', node_ids: ['sts-1', 'pod-4'] }
    ]
  }),
  getDiagramWorkload: async (namespace, kind, name) => {
    const data = await api.getDiagramNamespace(namespace);
    data.scope = 'workload';
    return data;
  },
  getDiagramRoles: async () => ({
    roles: [
      { namespace: 'production', name: 'app-reader' },
      { namespace: 'database', name: 'db-admin' }
    ],
    cluster_roles: [
      { name: 'cluster-admin' },
      { name: 'view' }
    ]
  }),
  getDiagramRole: async (namespace, name) => ({
    scope: 'role',
    nodes: [
      { id: 'role-1', kind: 'Role', name, namespace },
      { id: 'sa-1', kind: 'ServiceAccount', name: 'default', namespace },
      { id: 'rb-1', kind: 'RoleBinding', name: `${name}-binding`, namespace }
    ],
    edges: [
      { source: 'rb-1', target: 'role-1', type: 'references' },
      { source: 'rb-1', target: 'sa-1', type: 'binds' }
    ],
    groups: []
  }),
  getDiagramClusterRole: async (name) => ({
    scope: 'cluster-role',
    nodes: [
      { id: 'cr-1', kind: 'ClusterRole', name },
      { id: 'user-1', kind: 'User', name: 'admin@company.com' },
      { id: 'crb-1', kind: 'ClusterRoleBinding', name: `${name}-binding` }
    ],
    edges: [
      { source: 'crb-1', target: 'cr-1', type: 'references' },
      { source: 'crb-1', target: 'user-1', type: 'binds' }
    ],
    groups: []
  }),
  
  // Advice
  getAdviceFindings: async (params = {}) => {
    const mockFindings = [
      {
        id: 'adv-1',
        detector_id: 'deployment-should-be-daemonset',
        severity: 'high',
        category: 'workload-pattern',
        title: 'Deployment resembles a DaemonSet pattern',
        summary: 'This Deployment is scheduled on every single node using node anti-affinity. This is an anti-pattern; DaemonSets are designed specifically for this use case.',
        resource_kind: 'Deployment',
        resource_name: 'log-forwarder',
        namespace: 'kube-system',
        evidence: {
          pod_anti_affinity_used: true,
          topology_key: 'kubernetes.io/hostname',
          replicas: 10,
          total_cluster_nodes: 10
        },
        recommended_change: 'Convert this Deployment into a DaemonSet. Remove the replicas field and the podAntiAffinity scheduling rules.',
        confidence: 0.95,
        explanation: 'The Kubernetes scheduler is currently being forced to place exactly one replica of `log-forwarder` on every node using complex anti-affinity rules. A DaemonSet inherently guarantees exactly one pod per matching node, which is much more efficient for the scheduler, natively handles nodes joining/leaving the cluster, and eliminates the need to manually manage replica counts.',
        timestamp: new Date().toISOString(),
        dismissed: false
      },
      {
        id: 'adv-2',
        detector_id: 'missing-liveness-probe',
        severity: 'medium',
        category: 'reliability',
        title: 'Missing liveness probe',
        summary: 'The frontend deployment is missing a liveness probe, which means Kubernetes cannot automatically restart it if it hangs.',
        resource_kind: 'Deployment',
        resource_name: 'frontend',
        namespace: 'production',
        evidence: {
          containers_without_liveness: ['nginx']
        },
        recommended_change: 'Add a livenessProbe to the nginx container definition, for example probing the /healthz endpoint.',
        confidence: 0.85,
        timestamp: new Date().toISOString(),
        dismissed: false
      },
      {
        id: 'adv-3',
        detector_id: 'over-provisioned-cpu',
        severity: 'low',
        category: 'efficiency',
        title: 'Significantly over-provisioned CPU requests',
        summary: 'The payment-service is requesting 2000m CPU but historical usage rarely exceeds 150m.',
        resource_kind: 'Deployment',
        resource_name: 'payment-service',
        namespace: 'production',
        evidence: {
          requested_cpu: '2000m',
          p99_cpu_usage: '142m',
          waste_ratio: '14x'
        },
        recommended_change: 'Reduce CPU requests from 2000m to 250m. This will free up cluster capacity while maintaining a safe buffer.',
        confidence: 0.92,
        timestamp: new Date(Date.now() - 86400000).toISOString(),
        dismissed: true
      }
    ];

    let filtered = mockFindings;
    if (params.namespace) {
      filtered = filtered.filter(f => f.namespace === params.namespace);
    }
    if (params.dismissed_only) {
      filtered = filtered.filter(f => f.dismissed === true);
    } else {
      filtered = filtered.filter(f => f.dismissed === false);
    }

    return { findings: filtered };
  },
  getAdviceDetectors: async () => ({ detectors: [], hubble_status: { available: true } }),
  runAdviceScan: async (scope) => ({ scan_id: 'scan-123' }),
  dismissAdviceFinding: async (id) => ({ success: true }),
  restoreAdviceFinding: async (id) => ({ success: true }),
  downloadAdviceFindings: async (format, params) => {},
  explainAdviceFinding: async (id) => ({
    id,
    explanation: 'This is an AI-generated explanation providing deep context about why this is an issue and how exactly you should fix it. In a real environment, this text streams in from the configured LLM provider based on the resources current state and the configured rules.'
  }),
  
  // Mirrors
  getActiveMirrors: async () => ([]),
  getMirrorTTL: async () => ({ seconds: 3600 }),
  
  // Settings & Admin
  getLLMStatus: async () => ({ configured: true, provider: 'openai', model: 'gpt-4o' }),
  getAllNamespaces: async () => (['default', 'production', 'database', 'kube-system']),
  getExcludedNamespaces: async () => ([]),
  getExcludedPods: async () => ([]),
  getExcludedRules: async () => ([]),
  getAllRuleTitles: async () => (['KSV013', 'KSV014', 'KSV111']),
  getMonitoredPods: async () => ([]),
  getTrustedRegistries: async () => ([]),
  getNotificationSettings: async () => ([
    { provider: 'slack', enabled: false, config: { webhook_url: '' } },
    { provider: 'teams', enabled: false, config: { webhook_url: '' } },
  ]),
  getAuthSetupRequired: async () => ({ setup_required: false }),
  getUsers: async () => ([{ id: 1, username: 'demo', email: 'demo@kuremonitor.com', role: 'admin' }]),
  getInvitations: async () => ([]),
};

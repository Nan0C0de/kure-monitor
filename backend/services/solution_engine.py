import logging
import re
import time
from typing import Dict, List, Optional
from models.models import PodEvent, ContainerStatus
from .llm_factory import LLMFactory
from .prometheus_metrics import LLM_REQUESTS_TOTAL, LLM_REQUEST_DURATION_SECONDS

logger = logging.getLogger(__name__)


class SolutionEngine:
    def __init__(self, db=None):
        # Store database reference for loading config
        self._db = db
        # Initialize LLM provider (will be set up properly after db init)
        self.llm_provider = None
        # Initialize hardcoded solutions dictionary
        self._init_solutions()

    def _init_solutions(self):
        """Initialize hardcoded solutions for common Kubernetes pod issues (fallback)"""
        self.solutions = {
            'ImagePullBackOff': {
                'default': 'The pod cannot pull the container image. Check: 1) Image name and tag are correct, 2) Image exists in the registry, 3) Registry credentials are properly configured, 4) Network connectivity to registry.',
                'patterns': {
                    'repository does not exist': 'The image repository does not exist. Verify the image name and registry URL.',
                    'pull access denied': 'Insufficient permissions to pull image. Check if imagePullSecrets are configured correctly.',
                    'not found': 'Image or tag not found. Verify the image name and tag exist in the registry.'
                }
            },
            'ErrImagePull': {
                'default': 'Error pulling container image. Verify: 1) Image name syntax is correct, 2) Registry is accessible, 3) Authentication credentials if needed.',
            },
            'CrashLoopBackOff': {
                'default': 'Container is crashing repeatedly. Check: 1) Application logs for errors, 2) Resource limits (CPU/Memory), 3) Environment variables and configuration, 4) Health check configuration.',
                'patterns': {
                    'exit code 125': 'Container failed to start. Check container configuration and command syntax.',
                    'exit code 126': 'Container command not executable. Verify file permissions and executable path.',
                    'exit code 127': 'Container command not found. Check if the command exists in the container.',
                    'OOMKilled': 'Container killed due to out of memory. Increase memory limits or optimize application memory usage.'
                }
            },
            'Pending': {
                'default': 'Pod is stuck in pending state. Check: 1) Node resources (CPU/Memory), 2) Node selectors and taints, 3) Persistent volume availability, 4) Image pull issues.',
                'patterns': {
                    'Insufficient cpu': 'Not enough CPU resources available. Scale cluster or reduce resource requests.',
                    'Insufficient memory': 'Not enough memory available. Scale cluster or reduce memory requests.',
                    'No nodes available': 'No suitable nodes found. Check node selectors, taints, and tolerations.',
                    'pod has unbound immediate PersistentVolumeClaims': 'Missing persistent volume. Create PV or check storage class configuration.',
                    'FailedScheduling': 'Scheduler cannot place pod. Check node resources, taints/tolerations, and node selectors.'
                }
            },
            'FailedScheduling': {
                'default': 'Pod cannot be scheduled to any node. Check: 1) Node resources (CPU/Memory), 2) Node selectors match available nodes, 3) Tolerations match node taints, 4) Affinity rules are satisfiable.',
                'patterns': {
                    'Insufficient cpu': 'Not enough CPU resources on nodes. Scale cluster, reduce resource requests, or wait for other pods to complete.',
                    'Insufficient memory': 'Not enough memory on nodes. Scale cluster, reduce memory requests, or wait for other pods to complete.',
                    'node(s) didn\'t match Pod\'s node affinity': 'No nodes match the pod\'s node selector or affinity rules. Update selectors or add matching nodes.',
                    'node(s) had taint': 'Nodes have taints that pod does not tolerate. Add tolerations to pod spec or remove taints from nodes.',
                    'persistentvolumeclaim': 'PVC not bound. Check PVC status and ensure storage class/PV is available.',
                    '0/': 'No nodes available for scheduling. Check if nodes are Ready and have sufficient resources.'
                }
            },
            'CreateContainerConfigError': {
                'default': 'Error creating container configuration. Check: 1) ConfigMap and Secret references, 2) Volume mount configurations, 3) Environment variable references.',
            },
            'InvalidImageName': {
                'default': 'Invalid container image name format. Verify image name follows registry/repository:tag format.',
            },
            'Error': {
                'default': 'Pod is in error state. Check pod events and logs for specific error details.',
            }
        }

    async def initialize(self):
        """Initialize the LLM provider from database configuration"""
        if self._db:
            try:
                db_config = await self._db.get_llm_config()
                if db_config:
                    logger.info(f"Loading LLM config from database: provider={db_config['provider']}")
                    self.llm_provider = LLMFactory.create_provider(
                        provider_name=db_config['provider'],
                        api_key=db_config['api_key'],
                        model=db_config['model'],
                        base_url=db_config.get('base_url')
                    )
                else:
                    logger.info("No LLM configuration found. Configure via Admin panel to enable AI solutions.")
            except Exception as e:
                logger.warning(f"Failed to load LLM config from database: {e}")

    async def reinitialize_llm(self, provider: str, api_key: str, model: str = None, base_url: str = None):
        """Reinitialize the LLM provider with new configuration"""
        try:
            self.llm_provider = LLMFactory.create_provider(
                provider_name=provider,
                api_key=api_key,
                model=model,
                base_url=base_url
            )
            logger.info(f"LLM provider reinitialized: {provider}")
        except Exception as e:
            logger.error(f"Failed to reinitialize LLM provider: {e}")
            raise

    async def get_solution(self, reason: str, message: Optional[str] = None,
                     events: List[PodEvent] = None,
                     container_statuses: List[ContainerStatus] = None,
                     pod_context: Dict = None,
                     use_llm: bool = True) -> str:
        """Generate solution based on failure reason and additional context"""

        # Try LLM first if available
        if use_llm and self.llm_provider:
            provider_name = self.llm_provider.provider_name
            start_time = time.monotonic()
            try:
                logger.info(f"Generating AI solution for {reason} using {provider_name}")

                # Convert events to dict format for LLM
                events_dict = []
                if events:
                    events_dict = [
                        {
                            "type": event.type,
                            "reason": event.reason,
                            "message": event.message
                        }
                        for event in events
                    ]

                # Convert container statuses to dict format
                container_statuses_dict = []
                if container_statuses:
                    container_statuses_dict = [
                        {
                            "name": status.name,
                            "restart_count": status.restart_count,
                            "last_state": getattr(status, 'last_state', None)
                        }
                        for status in container_statuses
                    ]

                llm_response = await self.llm_provider.generate_solution(
                    failure_reason=reason,
                    failure_message=message,
                    events=events_dict,
                    container_statuses=container_statuses_dict,
                    pod_context=pod_context
                )

                # Record success metrics
                duration = time.monotonic() - start_time
                LLM_REQUESTS_TOTAL.labels(provider=provider_name, status="success").inc()
                LLM_REQUEST_DURATION_SECONDS.labels(provider=provider_name).observe(duration)

                return llm_response.content

            except Exception as e:
                # Record error metrics
                duration = time.monotonic() - start_time
                LLM_REQUESTS_TOTAL.labels(provider=provider_name, status="error").inc()
                LLM_REQUEST_DURATION_SECONDS.labels(provider=provider_name).observe(duration)

                logger.error(f"LLM solution generation failed: {e}, falling back to hardcoded solutions")
        
        # Fallback to hardcoded solutions
        fallback_solution = self._get_fallback_solution(reason, message, events, container_statuses)
        return f"AI solution temporarily unavailable. Here's basic troubleshooting:\n\n{fallback_solution}"

    def _get_fallback_solution(self, reason: str, message: Optional[str] = None,
                     events: List[PodEvent] = None,
                     container_statuses: List[ContainerStatus] = None) -> str:
        """Generate fallback solution using hardcoded rules"""
        
        # Get base solution
        if reason in self.solutions:
            solution_config = self.solutions[reason]
            solution = solution_config['default']

            # Check for pattern-specific solutions
            if 'patterns' in solution_config:
                pattern_solution = self._find_pattern_solution(
                    solution_config['patterns'], message, events
                )
                if pattern_solution:
                    solution = pattern_solution
        else:
            solution = f"Unknown failure reason: {reason}. Check pod events and logs for more details."

        # Add context-specific advice
        solution = self._enhance_solution_with_context(
            solution, reason, message, events, container_statuses
        )

        return solution

    def _find_pattern_solution(self, patterns: Dict[str, str],
                               message: Optional[str],
                               events: List[PodEvent]) -> Optional[str]:
        """Find specific solution based on error message patterns"""
        search_text = ""

        if message:
            search_text += message.lower()

        if events:
            for event in events:
                search_text += f" {event.message.lower()}"

        for pattern, solution in patterns.items():
            if pattern.lower() in search_text:
                return solution

        return None

    def _enhance_solution_with_context(self, base_solution: str, reason: str,
                                       message: Optional[str],
                                       events: List[PodEvent],
                                       container_statuses: List[ContainerStatus]) -> str:
        """Add context-specific enhancements to the solution"""
        enhancements = []

        # Add specific commands or checks based on context
        if reason == 'ImagePullBackOff':
            enhancements.append(
                "Commands to check: 'kubectl describe pod <pod-name>' and 'docker pull <image>' on a node.")

        elif reason == 'CrashLoopBackOff':
            enhancements.append("Commands: 'kubectl logs <pod-name> --previous' to see crash logs.")

            # Check for high restart count
            if container_statuses:
                for status in container_statuses:
                    if status.restart_count > 5:
                        enhancements.append(
                            f"Container '{status.name}' has restarted {status.restart_count} times - investigate application startup issues.")

        elif reason == 'Pending':
            enhancements.append(
                "Commands: 'kubectl describe pod <pod-name>' and 'kubectl get nodes' to check resources.")

        # Add event-based enhancements
        if events:
            for event in events:
                if 'FailedScheduling' in event.reason:
                    enhancements.append("Scheduling issue detected - check node capacity and pod requirements.")
                elif 'FailedMount' in event.reason:
                    enhancements.append("Volume mount issue - verify PVC and volume configuration.")

        # Combine base solution with enhancements
        if enhancements:
            return base_solution + " Additional info: " + " ".join(enhancements)

        return base_solution

    async def generate_security_fix(self, manifest: str, title: str, description: str,
                                     remediation: str, resource_type: str, resource_name: str,
                                     namespace: str, severity: str) -> dict:
        """Generate an AI-powered security fix for a Kubernetes resource manifest.

        Returns:
            dict with keys: fixed_manifest, explanation, is_fallback
        """
        if not self.llm_provider or not manifest:
            return {
                'fixed_manifest': '',
                'explanation': remediation,
                'is_fallback': True
            }

        system_prompt = """You are a Kubernetes security expert. You will be given a Kubernetes resource YAML manifest and a security finding.
Your task is to produce a FIXED version of the manifest that resolves the security issue.

Rules:
- Return the COMPLETE fixed YAML manifest (not a partial patch)
- Only change what is necessary to fix the security issue
- Preserve all existing functionality
- Use best practices from Pod Security Standards and NSA/CISA guidelines
- Do NOT add comments to the YAML

Output format (follow EXACTLY):
```yaml
<complete fixed manifest here>
```
---EXPLANATION---
<brief explanation of what was changed and why, 2-4 sentences>"""

        user_prompt = f"""Security Finding:
- Title: {title}
- Severity: {severity}
- Description: {description}
- Remediation Guidance: {remediation}
- Resource: {resource_type}/{resource_name} in namespace {namespace}

Current Manifest:
```yaml
{manifest}
```

Please provide the fixed manifest and explanation."""

        try:
            provider_name = self.llm_provider.provider_name
            start_time = time.monotonic()

            llm_response = await self.llm_provider.generate_raw(system_prompt, user_prompt)

            duration = time.monotonic() - start_time
            LLM_REQUESTS_TOTAL.labels(provider=provider_name, status="success").inc()
            LLM_REQUEST_DURATION_SECONDS.labels(provider=provider_name).observe(duration)

            # Parse the response
            content = llm_response.content
            fixed_manifest = ''
            explanation = remediation

            # Extract YAML block
            yaml_match = re.search(r'```ya?ml\s*\n(.*?)```', content, re.DOTALL)
            if yaml_match:
                fixed_manifest = yaml_match.group(1).strip()

            # Extract explanation
            explanation_match = re.search(r'---EXPLANATION---\s*\n(.*?)$', content, re.DOTALL)
            if explanation_match:
                explanation = explanation_match.group(1).strip()
            elif not yaml_match:
                # If no structured output, use the whole response as explanation
                explanation = content

            return {
                'fixed_manifest': fixed_manifest,
                'explanation': explanation,
                'is_fallback': False
            }

        except Exception as e:
            logger.error(f"Security fix generation failed: {e}")
            return {
                'fixed_manifest': '',
                'explanation': remediation,
                'is_fallback': True
            }

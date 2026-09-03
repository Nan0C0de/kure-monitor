import logging
import re
import time
from typing import Dict, List, Optional
from core.config import LLM_LOGS_TAIL_LINES, LLM_MANIFEST_MAX_BYTES
from models.models import PodEvent, ContainerStatus
from .llm_factory import LLMFactory
from .prometheus_metrics import (
    LLM_REQUESTS_TOTAL,
    LLM_REQUEST_DURATION_SECONDS,
    LLM_FAILOVER_TOTAL,
)

logger = logging.getLogger(__name__)


class SolutionEngine:
    def __init__(self, db=None):
        # Store database reference for loading config
        self._db = db
        # Multi-provider pool: dict mapping config_id -> LLMProvider
        self.providers: Dict[int, any] = {}
        # Default provider ID (points to entry in self.providers)
        self.default_provider_id: Optional[int] = None
        # Legacy/primary reference for direct access (points to default provider)
        self.llm_provider = None
        # Custom instructions configured by cluster admin
        self.custom_instructions: Optional[str] = None
        # Initialize hardcoded solutions dictionary
        self._init_solutions()

    def _format_instructions(self) -> str:
        """Format custom instructions for injection into system or user prompts"""
        if self.custom_instructions and self.custom_instructions.strip():
            return f"\n\n--- Custom Instructions (provided by cluster admin) ---\n{self.custom_instructions.strip()}\n--- End Custom Instructions ---"
        return ""

    def _init_solutions(self):
        """Initialize hardcoded solutions for common Kubernetes pod issues (fallback)"""
        self.solutions = {
            "ImagePullBackOff": {
                "default": "The pod cannot pull the container image. Check: 1) Image name and tag are correct, 2) Image exists in the registry, 3) Registry credentials are properly configured, 4) Network connectivity to registry.",
                "patterns": {
                    "repository does not exist": "The image repository does not exist. Verify the image name and registry URL.",
                    "pull access denied": "Insufficient permissions to pull image. Check if imagePullSecrets are configured correctly.",
                    "not found": "Image or tag not found. Verify the image name and tag exist in the registry.",
                },
            },
            "ErrImagePull": {
                "default": "Error pulling container image. Verify: 1) Image name syntax is correct, 2) Registry is accessible, 3) Authentication credentials if needed.",
                "patterns": {
                    "not found": "Image or tag not found in the registry.",
                    "pull access denied": "Authentication failed. Check imagePullSecrets.",
                    "rpc error": "Container runtime error while pulling image.",
                },
            },
            "CrashLoopBackOff": {
                "default": "Container is crashing repeatedly. Check: 1) Application logs for errors, 2) Resource limits (CPU/Memory), 3) Environment variables and configuration, 4) Health check configuration.",
                "patterns": {
                    "exit code 125": "Container failed to start. Check container configuration and command syntax.",
                    "exit code 126": "Container command not executable. Verify file permissions and executable path.",
                    "exit code 127": "Container command not found. Check if the command exists in the container.",
                    "OOMKilled": "Container killed due to out of memory. Increase memory limits or optimize application memory usage.",
                },
            },
            "Pending": {
                "default": "Pod is stuck in pending state. Check: 1) Node resources (CPU/Memory), 2) Node selectors and taints, 3) Persistent volume availability, 4) Image pull issues.",
                "patterns": {
                    "Insufficient cpu": "Not enough CPU resources available. Scale cluster or reduce resource requests.",
                    "Insufficient memory": "Not enough memory available. Scale cluster or reduce memory requests.",
                    "No nodes available": "No suitable nodes found. Check node selectors, taints, and tolerations.",
                    "pod has unbound immediate PersistentVolumeClaims": "Missing persistent volume. Create PV or check storage class configuration.",
                    "FailedScheduling": "Scheduler cannot place pod. Check node resources, taints/tolerations, and node selectors.",
                },
            },
            "FailedScheduling": {
                "default": "Pod cannot be scheduled to any node. Check: 1) Node resources (CPU/Memory), 2) Node selectors match available nodes, 3) Tolerations match node taints, 4) Affinity rules are satisfiable.",
                "patterns": {
                    "Insufficient cpu": "Not enough CPU resources on nodes. Scale cluster, reduce resource requests, or wait for other pods to complete.",
                    "Insufficient memory": "Not enough memory on nodes. Scale cluster, reduce memory requests, or wait for other pods to complete.",
                    "node(s) didn't match Pod's node affinity": "No nodes match the pod's node selector or affinity rules. Update selectors or add matching nodes.",
                    "node(s) had taint": "Nodes have taints that pod does not tolerate. Add tolerations to pod spec or remove taints from nodes.",
                    "persistentvolumeclaim": "PVC not bound. Check PVC status and ensure storage class/PV is available.",
                    "0/": "No nodes available for scheduling. Check if nodes are Ready and have sufficient resources.",
                },
            },
            "CreateContainerConfigError": {
                "default": "Error creating container configuration. Check: 1) ConfigMap and Secret references, 2) Volume mount configurations, 3) Environment variable references.",
                "patterns": {
                    "not found": "A referenced ConfigMap or Secret is missing.",
                }
            },
            "CreateContainerError": {
                "default": "Failed to create container. Check: 1) Container spec validity, 2) Volume mount permissions, 3) Runtime configuration.",
                "patterns": {
                    "no such file or directory": "A host path or mount point is missing or invalid.",
                    "permission denied": "Container lacks permissions to mount or access resources.",
                }
            },
            "RunContainerError": {
                "default": "Failed to start container. Check: 1) Entrypoint/command syntax, 2) Executable permissions, 3) Missing libraries or binaries.",
                "patterns": {
                    "executable file not found": "The command or entrypoint binary is missing from the image.",
                    "permission denied": "The entrypoint script or binary lacks execution permissions.",
                }
            },
            "Evicted": {
                "default": "Pod was evicted from the node. Check: 1) Node disk pressure, 2) Node memory pressure, 3) Pod resource limits/requests.",
                "patterns": {
                    "disk pressure": "Node ran out of disk space. Check for large logs, emptyDirs, or local volumes.",
                    "memory pressure": "Node ran out of memory. Consider setting or reducing pod memory limits.",
                    "pid pressure": "Node ran out of available PIDs.",
                }
            },
            "NodeLost": {
                "default": "The node running the pod became unreachable. Check: 1) Node status, 2) Network connectivity to the node, 3) Kubelet status on the node.",
                "patterns": {
                    "node unresponsive": "Node stopped reporting to the control plane.",
                }
            },
            "InvalidImageName": {
                "default": "Invalid container image name format. Verify image name follows registry/repository:tag format.",
            },
            "Error": {
                "default": "Pod is in error state. Check pod events and logs for specific error details.",
            },
        }

    async def initialize(self):
        """Initialize all registered LLM providers and custom instructions from database"""
        if self._db:
            try:
                await self.reload_providers()
            except Exception as e:
                logger.warning(f"Failed to load LLM providers: {e}")

            try:
                self.custom_instructions = await self._db.get_app_setting(
                    "llm_custom_instructions"
                )
                if self.custom_instructions:
                    logger.info("Loaded custom LLM instructions from database")
            except Exception as e:
                logger.warning(f"Failed to load custom LLM instructions: {e}")

    async def reload_providers(self) -> None:
        """Reload all active LLM providers from database into self.providers pool"""
        if not self._db:
            return

        new_providers: Dict[int, any] = {}
        default_id: Optional[int] = None

        try:
            configs = await self._db.get_all_llm_configs(active_only=True)
            for c in configs:
                try:
                    p = LLMFactory.create_provider(
                        provider_name=c["provider"],
                        api_key=c["api_key"],
                        model=c["model"],
                        base_url=c.get("base_url"),
                    )
                    new_providers[c["id"]] = p
                    if c["is_default"] and default_id is None:
                        default_id = c["id"]
                except Exception as ex:
                    logger.warning(
                        f"Failed to initialize LLM provider '{c.get('name')}' ({c.get('provider')}): {ex}"
                    )

            # If no explicit default, use the first successfully created provider
            if default_id is None and new_providers:
                default_id = next(iter(new_providers.keys()))

            # Close old providers no longer in new pool
            for old_id, old_prov in list(self.providers.items()):
                if old_id not in new_providers:
                    try:
                        await old_prov.close()
                    except Exception:
                        pass

            self.providers = new_providers
            self.default_provider_id = default_id
            self.llm_provider = self.providers.get(default_id) if default_id else None

            logger.info(
                f"Loaded {len(self.providers)} active LLM provider(s). Default provider ID: {self.default_provider_id}"
            )
        except Exception as e:
            logger.error(f"Error in reload_providers: {e}")

    def get_provider(self, llm_id: Optional[int] = None):
        """Get requested provider by ID, or default provider if omitted/invalid"""
        if llm_id and llm_id in self.providers:
            return self.providers[llm_id]
        if self.default_provider_id and self.default_provider_id in self.providers:
            return self.providers[self.default_provider_id]
        return self.llm_provider

    def get_ordered_providers(self, target_llm_id: Optional[int] = None) -> List[tuple[int, any]]:
        """Return ordered list of (id, provider) starting with target or default, followed by remaining providers for failover"""
        ordered = []
        visited = set()

        # 1. First priority: explicitly requested target
        if target_llm_id and target_llm_id in self.providers:
            ordered.append((target_llm_id, self.providers[target_llm_id]))
            visited.add(target_llm_id)

        # 2. Second priority: designated default (if not already added)
        if self.default_provider_id and self.default_provider_id in self.providers and self.default_provider_id not in visited:
            ordered.append((self.default_provider_id, self.providers[self.default_provider_id]))
            visited.add(self.default_provider_id)

        # 3. Remaining active providers in priority order
        for pid, prov in self.providers.items():
            if pid not in visited:
                ordered.append((pid, prov))
                visited.add(pid)

        return ordered

    def update_custom_instructions(self, instructions: Optional[str]) -> None:
        """Update the active custom instructions in memory"""
        self.custom_instructions = instructions.strip() if instructions and instructions.strip() else None
        logger.info("Updated in-memory custom LLM instructions")

    async def reinitialize_llm(
        self, provider: str, api_key: str, model: str = None, base_url: str = None
    ):
        """Reinitialize providers from DB (supports legacy callers)"""
        await self.reload_providers()

    async def _swap_llm_provider(self, new_provider) -> None:
        """Legacy helper to replace default LLM provider"""
        old = self.llm_provider
        self.llm_provider = new_provider
        if old is not None and old is not new_provider:
            try:
                await old.close()
            except Exception:
                logger.warning(
                    "Failed to close previous LLM provider cleanly", exc_info=True
                )

    async def close(self) -> None:
        """Close all configured LLM providers in the pool."""
        for p in self.providers.values():
            try:
                await p.close()
            except Exception:
                pass
        self.providers.clear()
        self.llm_provider = None

    async def get_solution(
        self,
        reason: str,
        message: Optional[str] = None,
        events: List[PodEvent] = None,
        container_statuses: List[ContainerStatus] = None,
        pod_context: Dict = None,
        use_llm: bool = True,
        llm_id: Optional[int] = None,
    ) -> str:
        """Generate solution based on failure reason and additional context, with automatic multi-LLM failover."""

        ordered_providers = self.get_ordered_providers(target_llm_id=llm_id) if use_llm else []

        if ordered_providers:
            # Convert events to dict format for LLM once
            events_dict = []
            if events:
                events_dict = [
                    {
                        "type": event.type,
                        "reason": event.reason,
                        "message": event.message,
                    }
                    for event in events
                ]

            # Convert container statuses to dict format once
            container_statuses_dict = []
            if container_statuses:
                container_statuses_dict = [
                    {
                        "name": status.name,
                        "restart_count": status.restart_count,
                        "last_state": getattr(status, "last_state", None),
                    }
                    for status in container_statuses
                ]

            initial_provider_name = ordered_providers[0][1].provider_name

            for idx, (p_id, provider) in enumerate(ordered_providers):
                provider_name = provider.provider_name
                start_time = time.monotonic()
                try:
                    logger.info(
                        f"Generating AI solution for {reason} using provider '{provider_name}' (id={p_id})"
                    )

                    llm_response = await provider.generate_solution(
                        failure_reason=reason,
                        failure_message=message,
                        events=events_dict,
                        container_statuses=container_statuses_dict,
                        pod_context=pod_context,
                        custom_instructions=self.custom_instructions,
                    )

                    duration = time.monotonic() - start_time
                    LLM_REQUESTS_TOTAL.labels(
                        provider=provider_name, status="success"
                    ).inc()
                    LLM_REQUEST_DURATION_SECONDS.labels(provider=provider_name).observe(
                        duration
                    )

                    if idx > 0:
                        LLM_FAILOVER_TOTAL.labels(
                            from_provider=initial_provider_name,
                            to_provider=provider_name,
                        ).inc()
                        logger.info(
                            f"Failover successful: generated solution using fallback provider '{provider_name}'"
                        )

                    return llm_response.content

                except Exception as e:
                    duration = time.monotonic() - start_time
                    LLM_REQUESTS_TOTAL.labels(provider=provider_name, status="error").inc()
                    LLM_REQUEST_DURATION_SECONDS.labels(provider=provider_name).observe(
                        duration
                    )
                    logger.warning(
                        f"LLM provider '{provider_name}' (id={p_id}) failed: {e}. "
                        f"{'Attempting failover to next provider...' if idx + 1 < len(ordered_providers) else 'No more providers to try.'}"
                    )

        # Fallback to hardcoded solutions
        fallback_solution = self._get_fallback_solution(
            reason, message, events, container_statuses
        )

        if not self.providers:
            return f"AI solution temporarily unavailable. Here's basic troubleshooting:\n\n{fallback_solution}"
        else:
            return fallback_solution

    async def get_log_aware_solution(
        self,
        reason: str,
        message: Optional[str] = None,
        events: List = None,
        container_statuses: List = None,
        pod_context: Dict = None,
        manifest: str = "",
        container_logs: List[dict] = None,
        llm_id: Optional[int] = None,
    ) -> str:
        """Generate an LLM-only troubleshoot solution with automatic multi-LLM failover."""
        ordered_providers = self.get_ordered_providers(target_llm_id=llm_id)
        if not ordered_providers:
            return (
                "Log-aware troubleshoot is unavailable because no active LLM provider is "
                "configured. Configure an LLM provider in the Admin panel to enable "
                "AI-powered, log-aware troubleshooting."
            )

        # Normalize events / container_statuses into list-of-dict form once
        events_dict: List[Dict] = []
        if events:
            for event in events:
                if isinstance(event, dict):
                    events_dict.append(
                        {
                            "type": event.get("type", "Unknown"),
                            "reason": event.get("reason", ""),
                            "message": event.get("message", ""),
                        }
                    )
                elif hasattr(event, "type"):
                    events_dict.append(
                        {
                            "type": event.type,
                            "reason": event.reason,
                            "message": event.message,
                        }
                    )

        statuses_dict: List[Dict] = []
        if container_statuses:
            for status in container_statuses:
                if isinstance(status, dict):
                    statuses_dict.append(
                        {
                            "name": status.get("name", "Unknown"),
                            "restart_count": status.get("restart_count", 0),
                            "last_state": status.get("last_state"),
                        }
                    )
                elif hasattr(status, "name"):
                    statuses_dict.append(
                        {
                            "name": status.name,
                            "restart_count": status.restart_count,
                            "last_state": getattr(status, "last_state", None),
                        }
                    )

        system_prompt = (
            "You are a Kubernetes expert. Use the previous container logs as the "
            "primary diagnostic signal. Identify the root cause of the failure from "
            "the logs and propose a specific, actionable fix. Reference concrete "
            "lines from the logs in your explanation."
        ) + self._format_instructions()

        user_prompt = self._build_log_aware_prompt(
            reason=reason,
            message=message,
            events=events_dict,
            container_statuses=statuses_dict,
            pod_context=pod_context,
            manifest=manifest or "",
            container_logs=container_logs or [],
        )

        initial_provider_name = ordered_providers[0][1].provider_name

        for idx, (p_id, provider) in enumerate(ordered_providers):
            provider_name = provider.provider_name
            start_time = time.monotonic()
            try:
                llm_response = await provider.generate_raw(
                    system_prompt, user_prompt
                )
                duration = time.monotonic() - start_time
                LLM_REQUESTS_TOTAL.labels(provider=provider_name, status="success").inc()
                LLM_REQUEST_DURATION_SECONDS.labels(provider=provider_name).observe(
                    duration
                )

                if idx > 0:
                    LLM_FAILOVER_TOTAL.labels(
                        from_provider=initial_provider_name,
                        to_provider=provider_name,
                    ).inc()
                    logger.info(
                        f"Failover successful in log-aware triage: used '{provider_name}'"
                    )

                return llm_response.content
            except Exception as e:
                duration = time.monotonic() - start_time
                LLM_REQUESTS_TOTAL.labels(provider=provider_name, status="error").inc()
                LLM_REQUEST_DURATION_SECONDS.labels(provider=provider_name).observe(
                    duration
                )
                logger.warning(
                    f"Log-aware solution failed with provider '{provider_name}' (id={p_id}): {e}. "
                    f"{'Attempting failover to next provider...' if idx + 1 < len(ordered_providers) else 'All providers failed.'}"
                )

        return "Failed to generate log-aware troubleshoot solution: All configured LLM providers failed."

    def _build_log_aware_prompt(
        self,
        reason: str,
        message: Optional[str],
        events: List[Dict],
        container_statuses: List[Dict],
        pod_context: Optional[Dict],
        manifest: str,
        container_logs: List[dict],
    ) -> str:
        """Assemble the user prompt for log-aware troubleshoot."""
        lines: List[str] = []
        lines.append("## Pod Failure Details")
        lines.append(f"- Failure Reason: {reason}")
        if message:
            lines.append(f"- Failure Message: {message}")
        if pod_context:
            lines.append(
                f"- Pod Name: {pod_context.get('pod_name') or pod_context.get('name', 'Unknown')}"
            )
            lines.append(f"- Namespace: {pod_context.get('namespace', 'Unknown')}")
            image = pod_context.get("image")
            if image:
                lines.append(f"- Image: {image}")

        if events:
            # We omit events from the log-aware prompt so the model focuses strictly on logs.
            pass

        if container_statuses:
            lines.append("")
            lines.append("## Container Statuses")
            for status in container_statuses:
                entry = (
                    f"- {status.get('name', 'Unknown')}: "
                    f"restart_count={status.get('restart_count', 0)}"
                )
                if status.get("last_state"):
                    entry += f", last_state={status['last_state']}"
                lines.append(entry)

        # Manifest omitted to focus on logs
        if manifest:
            pass

        # Previous container logs — the primary signal
        if container_logs:
            lines.append("")
            lines.append("## Previous Container Logs")
            for entry in container_logs:
                container_name = entry.get("container_name", "unknown")
                source = entry.get("source", "previous")
                log_text = entry.get("logs", "") or ""
                log_lines = log_text.splitlines()
                if len(log_lines) > LLM_LOGS_TAIL_LINES:
                    log_lines = log_lines[-LLM_LOGS_TAIL_LINES:]
                truncated_flag = (
                    " (truncated)"
                    if entry.get("truncated")
                    or len(log_text.splitlines()) > LLM_LOGS_TAIL_LINES
                    else ""
                )
                lines.append("")
                lines.append(
                    f"### Container: {container_name} [{source}]{truncated_flag}"
                )
                lines.append("```")
                lines.append("\n".join(log_lines))
                lines.append("```")

        lines.append("")
        lines.append(
            "Please analyze the logs first, identify the root cause, and provide a "
            "specific fix. Use this output format:\n\n"
            "## Root Cause\n<what the logs show>\n\n"
            "## Fix\n1. Step-by-step remediation\n\n"
            "## Verification\n- How to confirm the fix worked"
        )

        return "\n".join(lines)

    def _get_fallback_solution(
        self,
        reason: str,
        message: Optional[str] = None,
        events: List[PodEvent] = None,
        container_statuses: List[ContainerStatus] = None,
    ) -> str:
        """Generate fallback solution using hardcoded rules"""

        # Get base solution
        if reason in self.solutions:
            solution_config = self.solutions[reason]
            solution = solution_config["default"]

            # Check for pattern-specific solutions
            if "patterns" in solution_config:
                pattern_solution = self._find_pattern_solution(
                    solution_config["patterns"], message, events
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

    def _find_pattern_solution(
        self, patterns: Dict[str, str], message: Optional[str], events: List[PodEvent]
    ) -> Optional[str]:
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

    def _enhance_solution_with_context(
        self,
        base_solution: str,
        reason: str,
        message: Optional[str],
        events: List[PodEvent],
        container_statuses: List[ContainerStatus],
    ) -> str:
        """Add context-specific enhancements to the solution"""
        enhancements = []

        # Add specific commands or checks based on context
        if reason == "ImagePullBackOff":
            enhancements.append(
                "Commands to check: 'kubectl describe pod <pod-name>' and 'docker pull <image>' on a node."
            )

        elif reason == "CrashLoopBackOff":
            enhancements.append(
                "Commands: 'kubectl logs <pod-name> --previous' to see crash logs."
            )

            # Check for high restart count
            if container_statuses:
                for status in container_statuses:
                    if status.restart_count > 5:
                        enhancements.append(
                            f"Container '{status.name}' has restarted {status.restart_count} times - investigate application startup issues."
                        )

        elif reason == "Pending":
            enhancements.append(
                "Commands: 'kubectl describe pod <pod-name>' and 'kubectl get nodes' to check resources."
            )

        # Add event-based enhancements
        if events:
            for event in events:
                if "FailedScheduling" in event.reason:
                    enhancements.append(
                        "Scheduling issue detected - check node capacity and pod requirements."
                    )
                elif "FailedMount" in event.reason:
                    enhancements.append(
                        "Volume mount issue - verify PVC and volume configuration."
                    )

        # Combine base solution with enhancements
        if enhancements:
            return base_solution + " Additional info: " + " ".join(enhancements)

        return base_solution

    async def generate_pod_fix(
        self,
        manifest: str,
        failure_reason: str,
        failure_message: str,
        events: list,
        solution: str,
        llm_id: Optional[int] = None,
    ) -> dict:
        """Generate an AI-fixed pod manifest based on failure analysis, with failover."""
        ordered_providers = self.get_ordered_providers(target_llm_id=llm_id)
        if not ordered_providers or not manifest:
            return {
                "fixed_manifest": "",
                "explanation": "No LLM configured. Cannot generate a fixed manifest automatically.",
                "is_fallback": True,
            }

        system_prompt = (
            """You are a Kubernetes expert. You will be given a Kubernetes Pod YAML manifest, a failure reason, events, and a suggested solution.
Your task is to produce a FIXED version of the manifest that resolves the failure.

Rules:
- Return the COMPLETE fixed YAML manifest (not a partial patch)
- Only change what is necessary to fix the SPECIFIC failure described
- Do NOT modify metadata fields (name, namespace, labels, annotations) unless the failure is specifically about them
- Do NOT change fields that are unrelated to the failure, even if they could be improved
- Preserve all existing functionality
- If the fix requires external action (e.g., creating a Secret, adding a node) that cannot be expressed in the manifest, still return the best possible manifest and explain what else is needed
- Do NOT add comments to the YAML

Output format (follow EXACTLY):
```yaml
<complete fixed manifest here>
```
---EXPLANATION---
<brief explanation of what was changed and why, 2-4 sentences>"""
            + self._format_instructions()
        )

        user_prompt = f"""Pod Failure Details:
- Failure Reason: {failure_reason}
- Failure Message: {failure_message or 'N/A'}

Events:
{self._format_events_for_prompt(events)}

Previously Suggested Solution:
{solution}

Current Pod Manifest:
```yaml
{manifest}
```

Please provide the fixed manifest and explanation."""

        initial_provider_name = ordered_providers[0][1].provider_name

        for idx, (p_id, provider) in enumerate(ordered_providers):
            provider_name = provider.provider_name
            start_time = time.monotonic()
            try:
                llm_response = await provider.generate_raw(
                    system_prompt, user_prompt
                )
                duration = time.monotonic() - start_time
                LLM_REQUESTS_TOTAL.labels(provider=provider_name, status="success").inc()
                LLM_REQUEST_DURATION_SECONDS.labels(provider=provider_name).observe(
                    duration
                )

                if idx > 0:
                    LLM_FAILOVER_TOTAL.labels(
                        from_provider=initial_provider_name,
                        to_provider=provider_name,
                    ).inc()

                # Parse the response
                content = llm_response.content
                fixed_manifest = ""
                explanation = ""

                yaml_match = re.search(r"```ya?ml\s*\n(.*?)```", content, re.DOTALL)
                if yaml_match:
                    fixed_manifest = yaml_match.group(1).strip()

                explanation_match = re.search(
                    r"---EXPLANATION---\s*\n(.*?)$", content, re.DOTALL
                )
                if explanation_match:
                    explanation = explanation_match.group(1).strip()
                elif not yaml_match:
                    explanation = content

                return {
                    "fixed_manifest": fixed_manifest,
                    "explanation": explanation,
                    "is_fallback": False,
                    "provider": provider_name,
                    "provider_id": p_id,
                }
            except Exception as e:
                duration = time.monotonic() - start_time
                LLM_REQUESTS_TOTAL.labels(provider=provider_name, status="error").inc()
                LLM_REQUEST_DURATION_SECONDS.labels(provider=provider_name).observe(
                    duration
                )
                logger.warning(
                    f"Pod fix generation failed with provider '{provider_name}' (id={p_id}): {e}. "
                    f"{'Attempting failover to next provider...' if idx + 1 < len(ordered_providers) else 'All providers failed.'}"
                )

        return {
            "fixed_manifest": "",
            "explanation": "Failed to generate fix: All configured LLM providers failed.",
            "is_fallback": True,
        }

    def _format_events_for_prompt(self, events: list) -> str:
        """Format events list for LLM prompt"""
        if not events:
            return "No events available"
        lines = []
        for event in events[-10:]:
            if isinstance(event, dict):
                lines.append(
                    f"- {event.get('type', 'Unknown')} {event.get('reason', '')}: {event.get('message', '')}"
                )
            elif hasattr(event, "type"):
                lines.append(f"- {event.type} {event.reason}: {event.message}")
            else:
                lines.append(f"- {str(event)}")
        return "\n".join(lines)

    async def generate_security_fix(
        self,
        manifest: str,
        title: str,
        description: str,
        remediation: str,
        resource_type: str,
        resource_name: str,
        namespace: str,
        severity: str,
        llm_id: Optional[int] = None,
    ) -> dict:
        """Generate an AI-powered security fix for a Kubernetes resource manifest, with failover.

        Returns:
            dict with keys: fixed_manifest, explanation, is_fallback
        """
        ordered_providers = self.get_ordered_providers(target_llm_id=llm_id)
        if not ordered_providers or not manifest:
            return {
                "fixed_manifest": "",
                "explanation": remediation,
                "is_fallback": True,
            }

        system_prompt = (
            """You are a Kubernetes security expert. You will be given a Kubernetes resource YAML manifest and a security finding.
Your task is to produce a FIXED version of the manifest that resolves the security issue.

Rules:
- Return the COMPLETE fixed YAML manifest (not a partial patch)
- Only change what is necessary to fix the SPECIFIC security issue described in the finding
- Do NOT modify metadata fields (name, namespace, labels, annotations) unless the finding is specifically about them
- Do NOT change fields that are unrelated to the security finding, even if they could be improved
- Preserve all existing functionality
- Use best practices from Pod Security Standards and NSA/CISA guidelines
- Do NOT add comments to the YAML

Output format (follow EXACTLY):
```yaml
<complete fixed manifest here>
```
---EXPLANATION---
<brief explanation of what was changed and why, 2-4 sentences>"""
            + self._format_instructions()
        )

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

        initial_provider_name = ordered_providers[0][1].provider_name

        for idx, (p_id, provider) in enumerate(ordered_providers):
            provider_name = provider.provider_name
            start_time = time.monotonic()
            try:
                llm_response = await provider.generate_raw(
                    system_prompt, user_prompt
                )

                duration = time.monotonic() - start_time
                LLM_REQUESTS_TOTAL.labels(provider=provider_name, status="success").inc()
                LLM_REQUEST_DURATION_SECONDS.labels(provider=provider_name).observe(
                    duration
                )

                if idx > 0:
                    LLM_FAILOVER_TOTAL.labels(
                        from_provider=initial_provider_name,
                        to_provider=provider_name,
                    ).inc()

                # Parse the response
                content = llm_response.content
                fixed_manifest = ""
                explanation = remediation

                # Extract YAML block
                yaml_match = re.search(r"```ya?ml\s*\n(.*?)```", content, re.DOTALL)
                if yaml_match:
                    fixed_manifest = yaml_match.group(1).strip()

                # Extract explanation
                explanation_match = re.search(
                    r"---EXPLANATION---\s*\n(.*?)$", content, re.DOTALL
                )
                if explanation_match:
                    explanation = explanation_match.group(1).strip()
                elif not yaml_match:
                    # If no structured output, use the whole response as explanation
                    explanation = content

                return {
                    "fixed_manifest": fixed_manifest,
                    "explanation": explanation,
                    "is_fallback": False,
                    "provider": provider_name,
                    "provider_id": p_id,
                }

            except Exception as e:
                duration = time.monotonic() - start_time
                LLM_REQUESTS_TOTAL.labels(provider=provider_name, status="error").inc()
                LLM_REQUEST_DURATION_SECONDS.labels(provider=provider_name).observe(
                    duration
                )
                logger.warning(
                    f"Security fix generation failed with provider '{provider_name}' (id={p_id}): {e}. "
                    f"{'Attempting failover to next provider...' if idx + 1 < len(ordered_providers) else 'All providers failed.'}"
                )

        return {
            "fixed_manifest": "",
            "explanation": remediation,
            "is_fallback": True,
        }

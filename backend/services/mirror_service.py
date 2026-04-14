import asyncio
import copy
import logging
import uuid
import yaml
from datetime import datetime, timezone
from typing import Dict, Optional

try:
    from kubernetes import client, config
    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False

from database.database import Database
from services.solution_engine import SolutionEngine
from services.websocket import WebSocketManager

logger = logging.getLogger(__name__)

DEFAULT_MIRROR_TTL_SECONDS = 180

# Metadata fields that are runtime/cluster-assigned and should be stripped
_METADATA_FIELDS_TO_REMOVE = {
    "creationTimestamp", "creation_timestamp",
    "deletionTimestamp", "deletion_timestamp",
    "deletionGracePeriodSeconds", "deletion_grace_period_seconds",
    "generateName", "generate_name",
    "generation",
    "resourceVersion", "resource_version",
    "selfLink", "self_link",
    "uid",
    "managedFields", "managed_fields",
    "ownerReferences", "owner_references",
    "finalizers",
}

# Spec-level fields to always remove (scheduler/runtime assigned)
_SPEC_FIELDS_TO_REMOVE = {
    "nodeName", "node_name",
    "priority",
    "preemptionPolicy", "preemption_policy",
    "enableServiceLinks", "enable_service_links",
    "schedulerName", "scheduler_name",
}

# Default tolerations auto-added by Kubernetes (should be stripped)
_DEFAULT_TOLERATIONS = {
    "node.kubernetes.io/not-ready",
    "node.kubernetes.io/unreachable",
}

# Volume name prefixes that are auto-injected by Kubernetes
_AUTO_INJECTED_VOLUME_PREFIXES = (
    "kube-api-access-",
    "default-token-",
)

# Per-container fields to remove
_CONTAINER_FIELDS_TO_REMOVE = {
    "terminationMessagePath", "termination_message_path",
    "terminationMessagePolicy", "termination_message_policy",
}

# Status sub-fields (also covers top-level 'status' being removed entirely)
_STATUS_FIELDS_TO_REMOVE = {
    "podIP", "pod_ip",
    "podIPs", "pod_ips",
    "hostIP", "host_ip",
    "hostIPs", "host_ips",
    "startTime", "start_time",
    "phase",
    "conditions",
    "containerStatuses", "container_statuses",
    "initContainerStatuses", "init_container_statuses",
    "qosClass", "qos_class",
}


def clean_manifest(manifest) -> str:
    """Clean runtime/cluster-assigned fields from a pod manifest.

    Accepts either a dict or a YAML string. Always returns a YAML string
    with only user-configurable fields retained.
    """
    if isinstance(manifest, str):
        manifest_dict = yaml.safe_load(manifest)
        if not isinstance(manifest_dict, dict):
            return manifest  # Not a valid manifest dict, return as-is
    elif isinstance(manifest, dict):
        # Work on a deep copy to avoid mutating the caller's dict
        manifest_dict = copy.deepcopy(manifest)
    else:
        raise TypeError(f"Expected str or dict, got {type(manifest).__name__}")

    _clean_manifest_dict(manifest_dict)
    return yaml.dump(manifest_dict, default_flow_style=False)


def _clean_manifest_dict(manifest_dict: dict) -> None:
    """In-place removal of runtime/cluster-assigned fields from a pod manifest dict."""

    # 1. Remove top-level 'status' entirely
    manifest_dict.pop("status", None)

    # 2. Clean metadata
    metadata = manifest_dict.get("metadata")
    if isinstance(metadata, dict):
        for field in _METADATA_FIELDS_TO_REMOVE:
            metadata.pop(field, None)

    # 3. Clean spec
    spec = manifest_dict.get("spec")
    if isinstance(spec, dict):
        # Remove scheduler/runtime spec fields
        for field in _SPEC_FIELDS_TO_REMOVE:
            spec.pop(field, None)

        # Remove serviceAccountName only if it's "default"
        for key in ("serviceAccountName", "service_account_name"):
            if spec.get(key) == "default":
                spec.pop(key, None)

        # Remove priorityClassName only if empty string
        for key in ("priorityClassName", "priority_class_name"):
            if key in spec and spec[key] in ("", None):
                spec.pop(key, None)

        # Remove default Kubernetes tolerations (auto-injected)
        for key in ("tolerations",):
            if key in spec and isinstance(spec[key], list):
                spec[key] = [
                    t for t in spec[key]
                    if not isinstance(t, dict) or t.get("key") not in _DEFAULT_TOLERATIONS
                ]
                if not spec[key]:
                    del spec[key]

        # Remove auto-injected volumes (kube-api-access-*, default-token-*)
        for key in ("volumes",):
            if key in spec and isinstance(spec[key], list):
                spec[key] = [
                    v for v in spec[key]
                    if not isinstance(v, dict) or not any(
                        v.get("name", "").startswith(prefix) for prefix in _AUTO_INJECTED_VOLUME_PREFIXES
                    )
                ]
                if not spec[key]:
                    del spec[key]

        # Remove auto-injected volumeMounts from containers
        def _clean_container(container):
            if isinstance(container, dict):
                for field in _CONTAINER_FIELDS_TO_REMOVE:
                    container.pop(field, None)
                # Remove volumeMounts referencing auto-injected volumes
                for mounts_key in ("volumeMounts", "volume_mounts"):
                    if mounts_key in container and isinstance(container[mounts_key], list):
                        container[mounts_key] = [
                            m for m in container[mounts_key]
                            if not isinstance(m, dict) or not any(
                                m.get("name", "").startswith(prefix) for prefix in _AUTO_INJECTED_VOLUME_PREFIXES
                            )
                        ]
                        if not container[mounts_key]:
                            del container[mounts_key]

        # Clean containers
        for container in spec.get("containers", []):
            _clean_container(container)

        # Clean initContainers
        for container in spec.get("initContainers", spec.get("init_containers", [])) or []:
            _clean_container(container)


class MirrorService:
    """Service for creating, tracking, and auto-deleting mirror pods."""

    def __init__(self, db: Database, solution_engine: SolutionEngine, websocket_manager: WebSocketManager):
        self._db = db
        self._solution_engine = solution_engine
        self._websocket_manager = websocket_manager
        self._active_mirrors: Dict[str, dict] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._k8s_core_v1: Optional[object] = None

    def _init_k8s_client(self):
        """Initialize Kubernetes client (in-cluster first, then local kubeconfig)."""
        if self._k8s_core_v1 is not None:
            return

        if not K8S_AVAILABLE:
            raise RuntimeError("Kubernetes Python client is not installed")

        try:
            config.load_incluster_config()
            logger.info("Mirror service: using in-cluster Kubernetes config")
        except config.ConfigException:
            try:
                config.load_kube_config()
                logger.info("Mirror service: using local kubeconfig")
            except config.ConfigException:
                raise RuntimeError("Could not configure Kubernetes client (tried in-cluster and kubeconfig)")

        self._k8s_core_v1 = client.CoreV1Api()

    async def start_cleanup_task(self):
        """Start the background cleanup loop."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Mirror pod cleanup background task started")

    async def stop_cleanup_task(self):
        """Cancel the background cleanup loop."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_loop(self):
        """Background loop that checks TTL and deletes expired mirror pods every 30 seconds."""
        while True:
            try:
                await asyncio.sleep(30)
                await self._cleanup_expired_mirrors()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in mirror cleanup loop: {e}")

    async def _cleanup_expired_mirrors(self):
        """Delete all mirror pods that have exceeded their TTL."""
        now = datetime.now(timezone.utc)
        expired_ids = []

        for mirror_id, info in list(self._active_mirrors.items()):
            expires_at = datetime.fromisoformat(info["expires_at"])
            if now >= expires_at:
                expired_ids.append(mirror_id)

        for mirror_id in expired_ids:
            try:
                await self.delete_mirror(mirror_id)
                logger.info(f"TTL expired, deleted mirror pod: {mirror_id}")
            except Exception as e:
                logger.error(f"Failed to delete expired mirror pod {mirror_id}: {e}")

    async def get_default_ttl(self) -> int:
        """Get the default mirror TTL from app settings."""
        value = await self._db.get_app_setting("mirror_ttl_seconds")
        return int(value) if value else DEFAULT_MIRROR_TTL_SECONDS

    async def set_default_ttl(self, seconds: int):
        """Set the default mirror TTL in app settings."""
        await self._db.set_app_setting("mirror_ttl_seconds", str(seconds))

    async def generate_preview(self, pod_failure_id: int) -> dict:
        """Generate an AI-fixed manifest preview without deploying.

        Returns:
            dict with keys: fixed_manifest, explanation, is_fallback
        """
        self._init_k8s_client()

        # 1. Get pod failure record
        pod_failure = await self._db.get_pod_failure_by_id(pod_failure_id)
        if not pod_failure:
            raise ValueError(f"Pod failure record not found: {pod_failure_id}")

        original_name = pod_failure.pod_name
        namespace = pod_failure.namespace

        # 2. Get original pod manifest from K8s API
        try:
            original_pod = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._k8s_core_v1.read_namespaced_pod(name=original_name, namespace=namespace)
            )
        except client.ApiException as e:
            if e.status == 404:
                raise ValueError(
                    f"Pod '{original_name}' not found in namespace '{namespace}'. "
                    "It may have been deleted. Cannot generate preview."
                )
            raise RuntimeError(f"Kubernetes API error: {e.reason}")

        # Convert to dict, clean runtime fields, then to YAML for the LLM
        serialized = client.ApiClient().sanitize_for_serialization(original_pod)
        original_manifest_yaml = clean_manifest(serialized)

        # 3. Build events list
        events_list = []
        if pod_failure.events:
            for e in pod_failure.events:
                if isinstance(e, dict):
                    events_list.append(e)
                elif hasattr(e, 'dict'):
                    events_list.append(e.dict())
                elif hasattr(e, 'model_dump'):
                    events_list.append(e.model_dump())

        # 4. Generate AI-fixed manifest
        fix_result = await self._solution_engine.generate_pod_fix(
            manifest=original_manifest_yaml,
            failure_reason=pod_failure.failure_reason,
            failure_message=pod_failure.failure_message or "",
            events=events_list,
            solution=pod_failure.solution
        )

        return fix_result

    async def create_mirror(self, pod_failure_id: int, ttl_seconds: Optional[int] = None, manifest: Optional[str] = None) -> dict:
        """Create a mirror pod from a failing pod's data.

        Steps:
        1. Get the pod failure record from DB
        2. Get the original pod manifest from K8s API
        3. Generate an AI-fixed manifest
        4. Strip ownerReferences, rename, add labels/annotations
        5. Deploy to K8s
        6. Track in-memory

        Returns mirror info dict.
        """
        self._init_k8s_client()

        # 1. Get pod failure record
        pod_failure = await self._db.get_pod_failure_by_id(pod_failure_id)
        if not pod_failure:
            raise ValueError(f"Pod failure record not found: {pod_failure_id}")

        original_name = pod_failure.pod_name
        namespace = pod_failure.namespace

        # 2. Get original pod manifest from K8s API
        try:
            original_pod = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._k8s_core_v1.read_namespaced_pod(name=original_name, namespace=namespace)
            )
        except client.ApiException as e:
            if e.status == 404:
                raise ValueError(
                    f"Pod '{original_name}' not found in namespace '{namespace}'. "
                    "It may have been deleted. Cannot create mirror."
                )
            raise RuntimeError(f"Kubernetes API error: {e.reason}")

        # Serialize and clean runtime fields
        serialized = client.ApiClient().sanitize_for_serialization(original_pod)
        original_manifest_yaml = clean_manifest(serialized)

        # 3. Use provided manifest or generate AI-fixed manifest
        if manifest:
            # User provided an edited manifest (e.g. from the preview flow)
            # Clean it in case it still contains runtime fields
            fix_result = {
                "fixed_manifest": clean_manifest(manifest),
                "explanation": "User-provided manifest",
                "is_fallback": False,
            }
        else:
            events_list = []
            if pod_failure.events:
                for e in pod_failure.events:
                    if isinstance(e, dict):
                        events_list.append(e)
                    elif hasattr(e, 'dict'):
                        events_list.append(e.dict())
                    elif hasattr(e, 'model_dump'):
                        events_list.append(e.model_dump())

            fix_result = await self._solution_engine.generate_pod_fix(
                manifest=original_manifest_yaml,
                failure_reason=pod_failure.failure_reason,
                failure_message=pod_failure.failure_message or "",
                events=events_list,
                solution=pod_failure.solution
            )

        # Determine the effective TTL
        if ttl_seconds is None:
            ttl_seconds = await self.get_default_ttl()

        # 4. Build the mirror pod spec
        mirror_id = str(uuid.uuid4())
        mirror_pod_name = f"{original_name}-kure-mirror"
        now = datetime.now(timezone.utc)
        expires_at = datetime.fromtimestamp(now.timestamp() + ttl_seconds, tz=timezone.utc)

        # Parse fixed manifest if available, otherwise use cleaned original
        if fix_result["fixed_manifest"]:
            try:
                mirror_spec = yaml.safe_load(fix_result["fixed_manifest"])
            except yaml.YAMLError:
                logger.warning("Failed to parse AI-generated manifest, using original")
                mirror_spec = yaml.safe_load(original_manifest_yaml)
        else:
            mirror_spec = yaml.safe_load(original_manifest_yaml)

        # Apply mirror pod modifications
        self._prepare_mirror_spec(
            mirror_spec,
            mirror_pod_name=mirror_pod_name,
            original_pod_name=original_name,
            namespace=namespace,
            pod_failure_id=pod_failure_id,
            mirror_id=mirror_id,
            ttl_seconds=ttl_seconds,
            created_at=now.isoformat()
        )

        # 5. Deploy to Kubernetes
        try:
            created_pod = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._k8s_core_v1.create_namespaced_pod(
                    namespace=namespace,
                    body=mirror_spec
                )
            )
            phase = created_pod.status.phase if created_pod.status and created_pod.status.phase else "Pending"
        except client.ApiException as e:
            raise RuntimeError(f"Failed to create mirror pod: {e.reason}")

        # 6. Track in-memory
        mirror_info = {
            "mirror_id": mirror_id,
            "mirror_pod_name": mirror_pod_name,
            "namespace": namespace,
            "source_pod_name": original_name,
            "pod_failure_id": pod_failure_id,
            "phase": phase,
            "ttl_seconds": ttl_seconds,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "fixed_manifest": fix_result["fixed_manifest"],
            "explanation": fix_result["explanation"],
            "is_fallback": fix_result["is_fallback"],
        }
        self._active_mirrors[mirror_id] = mirror_info

        logger.info(
            f"Mirror pod created: {mirror_pod_name} in {namespace} "
            f"(mirror_id={mirror_id}, ttl={ttl_seconds}s, source={original_name})"
        )

        # Broadcast mirror created event
        await self._websocket_manager.broadcast_mirror_event("mirror_created", mirror_info)

        return mirror_info

    def _prepare_mirror_spec(self, spec: dict, mirror_pod_name: str, original_pod_name: str,
                              namespace: str, pod_failure_id: int, mirror_id: str,
                              ttl_seconds: int, created_at: str):
        """Modify a pod spec dict to be a standalone mirror pod."""
        # Ensure metadata exists
        if "metadata" not in spec:
            spec["metadata"] = {}

        metadata = spec["metadata"]

        # Set name and namespace
        metadata["name"] = mirror_pod_name
        metadata["namespace"] = namespace

        # Strip ownerReferences so no controller fights with it
        metadata.pop("ownerReferences", None)
        metadata.pop("owner_references", None)

        # Strip fields that prevent re-creation
        metadata.pop("resourceVersion", None)
        metadata.pop("resource_version", None)
        metadata.pop("uid", None)
        metadata.pop("creationTimestamp", None)
        metadata.pop("creation_timestamp", None)
        metadata.pop("selfLink", None)
        metadata.pop("self_link", None)
        metadata.pop("managedFields", None)
        metadata.pop("managed_fields", None)
        metadata.pop("generateName", None)
        metadata.pop("generate_name", None)

        # Add mirror labels
        if "labels" not in metadata or metadata["labels"] is None:
            metadata["labels"] = {}
        metadata["labels"]["kure.io/mirror"] = "true"
        metadata["labels"]["kure.io/mirror-of"] = original_pod_name
        metadata["labels"]["kure.io/mirror-source-id"] = str(pod_failure_id)

        # Add mirror annotations
        if "annotations" not in metadata or metadata["annotations"] is None:
            metadata["annotations"] = {}
        metadata["annotations"]["kure.io/mirror-ttl"] = str(ttl_seconds)
        metadata["annotations"]["kure.io/mirror-created"] = created_at
        metadata["annotations"]["kure.io/mirror-id"] = mirror_id

        # Strip spec-level fields that prevent re-creation
        if "spec" in spec:
            spec["spec"].pop("nodeName", None)
            spec["spec"].pop("node_name", None)
            spec["spec"].pop("serviceAccountName", None)
            # Keep serviceAccount if set explicitly in original

        # Strip status
        spec.pop("status", None)

    async def get_mirror_status(self, mirror_id: str) -> dict:
        """Get the current status of a mirror pod from K8s API."""
        self._init_k8s_client()

        if mirror_id not in self._active_mirrors:
            raise ValueError(f"Mirror pod not found: {mirror_id}")

        info = self._active_mirrors[mirror_id]
        pod_name = info["mirror_pod_name"]
        namespace = info["namespace"]

        try:
            pod = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._k8s_core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            )
        except client.ApiException as e:
            if e.status == 404:
                # Pod was deleted externally
                self._active_mirrors.pop(mirror_id, None)
                raise ValueError(f"Mirror pod '{pod_name}' no longer exists in K8s")
            raise RuntimeError(f"Kubernetes API error: {e.reason}")

        phase = pod.status.phase if pod.status else "Unknown"

        # Update cached phase
        info["phase"] = phase

        # Collect conditions
        conditions = []
        if pod.status and pod.status.conditions:
            for c in pod.status.conditions:
                conditions.append({
                    "type": c.type,
                    "status": c.status,
                    "reason": c.reason or "",
                    "message": c.message or "",
                    "last_transition_time": c.last_transition_time.isoformat() if c.last_transition_time else None,
                })

        # Collect recent events
        events = []
        try:
            field_selector = f"involvedObject.name={pod_name},involvedObject.namespace={namespace}"
            event_list = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._k8s_core_v1.list_namespaced_event(
                    namespace=namespace,
                    field_selector=field_selector,
                    limit=20
                )
            )
            for ev in event_list.items:
                events.append({
                    "type": ev.type or "",
                    "reason": ev.reason or "",
                    "message": ev.message or "",
                    "timestamp": ev.last_timestamp.isoformat() if ev.last_timestamp else None,
                    "count": ev.count,
                })
        except Exception as e:
            logger.warning(f"Failed to fetch events for mirror pod {pod_name}: {e}")

        return {
            "mirror_id": mirror_id,
            "mirror_pod_name": pod_name,
            "namespace": namespace,
            "phase": phase,
            "conditions": conditions,
            "events": events,
            "created_at": info["created_at"],
            "expires_at": info["expires_at"],
        }

    async def delete_mirror(self, mirror_id: str) -> bool:
        """Delete a mirror pod from K8s and remove from tracking."""
        self._init_k8s_client()

        if mirror_id not in self._active_mirrors:
            raise ValueError(f"Mirror pod not found: {mirror_id}")

        info = self._active_mirrors[mirror_id]
        pod_name = info["mirror_pod_name"]
        namespace = info["namespace"]

        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._k8s_core_v1.delete_namespaced_pod(
                    name=pod_name,
                    namespace=namespace,
                    grace_period_seconds=0
                )
            )
            logger.info(f"Deleted mirror pod: {pod_name} in {namespace}")
        except client.ApiException as e:
            if e.status == 404:
                logger.warning(f"Mirror pod already deleted from K8s: {pod_name}")
            else:
                raise RuntimeError(f"Failed to delete mirror pod: {e.reason}")

        # Remove from tracking
        removed_info = self._active_mirrors.pop(mirror_id, None)

        # Broadcast mirror deleted event
        if removed_info:
            await self._websocket_manager.broadcast_mirror_event("mirror_deleted", {
                "mirror_id": mirror_id,
                "mirror_pod_name": pod_name,
                "namespace": namespace,
            })

        return True

    def list_active_mirrors(self) -> list:
        """Return a list of all active mirror pods."""
        return list(self._active_mirrors.values())

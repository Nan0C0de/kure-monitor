"""Diagram (topology) API routes.

These endpoints feed the Diagram tab in the UI. The graph is computed
deterministically from the K8s API by ``services.topology_service``; no LLM
involvement here.
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from models.models import DiagramResponse
from services.topology_service import (
    ALL_DIAGRAM_KINDS,
    WORKLOAD_ROOT_KINDS,
    K8S_AVAILABLE,
    TopologyService,
    normalise_kind,
)

from .deps import RouterDeps

logger = logging.getLogger(__name__)


def create_diagram_router(deps: RouterDeps) -> APIRouter:
    """Diagram (topology) endpoints. Authenticated via the parent router's
    ``require_read`` dependency."""
    router = APIRouter()
    # Prefer the shared TopologyService from deps so it's a singleton
    # across the app (and shared with AdviceEngine). Fall back to a fresh
    # instance for back-compat (older tests construct deps without it).
    service = getattr(deps, "topology_service", None) or TopologyService()

    @router.get("/diagram/namespaces")
    async def list_diagram_namespaces(kind: str | None = Query(None)):
        if not K8S_AVAILABLE:
            raise HTTPException(
                status_code=503, detail="Kubernetes client not available"
            )
        try:
            namespaces = await service.list_namespaces(kind=kind)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to list namespaces: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")
        return {"namespaces": namespaces}

    @router.get("/diagram/namespace/{ns}", response_model=DiagramResponse)
    async def get_namespace_diagram(ns: str):
        if not K8S_AVAILABLE:
            raise HTTPException(
                status_code=503, detail="Kubernetes client not available"
            )
        try:
            return await service.get_namespace_diagram(ns)
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to build namespace diagram for {ns}: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.get("/diagram/workloads/{ns}/{kind}")
    async def list_workloads(ns: str, kind: str):
        if not K8S_AVAILABLE:
            raise HTTPException(
                status_code=503, detail="Kubernetes client not available"
            )
        normalised = normalise_kind(kind)
        if normalised not in WORKLOAD_ROOT_KINDS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Workload kind must be one of "
                    f"{sorted(WORKLOAD_ROOT_KINDS)}; got '{kind}'"
                ),
            )
        try:
            names = await service.list_workloads(ns, normalised)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to list {normalised} in {ns}: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")
        return {"workloads": names}

    @router.get("/diagram/workload/{ns}/{kind}/{name}", response_model=DiagramResponse)
    async def get_workload_diagram(ns: str, kind: str, name: str):
        if not K8S_AVAILABLE:
            raise HTTPException(
                status_code=503, detail="Kubernetes client not available"
            )
        normalised = normalise_kind(kind)
        if normalised not in WORKLOAD_ROOT_KINDS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Workload kind must be one of "
                    f"{sorted(WORKLOAD_ROOT_KINDS)}; got '{kind}'"
                ),
            )
        try:
            return await service.get_workload_diagram(ns, normalised, name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            # The kubernetes client raises ApiException; map 404 from K8s through.
            try:
                from kubernetes.client import ApiException  # type: ignore

                if isinstance(e, ApiException) and e.status == 404:
                    raise HTTPException(
                        status_code=404,
                        detail=f"{normalised} '{name}' not found in namespace '{ns}'",
                    )
            except ImportError:
                pass
            logger.error(
                f"Failed to build workload diagram for {ns}/{kind}/{name}: {e}"
            )
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.get("/diagram/manifest/{ns}/{kind}/{name}")
    async def get_diagram_manifest(ns: str, kind: str, name: str):
        if not K8S_AVAILABLE:
            raise HTTPException(
                status_code=503, detail="Kubernetes client not available"
            )

        normalised = normalise_kind(kind)
        if normalised is None or normalised not in ALL_DIAGRAM_KINDS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported kind '{kind}'",
            )
        if normalised == "Secret":
            raise HTTPException(
                status_code=403,
                detail=(
                    "Secret manifests are not exposed by Kure Monitor. "
                    "The diagram references Secrets via workload spec only."
                ),
            )

        try:
            manifest_yaml = await service.get_manifest_yaml(ns, normalised, name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            try:
                from kubernetes.client import ApiException  # type: ignore

                if isinstance(e, ApiException):
                    if e.status == 404:
                        raise HTTPException(
                            status_code=404,
                            detail=f"{normalised} '{name}' not found in namespace '{ns}'",
                        )
                    raise HTTPException(status_code=e.status, detail=str(e.reason))
            except ImportError:
                pass
            logger.error(f"Failed to fetch manifest for {ns}/{normalised}/{name}: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

        return {
            "manifest": manifest_yaml,
            "kind": normalised,
            "name": name,
            "namespace": ns,
        }

    # -- RBAC ---------------------------------------------------------------

    @router.get("/diagram/roles")
    async def list_diagram_roles():
        if not K8S_AVAILABLE:
            raise HTTPException(
                status_code=503, detail="Kubernetes client not available"
            )
        try:
            return await service.list_roles()
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to list roles/clusterroles: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.get("/diagram/role/{namespace}/{name}", response_model=DiagramResponse)
    async def get_role_diagram(namespace: str, name: str):
        if not K8S_AVAILABLE:
            raise HTTPException(
                status_code=503, detail="Kubernetes client not available"
            )
        try:
            return await service.get_role_diagram(namespace, name)
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            try:
                from kubernetes.client import ApiException  # type: ignore

                if isinstance(e, ApiException) and e.status == 404:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Role '{name}' not found in namespace '{namespace}'",
                    )
            except ImportError:
                pass
            logger.error(f"Failed to build role diagram for {namespace}/{name}: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.get("/diagram/clusterrole/{name}", response_model=DiagramResponse)
    async def get_cluster_role_diagram(name: str):
        if not K8S_AVAILABLE:
            raise HTTPException(
                status_code=503, detail="Kubernetes client not available"
            )
        try:
            return await service.get_cluster_role_diagram(name)
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            try:
                from kubernetes.client import ApiException  # type: ignore

                if isinstance(e, ApiException) and e.status == 404:
                    raise HTTPException(
                        status_code=404,
                        detail=f"ClusterRole '{name}' not found",
                    )
            except ImportError:
                pass
            logger.error(f"Failed to build clusterrole diagram for {name}: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    return router

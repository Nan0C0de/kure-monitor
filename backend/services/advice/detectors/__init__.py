"""Detector registry for the AI Advice subsystem.

``AdviceEngine`` iterates :data:`ALL_DETECTORS`, instantiates each
class once per scan, and awaits :meth:`PatternDetector.detect`.
"""

from __future__ import annotations

from typing import List, Type

from .aggressive_liveness_probe import AggressiveLivenessProbe
from .all_to_all_replicas import AllToAllReplicas
from .base import PatternDetector
from .cronjob_overlap_risk import CronJobOverlapRisk
from .db_connections_per_replica import DbConnectionsPerReplica
from .deployment_hpa_burst_mismatch import DeploymentHpaBurstMismatch
from .ephemeral_processes import EphemeralProcesses
from .fan_out_pattern import FanOutPattern
from .hpa_target_mismatch import HpaTargetMismatch
from .ingress_missing_service import IngressMissingService
from .job_no_bounds import JobNoBounds
from .missing_pdb import MissingPdb
from .missing_readiness_probe import MissingReadinessProbe
from .mutable_image_tag import MutableImageTag
from .netpol_default_deny_no_allow import NetpolDefaultDenyNoAllow
from .ports_but_no_service import PortsButNoService
from .referenced_config_missing import ReferencedConfigMissing
from .replicas_over_hpa_max import ReplicasOverHpaMax
from .service_selector_no_match import ServiceSelectorNoMatch
from .sidecar_no_limits import SidecarNoLimits
from .single_node_pinning import SingleNodePinning
from .startup_io_amplification import StartupIoAmplification
from .statefulset_emptydir_data import StatefulSetEmptyDirData
from .websocket_on_deployment import WebSocketOnDeployment

#: Ordered list of detector classes the engine should run.
ALL_DETECTORS: List[Type[PatternDetector]] = [
    # Original 7
    DeploymentHpaBurstMismatch,
    DbConnectionsPerReplica,
    StartupIoAmplification,
    FanOutPattern,
    WebSocketOnDeployment,
    AllToAllReplicas,
    EphemeralProcesses,
    # Already-shipped 5
    MissingPdb,
    MissingReadinessProbe,
    AggressiveLivenessProbe,
    StatefulSetEmptyDirData,
    HpaTargetMismatch,
    # New 11
    ReplicasOverHpaMax,
    SingleNodePinning,
    PortsButNoService,
    MutableImageTag,
    SidecarNoLimits,
    CronJobOverlapRisk,
    JobNoBounds,
    ServiceSelectorNoMatch,
    IngressMissingService,
    NetpolDefaultDenyNoAllow,
    ReferencedConfigMissing,
]

__all__ = [
    "PatternDetector",
    "ALL_DETECTORS",
    "DeploymentHpaBurstMismatch",
    "DbConnectionsPerReplica",
    "StartupIoAmplification",
    "FanOutPattern",
    "WebSocketOnDeployment",
    "AllToAllReplicas",
    "EphemeralProcesses",
    "MissingPdb",
    "MissingReadinessProbe",
    "AggressiveLivenessProbe",
    "StatefulSetEmptyDirData",
    "HpaTargetMismatch",
    "ReplicasOverHpaMax",
    "SingleNodePinning",
    "PortsButNoService",
    "MutableImageTag",
    "SidecarNoLimits",
    "CronJobOverlapRisk",
    "JobNoBounds",
    "ServiceSelectorNoMatch",
    "IngressMissingService",
    "NetpolDefaultDenyNoAllow",
    "ReferencedConfigMissing",
]

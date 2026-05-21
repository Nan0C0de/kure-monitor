"""Detector registry for the AI Advice subsystem.

``AdviceEngine`` iterates :data:`ALL_DETECTORS`, instantiates each
class once per scan, and awaits :meth:`PatternDetector.detect`.
"""

from __future__ import annotations

from typing import List, Type

from .aggressive_liveness_probe import AggressiveLivenessProbe
from .all_to_all_replicas import AllToAllReplicas
from .base import PatternDetector
from .cpu_limit_throttling_risk import CpuLimitThrottlingRisk
from .cronjob_overlap_risk import CronJobOverlapRisk
from .db_connections_per_replica import DbConnectionsPerReplica
from .deployment_hpa_burst_mismatch import DeploymentHpaBurstMismatch
from .ephemeral_processes import EphemeralProcesses
from .fan_out_pattern import FanOutPattern
from .hpa_target_mismatch import HpaTargetMismatch
from .image_pull_always_with_mutable_tag import ImagePullAlwaysWithMutableTag
from .ingress_host_collision import IngressHostCollision
from .ingress_missing_service import IngressMissingService
from .job_no_bounds import JobNoBounds
from .job_restart_policy_mismatch import JobRestartPolicyMismatch
from .missing_pdb import MissingPdb
from .missing_pod_anti_affinity_replicas import MissingPodAntiAffinityReplicas
from .missing_priority_class import MissingPriorityClass
from .missing_readiness_probe import MissingReadinessProbe
from .missing_requests_limits import MissingRequestsLimits
from .missing_topology_spread_constraints import MissingTopologySpreadConstraints
from .mutable_image_tag import MutableImageTag
from .netpol_default_deny_no_allow import NetpolDefaultDenyNoAllow
from .networkpolicy_selects_nothing import NetworkPolicySelectsNothing
from .oom_prone_memory_headroom import OomProneMemoryHeadroom
from .ports_but_no_service import PortsButNoService
from .prestop_missing_short_grace import PreStopMissingShortGrace
from .pvc_no_storage_class import PvcNoStorageClass
from .replicas_over_hpa_max import ReplicasOverHpaMax
from .requests_equal_limits_burstable import RequestsEqualLimitsBurstable
from .rwo_pvc_multi_replica import RwoPvcMultiReplica
from .service_selector_no_match import ServiceSelectorNoMatch
from .service_target_port_mismatch import ServiceTargetPortMismatch
from .sidecar_no_limits import SidecarNoLimits
from .single_node_pinning import SingleNodePinning
from .single_replica_behind_service import SingleReplicaBehindService
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
    # Previously-added 10
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
    # New 16
    MissingRequestsLimits,
    RequestsEqualLimitsBurstable,
    CpuLimitThrottlingRisk,
    OomProneMemoryHeadroom,
    MissingPodAntiAffinityReplicas,
    MissingTopologySpreadConstraints,
    SingleReplicaBehindService,
    MissingPriorityClass,
    ServiceTargetPortMismatch,
    IngressHostCollision,
    NetworkPolicySelectsNothing,
    PreStopMissingShortGrace,
    JobRestartPolicyMismatch,
    ImagePullAlwaysWithMutableTag,
    PvcNoStorageClass,
    RwoPvcMultiReplica,
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
    "MissingRequestsLimits",
    "RequestsEqualLimitsBurstable",
    "CpuLimitThrottlingRisk",
    "OomProneMemoryHeadroom",
    "MissingPodAntiAffinityReplicas",
    "MissingTopologySpreadConstraints",
    "SingleReplicaBehindService",
    "MissingPriorityClass",
    "ServiceTargetPortMismatch",
    "IngressHostCollision",
    "NetworkPolicySelectsNothing",
    "PreStopMissingShortGrace",
    "JobRestartPolicyMismatch",
    "ImagePullAlwaysWithMutableTag",
    "PvcNoStorageClass",
    "RwoPvcMultiReplica",
]

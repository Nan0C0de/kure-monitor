"""Detector registry for the AI Advice subsystem.

``AdviceEngine`` iterates :data:`ALL_DETECTORS`, instantiates each
class once per scan, and awaits :meth:`PatternDetector.detect`.
"""

from __future__ import annotations

from typing import List, Type

from .all_to_all_replicas import AllToAllReplicas
from .base import PatternDetector
from .db_connections_per_replica import DbConnectionsPerReplica
from .deployment_hpa_burst_mismatch import DeploymentHpaBurstMismatch
from .ephemeral_processes import EphemeralProcesses
from .fan_out_pattern import FanOutPattern
from .startup_io_amplification import StartupIoAmplification
from .websocket_on_deployment import WebSocketOnDeployment

#: Ordered list of detector classes the engine should run.
ALL_DETECTORS: List[Type[PatternDetector]] = [
    DeploymentHpaBurstMismatch,
    DbConnectionsPerReplica,
    StartupIoAmplification,
    FanOutPattern,
    WebSocketOnDeployment,
    AllToAllReplicas,
    EphemeralProcesses,
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
]

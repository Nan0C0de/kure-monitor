"""Tests for services.advice.findings."""

import json

import pytest

from models.models import AdviceFinding
from services.advice.detectors.base import PatternDetector
from services.advice.findings import Finding, Severity, WorkloadContext, make_finding


def _base_finding(**overrides) -> Finding:
    """Helper: a fully-populated Finding suitable for most tests."""
    fields = dict(
        detector_id="deployment-should-be-daemonset",
        severity=Severity.MEDIUM,
        category="workload-pattern",
        title="Deployment should be a DaemonSet",
        summary="Workload runs one pod per node via anti-affinity; DaemonSet fits better.",
        resource_kind="Deployment",
        resource_name="node-exporter",
        namespace="monitoring",
        evidence={
            "replicas": 3,
            "uses_hostpath": True,
            "anti_affinity_topology_key": "kubernetes.io/hostname",
        },
        recommended_change="Convert to DaemonSet and remove the HPA.",
        confidence=0.85,
    )
    fields.update(overrides)
    return Finding(**fields)


class _NodeExporterDetector(PatternDetector):
    """Fixture detector used only by make_finding tests."""

    id = "deployment-should-be-daemonset"
    default_severity = Severity.MEDIUM
    category = "workload-pattern"

    async def detect(self, ctx: WorkloadContext):  # pragma: no cover - unused
        return []


class TestFinding:
    def test_construction_with_required_fields(self):
        finding = _base_finding()
        assert finding.detector_id == "deployment-should-be-daemonset"
        assert finding.severity is Severity.MEDIUM
        assert finding.namespace == "monitoring"
        assert finding.explanation is None

    def test_missing_required_field_raises_type_error(self):
        with pytest.raises(TypeError):
            Finding(  # type: ignore[call-arg]
                detector_id="x",
                severity=Severity.LOW,
                category="c",
                title="t",
                summary="s",
                resource_kind="Pod",
                resource_name="p",
                namespace="default",
                # evidence intentionally omitted
                recommended_change="r",
                confidence=0.1,
            )

    def test_with_explanation_returns_new_instance(self):
        original = _base_finding()
        updated = original.with_explanation("## Why this matters\nIt does.")

        assert updated is not original
        assert updated.explanation == "## Why this matters\nIt does."
        # Original is unchanged (frozen + replace returns a new instance).
        assert original.explanation is None

    def test_frozen_disallows_mutation(self):
        finding = _base_finding()
        with pytest.raises(Exception):
            # FrozenInstanceError on python 3.12; covered by broad Exception.
            finding.explanation = "nope"  # type: ignore[misc]


class TestToWire:
    def test_to_wire_produces_advice_finding(self):
        finding = _base_finding(explanation="hi")
        wire = finding.to_wire()

        assert isinstance(wire, AdviceFinding)
        assert wire.detector_id == finding.detector_id
        assert wire.severity == "medium"
        assert wire.category == finding.category
        assert wire.title == finding.title
        assert wire.summary == finding.summary
        assert wire.resource_kind == finding.resource_kind
        assert wire.resource_name == finding.resource_name
        assert wire.namespace == finding.namespace
        assert wire.evidence == finding.evidence
        assert wire.recommended_change == finding.recommended_change
        assert wire.confidence == finding.confidence
        assert wire.explanation == "hi"

    def test_severity_serializes_as_string_value(self):
        finding = _base_finding(severity=Severity.HIGH)
        wire = finding.to_wire()
        dumped = json.loads(wire.model_dump_json())
        assert dumped["severity"] == "high"


class TestMakeFinding:
    def test_severity_falls_back_to_detector_default(self):
        detector = _NodeExporterDetector()
        finding = make_finding(
            detector,
            resource_kind="Deployment",
            resource_name="node-exporter",
            namespace="monitoring",
            title="t",
            summary="s",
            evidence={"replicas": 3},
            recommended_change="r",
            confidence=0.9,
        )
        assert finding.severity is Severity.MEDIUM  # from detector default
        assert finding.detector_id == "deployment-should-be-daemonset"
        assert finding.category == "workload-pattern"

    def test_explicit_severity_overrides_default(self):
        detector = _NodeExporterDetector()
        finding = make_finding(
            detector,
            resource_kind="Deployment",
            resource_name="node-exporter",
            namespace="monitoring",
            title="t",
            summary="s",
            evidence={"replicas": 3},
            recommended_change="r",
            confidence=0.9,
            severity=Severity.HIGH,
        )
        assert finding.severity is Severity.HIGH


class TestWorkloadContext:
    def test_defaults_are_empty(self):
        ctx = WorkloadContext(
            namespace="default",
            workload_kind=None,
            workload_name=None,
            pod_name=None,
        )
        assert ctx.manifests == {}
        assert ctx.pods == []

    def test_frozen(self):
        ctx = WorkloadContext(
            namespace="default",
            workload_kind=None,
            workload_name=None,
            pod_name=None,
        )
        with pytest.raises(Exception):
            ctx.namespace = "other"  # type: ignore[misc]

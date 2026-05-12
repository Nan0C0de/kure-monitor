"""Tests for services.advice.detectors.base and the empty detector registry."""

import pytest

from services.advice.detectors import ALL_DETECTORS
from services.advice.detectors.base import PatternDetector
from services.advice.findings import Finding, Severity, WorkloadContext


class _FixedDetector(PatternDetector):
    """Trivial concrete subclass: emits one hardcoded finding."""

    id = "fixed-test-detector"
    default_severity = Severity.LOW
    category = "test"

    async def detect(self, ctx: WorkloadContext):
        return [
            Finding(
                detector_id=self.id,
                severity=self.default_severity,
                category=self.category,
                title="Fixed",
                summary="A fixed finding for the unit test.",
                resource_kind="Pod",
                resource_name="example",
                namespace=ctx.namespace,
                evidence={"hello": "world"},
                recommended_change="Do the thing.",
                confidence=1.0,
            )
        ]


class TestPatternDetectorBase:
    @pytest.mark.asyncio
    async def test_subclass_detect_returns_findings(self):
        detector = _FixedDetector()
        ctx = WorkloadContext(
            namespace="ns-1",
            workload_kind="Pod",
            workload_name="example",
            pod_name="example",
        )

        findings = await detector.detect(ctx)

        assert len(findings) == 1
        finding = findings[0]
        assert finding.detector_id == "fixed-test-detector"
        assert finding.severity is Severity.LOW
        assert finding.namespace == "ns-1"

    def test_cannot_instantiate_abstract_base(self):
        with pytest.raises(TypeError):
            PatternDetector()  # type: ignore[abstract]


class TestRegistry:
    def test_all_detectors_registered(self):
        assert isinstance(ALL_DETECTORS, list)
        ids = {d.id for d in ALL_DETECTORS}
        assert {
            "deployment-hpa-burst-mismatch",
            "db-connections-per-replica",
            "startup-io-amplification",
            "fan-out-pattern",
            "websocket-on-deployment",
            "all-to-all-replicas",
            "ephemeral-processes",
        } <= ids

    def test_registry_entries_are_pattern_detector_subclasses(self):
        for cls in ALL_DETECTORS:
            assert issubclass(cls, PatternDetector)

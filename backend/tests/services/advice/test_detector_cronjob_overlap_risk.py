"""Tests for ``CronJobOverlapRisk``."""

from __future__ import annotations

import pytest

from services.advice.detectors.cronjob_overlap_risk import CronJobOverlapRisk
from services.advice.findings import WorkloadContext


def _ctx(manifests):
    return WorkloadContext(
        namespace="ns",
        workload_kind=None,
        workload_name=None,
        pod_name=None,
        manifests=manifests,
        pods=[],
    )


def _cj(name, policy=None, schedule="*/5 * * * *"):
    spec = {"schedule": schedule, "jobTemplate": {"spec": {}}}
    if policy is not None:
        spec["concurrencyPolicy"] = policy
    return {
        "kind": "CronJob",
        "metadata": {"name": name},
        "spec": spec,
    }


@pytest.mark.asyncio
async def test_positive_policy_unset():
    findings = await CronJobOverlapRisk().detect(
        _ctx({("CronJob", "nightly"): _cj("nightly")})
    )
    assert len(findings) == 1
    assert findings[0].detector_id == "cronjob-overlap-risk"
    assert findings[0].evidence["concurrency_policy"] == "Allow"


@pytest.mark.asyncio
async def test_positive_policy_allow():
    findings = await CronJobOverlapRisk().detect(
        _ctx({("CronJob", "nightly"): _cj("nightly", policy="Allow")})
    )
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_negative_policy_forbid():
    findings = await CronJobOverlapRisk().detect(
        _ctx({("CronJob", "nightly"): _cj("nightly", policy="Forbid")})
    )
    assert findings == []


@pytest.mark.asyncio
async def test_negative_policy_replace():
    findings = await CronJobOverlapRisk().detect(
        _ctx({("CronJob", "nightly"): _cj("nightly", policy="Replace")})
    )
    assert findings == []


@pytest.mark.asyncio
async def test_edge_malformed_cronjob():
    findings = await CronJobOverlapRisk().detect(
        _ctx({("CronJob", "bad"): {"kind": "CronJob"}})
    )
    assert findings == []

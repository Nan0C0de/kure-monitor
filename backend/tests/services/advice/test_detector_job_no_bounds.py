"""Tests for ``JobNoBounds``."""

from __future__ import annotations

import pytest

from services.advice.detectors.job_no_bounds import JobNoBounds
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


def _job(name, spec):
    return {"kind": "Job", "metadata": {"name": name}, "spec": spec}


def _cj(name, job_spec):
    return {
        "kind": "CronJob",
        "metadata": {"name": name},
        "spec": {"jobTemplate": {"spec": job_spec}},
    }


@pytest.mark.asyncio
async def test_positive_job_no_deadline_no_backoff():
    findings = await JobNoBounds().detect(_ctx({("Job", "j"): _job("j", {})}))
    assert len(findings) == 1
    assert findings[0].detector_id == "job-no-bounds"
    assert findings[0].evidence["active_deadline_seconds"] is None
    assert findings[0].evidence["backoff_limit"] is None


@pytest.mark.asyncio
async def test_positive_high_backoff():
    findings = await JobNoBounds().detect(
        _ctx({("Job", "j"): _job("j", {"backoffLimit": 10})})
    )
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_negative_has_deadline():
    findings = await JobNoBounds().detect(
        _ctx({("Job", "j"): _job("j", {"activeDeadlineSeconds": 600})})
    )
    assert findings == []


@pytest.mark.asyncio
async def test_negative_low_backoff():
    findings = await JobNoBounds().detect(
        _ctx({("Job", "j"): _job("j", {"backoffLimit": 2})})
    )
    assert findings == []


@pytest.mark.asyncio
async def test_edge_cronjob_template_inspected():
    findings = await JobNoBounds().detect(
        _ctx({("CronJob", "nightly"): _cj("nightly", {"backoffLimit": 6})})
    )
    assert len(findings) == 1
    assert findings[0].resource_kind == "CronJob"
    assert findings[0].resource_name == "nightly"

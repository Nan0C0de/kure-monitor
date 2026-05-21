"""Tests for ``JobRestartPolicyMismatch``."""

from __future__ import annotations

import pytest

from services.advice.detectors.job_restart_policy_mismatch import (
    JobRestartPolicyMismatch,
)
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


def _job(name, restart_policy):
    spec = {"containers": [{"name": "c", "image": "busybox"}]}
    if restart_policy is not None:
        spec["restartPolicy"] = restart_policy
    return {
        "kind": "Job",
        "metadata": {"name": name},
        "spec": {"template": {"spec": spec}},
    }


def _cronjob(name, restart_policy):
    return {
        "kind": "CronJob",
        "metadata": {"name": name},
        "spec": {
            "schedule": "* * * * *",
            "jobTemplate": {
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [{"name": "c", "image": "busybox"}],
                            "restartPolicy": restart_policy,
                        }
                    }
                }
            },
        },
    }


@pytest.mark.asyncio
async def test_positive_always_policy_job():
    findings = await JobRestartPolicyMismatch().detect(
        _ctx({("Job", "j"): _job("j", "Always")})
    )
    assert len(findings) == 1
    assert findings[0].evidence["restart_policy"] == "Always"


@pytest.mark.asyncio
async def test_positive_missing_policy_job():
    findings = await JobRestartPolicyMismatch().detect(
        _ctx({("Job", "j"): _job("j", None)})
    )
    assert len(findings) == 1
    assert findings[0].evidence["restart_policy"] is None


@pytest.mark.asyncio
async def test_negative_on_failure():
    findings = await JobRestartPolicyMismatch().detect(
        _ctx({("Job", "j"): _job("j", "OnFailure")})
    )
    assert findings == []


@pytest.mark.asyncio
async def test_edge_cronjob_with_bad_policy():
    findings = await JobRestartPolicyMismatch().detect(
        _ctx({("CronJob", "c"): _cronjob("c", "Always")})
    )
    assert len(findings) == 1
    assert findings[0].resource_kind == "CronJob"

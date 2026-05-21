"""Tests for ``PvcNoStorageClass``."""

from __future__ import annotations

import pytest

from services.advice.detectors.pvc_no_storage_class import PvcNoStorageClass
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


def _pvc(name, spec):
    return {
        "kind": "PersistentVolumeClaim",
        "metadata": {"name": name},
        "spec": spec,
    }


@pytest.mark.asyncio
async def test_positive_no_class_no_volume():
    manifests = {
        ("PersistentVolumeClaim", "data"): _pvc(
            "data",
            {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "1Gi"}},
            },
        )
    }
    findings = await PvcNoStorageClass().detect(_ctx(manifests))
    assert len(findings) == 1
    assert findings[0].confidence == 0.6


@pytest.mark.asyncio
async def test_negative_has_storage_class():
    manifests = {
        ("PersistentVolumeClaim", "data"): _pvc(
            "data",
            {
                "storageClassName": "ssd",
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "1Gi"}},
            },
        )
    }
    findings = await PvcNoStorageClass().detect(_ctx(manifests))
    assert findings == []


@pytest.mark.asyncio
async def test_negative_has_volume_name():
    manifests = {
        ("PersistentVolumeClaim", "data"): _pvc(
            "data",
            {
                "volumeName": "pv-static",
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "1Gi"}},
            },
        )
    }
    findings = await PvcNoStorageClass().detect(_ctx(manifests))
    assert findings == []

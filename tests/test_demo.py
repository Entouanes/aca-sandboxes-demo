import threading

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.manager import Manager


class Sandbox:
    sandbox_id = "test-sandbox"
    deleted = False

    def delete(self):
        self.deleted = True


class Provider:
    def __init__(self, fail=False):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.sandbox = Sandbox()
        self.fail = fail
        self.created = False

    def create(self):
        self.created = True
        return self.sandbox

    def discover(self):
        return [self.sandbox] if self.created and not self.sandbox.deleted else []

    def probe(self, sandbox):
        if self.fail:
            raise RuntimeError("Sandbox is suspended")
        return "copilot 1.0"

    def initialize(self, sandbox):
        self.entered.set()
        self.release.wait(2)
        if self.fail:
            raise RuntimeError("Copilot installation failed")
        return "copilot 1.0"


def test_real_readiness_progression_and_cleanup():
    provider = Provider()
    manager = Manager(provider, limit=12)
    initial = manager.start(1)
    assert initial["sandboxes"][0]["state"] == "provisioning"
    assert provider.entered.wait(2)
    assert manager.snapshot()["sandboxes"][0]["state"] == "initializing"
    with pytest.raises(ValueError, match="clean up"):
        manager.start(1)
    provider.release.set()
    manager.wait()
    item = manager.snapshot()["sandboxes"][0]
    assert item["state"] == "ready"
    assert item["version"] == "copilot 1.0"
    assert [entry["state"] for entry in item["history"]] == [
        "provisioning",
        "initializing",
        "ready",
    ]
    manager.cleanup()
    assert provider.sandbox.deleted
    assert manager.snapshot()["sandboxes"] == []
    manager.close()


def test_initialization_failure_is_visible_and_still_cleanable():
    provider = Provider(fail=True)
    provider.release.set()
    manager = Manager(provider)
    manager.start(1)
    manager.wait()
    item = manager.snapshot()["sandboxes"][0]
    assert item["state"] == "error"
    assert "installation failed" in item["message"]
    manager.cleanup()
    assert provider.sandbox.deleted
    manager.close()


@pytest.mark.parametrize("count", [0, -1, 51, True, 1.5])
def test_invalid_counts_are_rejected(count):
    manager = Manager(Provider())
    with pytest.raises(ValueError):
        manager.start(count)
    manager.close()


def test_api_requires_key_and_validates_count():
    provider = Provider()
    provider.release.set()
    manager = Manager(provider, limit=12)
    with TestClient(create_app(manager, key="demo-secret")) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/sandboxes").status_code == 401
        headers = {"X-Demo-Key": "demo-secret"}
        assert client.post("/api/sandboxes", json={"count": 0}, headers=headers).status_code == 422
        assert (
            client.post("/api/sandboxes", json={"count": 1.5}, headers=headers).status_code == 422
        )
        assert client.post("/api/sandboxes", json={"count": 13}, headers=headers).status_code == 409
        response = client.post("/api/sandboxes", json={"count": 2}, headers=headers)
        assert response.status_code == 202
        assert len(response.json()["sandboxes"]) == 2
        manager.wait()
        assert client.get("/api/sandboxes", headers=headers).json()["counts"]["ready"] == 2
        assert client.delete("/api/sandboxes", headers=headers).status_code == 200


def test_cleanup_failure_preserves_resource_for_retry():
    provider = Provider()
    provider.release.set()
    manager = Manager(provider)
    manager.start(1)
    manager.wait()
    original = provider.sandbox.delete
    provider.sandbox.delete = lambda: (_ for _ in ()).throw(RuntimeError("delete failed"))
    with pytest.raises(RuntimeError, match="delete failed"):
        manager.cleanup()
    assert manager.snapshot()["sandboxes"][0]["state"] == "error"
    provider.sandbox.delete = original
    manager.cleanup()
    manager.close()


def test_existing_azure_sandboxes_are_recovered_after_controller_restart():
    provider = Provider()
    provider.created = True
    manager = Manager(provider)
    manager.reconcile()
    item = manager.snapshot()["sandboxes"][0]
    assert item["sandboxName"] == provider.sandbox.sandbox_id
    assert item["state"] == "ready"
    manager.cleanup()
    manager.close()


def test_probe_failure_removes_stale_green_readiness():
    provider = Provider()
    provider.release.set()
    manager = Manager(provider)
    manager.start(1)
    manager.wait()
    provider.fail = True
    manager.reconcile()
    assert manager.snapshot()["sandboxes"][0]["state"] == "error"
    assert "suspended" in manager.snapshot()["sandboxes"][0]["message"]
    manager.close()


def test_cleanup_discovers_sandbox_left_by_failed_creation_poller():
    provider = Provider()

    def failed_create():
        provider.created = True
        raise RuntimeError("Timed out waiting for Azure")

    provider.create = failed_create
    manager = Manager(provider)
    manager.start(1)
    manager.wait()
    manager.cleanup()
    assert provider.sandbox.deleted
    manager.close()


def test_inventory_failure_blocks_launch_instead_of_silently_ignoring_resources():
    provider = Provider()
    provider.discover = lambda: (_ for _ in ()).throw(RuntimeError("Azure permission denied"))
    manager = Manager(provider)
    manager.reconcile()
    assert "permission denied" in manager.snapshot()["systemError"]
    with pytest.raises(ValueError, match="inventory"):
        manager.start(1)
    manager.close()

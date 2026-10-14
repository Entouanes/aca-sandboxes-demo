from types import SimpleNamespace

import pytest

from app.providers import AzureProvider, AzureSandbox


class Client:
    sandbox_id = "azure-id"

    def __init__(self, exit_code=0, state="Running"):
        self.result = SimpleNamespace(exit_code=exit_code, stdout="1.0.97\n", stderr="failed")
        self.state = state
        self.commands = []

    def exec(self, command):
        self.commands.append(command)
        return self.result

    def get(self):
        return SimpleNamespace(state=self.state)


def test_azure_readiness_requires_successful_command():
    provider = AzureProvider(client=object())
    client = Client(exit_code=1)
    with pytest.raises(RuntimeError, match="exited 1"):
        provider.initialize(AzureSandbox(client))
    assert "timeout 240" in client.commands[0]


def test_azure_probe_rejects_suspended_sandboxes_without_resuming_them():
    provider = AzureProvider(client=object())
    client = Client(state="Suspended")
    with pytest.raises(RuntimeError, match="Suspended"):
        provider.probe(AzureSandbox(client))
    assert not client.commands


def test_azure_probe_checks_marker_and_copilot_version():
    provider = AzureProvider(client=object())
    client = Client()
    assert provider.probe(AzureSandbox(client)) == "1.0.97"
    assert "copilot --version" in client.commands[0]
    assert ".launchpad-ready" in client.commands[0]


def test_copilot_update_notice_is_not_mistaken_for_version():
    provider = AzureProvider(client=object())
    client = Client()
    client.result.stdout = (
        "GitHub Copilot CLI 1.0.97.\nRun 'copilot update' to check for updates.\n"
    )
    assert provider.initialize(AzureSandbox(client)) == "GitHub Copilot CLI 1.0.97."

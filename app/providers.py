import os
import shlex
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from azure.containerapps.sandbox import SandboxClient, SandboxGroupClient, endpoint_for_region
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential

BOOTSTRAP = Path(__file__).resolve().parent / "bootstrap.sh"
PROBE = (
    'export PATH="$HOME/.local/share/node/bin:$HOME/.local/bin:$PATH"; '
    'test -f "$HOME/.launchpad-ready" && timeout 15 copilot --version'
)


@dataclass
class AzureSandbox:
    client: SandboxClient

    @property
    def sandbox_id(self) -> str:
        return self.client.sandbox_id

    def delete(self) -> None:
        try:
            self.client.begin_delete(polling_timeout=120).result()
        except ResourceNotFoundError:
            # A resource deleted through the portal is already cleaned up.
            return


class AzureProvider:
    def __init__(self, client: SandboxGroupClient | None = None):
        if client is not None:
            self.client = client
            return
        self.credential = DefaultAzureCredential(
            managed_identity_client_id=os.getenv("AZURE_CLIENT_ID")
        )
        self.client = SandboxGroupClient(
            endpoint_for_region(os.environ["AZURE_LOCATION"]),
            self.credential,
            subscription_id=os.environ["AZURE_SUBSCRIPTION_ID"],
            resource_group=os.environ["AZURE_RESOURCE_GROUP"],
            sandbox_group=os.environ["AZURE_SANDBOX_GROUP"],
            connection_timeout=15,
            read_timeout=300,
        )

    def create(self):
        return AzureSandbox(
            self.client.begin_create_sandbox(
                disk="ubuntu",
                cpu="1000m",
                memory="2048Mi",
                auto_suspend_seconds=1800,
                labels={"app": "sandbox-launchpad"},
                polling_timeout=300,
            ).result()
        )

    def discover(self) -> list[AzureSandbox]:
        return [
            AzureSandbox(self.client.get_sandbox_client(sandbox.id))
            for sandbox in self.client.list_sandboxes(labels={"app": "sandbox-launchpad"})
            if sandbox.state != "Deleting"
        ]

    def initialize(self, sandbox) -> str:
        result = sandbox.client.exec("timeout 240 bash -c " + shlex.quote(BOOTSTRAP.read_text()))
        return self._version(result)

    @staticmethod
    def _version(result) -> str:
        if result.exit_code != 0:
            raise RuntimeError(
                f"Copilot initialization exited {result.exit_code}: "
                f"{result.stderr or result.stdout}"
            )
        version = result.stdout.strip().splitlines()
        if not version:
            raise RuntimeError("Copilot readiness probe returned no version.")
        return version[0]

    def probe(self, sandbox: AzureSandbox) -> str:
        state = sandbox.client.get().state
        if state != "Running":
            raise RuntimeError(f"Sandbox is {state}; it is not currently ready.")
        return self._version(sandbox.client.exec(PROBE))


@dataclass
class SimulatedSandbox:
    sandbox_id: str
    deleted: bool = False

    def delete(self) -> None:
        self.deleted = True


class SimulationProvider:
    def __init__(self):
        self.resources = []

    def create(self):
        time.sleep(0.8 + uuid.uuid4().int % 12 / 10)
        sandbox = SimulatedSandbox(f"sim-{uuid.uuid4().hex[:12]}")
        self.resources.append(sandbox)
        return sandbox

    def initialize(self, sandbox) -> str:
        time.sleep(1.5 + uuid.uuid4().int % 20 / 10)
        return "copilot (simulated; no Azure resources)"

    def discover(self):
        return [resource for resource in self.resources if not resource.deleted]

    def probe(self, sandbox) -> str:
        return "copilot (simulated; no Azure resources)"

# Sandbox Launchpad

An interactive Azure Container Apps **Sandboxes** demo, not a dynamic-sessions
demo. Choose **N (1–50)** and watch a grid transition **red → orange → green**:

| Color | What has actually happened |
| --- | --- |
| Red / provisioning | Queued or allocating an Ubuntu sandbox microVM |
| Orange / initializing | Azure creation completed; installing Node.js and GitHub Copilot CLI |
| Green / ready | `copilot --version` executed successfully inside the sandbox |
| Red / error | Allocation or installation failed; select the tile for the reason |

The dashboard is static HTML/CSS/JavaScript, served alongside a small FastAPI
control API in one Container App. No frontend build, framework, or browser Azure
credential is required. The backend uses managed identity to call the official
`azure-containerapps-sandbox` Python SDK.

## Deploy with `azd up`

Prerequisites: Azure CLI, Azure Developer CLI (`azd`), Python 3, and an
Azure **Entra ID** account. Personal Microsoft accounts are not supported by
Sandboxes. Your deploying identity needs permission to create resources and
role assignments (for example Contributor plus Role Based Access Control
Administrator at the deployment scope). Sandbox availability and quota vary
by region/subscription; `westus2` is a documented starting point.

```sh
az login
azd auth login
azd env new sandbox-demo
azd env set AZURE_LOCATION westus2
azd up
```

Select your subscription when prompted. The preprovision hook generates a
random presenter key in the local `.azure/` environment; Bicep stores it as a
Container App secret. It is never a frontend asset or deployment output.
The controller image is built remotely in Azure Container Registry for
`linux/amd64`, so ARM development machines do not need Docker emulation.
The deploying identity must also be allowed to schedule ACR Tasks. Docker is
only required for the optional local container build.

```sh
azd env get-value DEMO_API_KEY
```

Open the endpoint printed by `azd`, enter the presenter key, and click
**Connect**. Choose N, click **Launch sandboxes**, and select any tile for its
Azure ID, CLI version, error message, and transition timestamps. The dashboard
polls every 1.5 seconds. Allocation/initialization concurrency is bounded at 8;
larger fleets queue rather than flooding the data plane.

Click **Delete fleet** when finished, then launch another run. Role assignments
can take a minute to propagate; an initial 403 is visible in the tile.
Delete the failed fleet and retry after propagation.

The initial Bicep provisioning uses a placeholder Container App image.
`azd deploy` replaces it with the image built from `Dockerfile`; the dashboard
is available after the complete `azd up` operation, not after provision alone.

## Copilot authentication

**Green verifies installation and executable readiness, not Copilot login or
a successful AI response.** No GitHub token is required or copied into these
sandboxes. Node.js `22.23.3` and Copilot CLI `1.0.97` are pinned in
`app/bootstrap.sh`. Node downloads are checked against the publisher's SHA-256
manifest. Installation runs as the sandbox user in `$HOME/.local`; an empty
workspace is created at `$HOME/workspace`.

To try Copilot interactively, open the sandbox in the
[Sandboxes portal](https://sandboxes.azure.com), then:

```sh
source ~/.profile
cd ~/workspace
copilot
```

Use `/login` to authenticate with your own Copilot-enabled GitHub account.
Do not use privileged organization tokens for a public demo or expose them in
browser JavaScript, images, Bicep parameter files, or logs.

## Local rehearsal

Use [uv](https://docs.astral.sh/uv/) and Python 3.12+:

```sh
uv sync
export DEMO_API_KEY=local-demo-presenter-key
export DEMO_MODE=simulation
uv run uvicorn app.main:build_app --factory --host 127.0.0.1 --port 8080
```

Open `http://localhost:8080`. The same UI/API runs with explicitly labeled
**SIMULATION / NO AZURE** telemetry. It creates no Azure resources and does not
install Copilot. Omit `DEMO_MODE=simulation` to use Azure; supply
`AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION`, and
`AZURE_SANDBOX_GROUP`, and sign in using `az login`.

## Infrastructure

```text
Browser ── HTTPS ── Container App (static UI + control API)
                              │
                              └── managed identity ── Sandbox group
                                                        ├─ Ubuntu + Copilot
                                                        ├─ Ubuntu + Copilot
                                                        └─ ... N workspaces
```

`infra/main.bicep` creates a resource group and `resources.bicep` creates:
the sandbox group, Container Apps environment, Log Analytics workspace,
Basic Azure Container Registry, controller managed identity, and Container App.
RBAC grants that identity **Container Apps SandboxGroup Data Owner** only on
the demo group and **AcrPull** only on the demo registry. The deployer gets
**AcrPush** on that registry. Registry admin passwords are disabled.

`main.parameters.json` is the azd environment-substitution adapter, not a
hand-maintained secrets file. The sandbox ARM API is deliberately pinned to
`2026-02-01-preview`, matching the SDK and
[Microsoft's Bicep quickstart](https://learn.microsoft.com/azure/container-apps/sandboxes-quickstart-bicep).
Current Bicep type catalogs may omit that preview even when the resource
provider supports it; its BCP081 warning alone is suppressed.

This is a **presenter-controlled demo, not a multi-user production service**:
the dashboard is public, but all control/telemetry endpoints require the key.
The key stays in page memory and is discarded on reload. There is no arbitrary
command-execution API or Copilot prompt proxy. Use one controller replica and
one Uvicorn worker, as configured; do not scale the process-local coordinator
horizontally without a durable coordination store.

Sandboxes have a 30-minute inactivity auto-suspend policy. Suspension stops CPU
and memory billing but is **not deletion**; disk/snapshot and infrastructure
charges may remain. Do not leave demo resources unattended.

The controller discovers labeled demo sandboxes on startup, so a restart does
not hide previously allocated resources. While the dashboard is being viewed,
it reconciles inventory and reruns the CLI probe every 15 seconds. Suspended,
deleted, or unhealthy sandboxes become red with a reason; it does not
automatically resume them. Background probes stop after 60 seconds without a
dashboard poll, allowing the inactivity policy to take effect. Continuous
viewing/probing keeps healthy sandboxes active. Cleanup also discovers orphans
left by failed creation polling, and waits for confirmed Azure deletion.
Run history before a restart is not durable; recovered tiles show new probe
timestamps. Inventory/RBAC failures are surfaced, and new launches are blocked
until Azure inventory can be checked.

```sh
# Remove the whole demo, including the sandbox group and its children.
azd down
```

## Development

```sh
uv run pytest
uv run ruff check app tests scripts
npm test
az bicep build --file infra/main.bicep --stdout > /dev/null
docker build -t sandbox-launchpad .
```

With the simulation server running, optional real-browser verification:

```sh
uv sync --group browser
uv run playwright install chromium
DEMO_API_KEY=local-demo-presenter-key uv run --group browser python tests/browser_demo.py
```

Tests exercise lifecycle transitions, initialization failures, count bounds,
API authorization, cleanup retries, and frontend color/count logic without
creating billable resources. A real end-to-end Azure run requires deploying
into an enabled subscription and verifying the grid against sandbox telemetry.

References:
[Sandbox overview](https://learn.microsoft.com/azure/container-apps/sandboxes-overview),
[Python SDK quickstart](https://learn.microsoft.com/azure/container-apps/sandboxes-quickstart-python-sdk),
[Copilot CLI installation](https://docs.github.com/en/copilot/how-tos/copilot-cli/cli-getting-started).

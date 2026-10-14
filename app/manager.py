import copy
import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Protocol

log = logging.getLogger(__name__)


class Resource(Protocol):
    sandbox_id: str

    def delete(self) -> None: ...


class Provider(Protocol):
    def create(self) -> Resource: ...

    def initialize(self, sandbox: Resource) -> str: ...

    def discover(self) -> list[Resource]: ...

    def probe(self, sandbox: Resource) -> str: ...


class Manager:
    def __init__(self, provider: Provider, limit: int = 50):
        self.provider = provider
        self.limit = limit
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="sandbox")
        self._futures: list[Future] = []
        self._items: list[dict] = []
        self._resources: dict[int, Resource] = {}
        self._cleaning = False
        self._reconciling = False
        self._system_error = None
        self._stop = threading.Event()
        self._monitor: threading.Thread | None = None
        self._last_view = time.monotonic()
        self._started = 0.0

    def snapshot(self) -> dict:
        with self._lock:
            items = copy.deepcopy(self._items)
            counts = {state: 0 for state in ("provisioning", "initializing", "ready", "error")}
            for item in items:
                counts[item["state"]] += 1
            return {
                "sandboxes": items,
                "counts": counts,
                "limit": self.limit,
                "busy": self._cleaning
                or self._reconciling
                or any(not future.done() for future in self._futures),
                "elapsed": round(time.monotonic() - self._started, 1) if items else 0,
                "systemError": self._system_error,
            }

    def start(self, count: int) -> dict:
        with self._lock:
            if type(count) is not int or not 1 <= count <= self.limit:
                raise ValueError(f"Sandbox count must be an integer between 1 and {self.limit}.")
            if self._system_error or self._reconciling:
                raise ValueError("Azure inventory is unavailable or refreshing. Please retry.")
            if self._items or self._cleaning:
                raise ValueError("Please clean up the existing run before launching another.")
            self._started = time.monotonic()
            self._items = [
                {
                    "id": f"sandbox-{index + 1:02d}",
                    "state": "provisioning",
                    "message": "Queued for Azure allocation",
                    "sandboxName": None,
                    "version": None,
                    "readyAfter": None,
                    "history": [{"state": "provisioning", "at": 0}],
                }
                for index in range(count)
            ]
            initial = self.snapshot()
            initial["busy"] = True
            self._futures = [self._pool.submit(self._provision, index) for index in range(count)]
            return initial

    def _transition(self, index: int, state: str, message: str, **fields) -> None:
        with self._lock:
            item = self._items[index]
            elapsed = round(time.monotonic() - self._started, 1)
            if item["state"] != state:
                item["history"].append({"state": state, "at": elapsed})
                item["history"] = item["history"][-100:]
            item.update(state=state, message=message, **fields)
            if state == "ready" and item["readyAfter"] is None:
                item["readyAfter"] = elapsed

    def _provision(self, index: int) -> None:
        try:
            sandbox = self.provider.create()
            with self._lock:
                self._resources[index] = sandbox
            self._transition(
                index,
                "initializing",
                "Installing Node.js and GitHub Copilot CLI",
                sandboxName=sandbox.sandbox_id,
            )
            version = self.provider.initialize(sandbox)
            self._transition(index, "ready", "Copilot CLI readiness probe passed", version=version)
        except Exception as error:
            # A per-sandbox failure must not cancel the rest of the batch.
            log.exception("Sandbox %s failed to initialize", index + 1)
            self._transition(index, "error", str(error)[:2000])

    def wait(self) -> None:
        wait(self._futures)

    def _adopt(self, discovered: list[Resource]) -> None:
        with self._lock:
            known = {resource.sandbox_id for resource in self._resources.values()}
            for sandbox in discovered:
                if sandbox.sandbox_id in known:
                    continue
                if not self._items:
                    self._started = time.monotonic()
                index = len(self._items)
                self._items.append(
                    {
                        "id": f"recovered-{index + 1:02d}",
                        "state": "initializing",
                        "message": "Recovered from Azure; checking CLI readiness",
                        "sandboxName": sandbox.sandbox_id,
                        "version": None,
                        "readyAfter": None,
                        "history": [{"state": "initializing", "at": 0}],
                    }
                )
                self._resources[index] = sandbox
                known.add(sandbox.sandbox_id)

    def reconcile(self) -> None:
        with self._lock:
            if self._cleaning or any(not future.done() for future in self._futures):
                return
            self._reconciling = True
        try:
            self._adopt(self.provider.discover())
            with self._lock:
                self._system_error = None
                resources = list(self._resources.items())
            for index, sandbox in resources:
                try:
                    version = self.provider.probe(sandbox)
                    self._transition(
                        index, "ready", "Copilot CLI readiness probe passed", version=version
                    )
                except Exception as error:
                    log.exception("Readiness probe failed for %s", sandbox.sandbox_id)
                    self._transition(index, "error", str(error)[:2000])
        except Exception as error:
            log.exception("Sandbox inventory reconciliation failed")
            with self._lock:
                self._system_error = f"Azure inventory unavailable: {error}"[:2000]
        finally:
            with self._lock:
                self._reconciling = False

    def start_monitor(self) -> None:
        def monitor():
            self.reconcile()
            while not self._stop.wait(15):
                if time.monotonic() - self._last_view < 60:
                    self.reconcile()

        with self._lock:
            self._reconciling = True
            self._monitor = threading.Thread(target=monitor, name="inventory", daemon=True)
            self._monitor.start()

    def observe(self) -> None:
        self._last_view = time.monotonic()

    def cleanup(self) -> dict:
        with self._lock:
            if (
                self._cleaning
                or self._reconciling
                or any(not future.done() for future in self._futures)
            ):
                raise ValueError("Wait for the current operation to finish before cleaning up.")
            self._cleaning = True
        failures = []
        try:
            try:
                self._adopt(self.provider.discover())
            except Exception as error:
                log.exception("Could not discover remaining sandboxes before cleanup")
                raise RuntimeError(f"Azure inventory unavailable: {error}") from error
            with self._lock:
                resources = list(self._resources.items())
            for index, sandbox in resources:
                try:
                    sandbox.delete()
                    with self._lock:
                        del self._resources[index]
                except Exception as error:
                    log.exception("Failed to delete sandbox %s", sandbox.sandbox_id)
                    self._transition(index, "error", f"Cleanup failed: {error}"[:2000])
                    failures.append(str(error))
            if failures:
                raise RuntimeError("; ".join(failures))
            with self._lock:
                self._items = []
                self._futures = []
                self._system_error = None
                self._cleaning = False
            return self.snapshot()
        finally:
            with self._lock:
                self._cleaning = False

    def close(self) -> None:
        self._stop.set()
        if self._monitor is not None:
            self._monitor.join()
        self._pool.shutdown(wait=True)

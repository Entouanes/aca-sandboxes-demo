import { test } from "node:test";
import assert from "node:assert/strict";
import { summarize, colorForState } from "../web/state.js";

test("lifecycle colors are red then orange then green; failures stay red", () => {
  assert.equal(colorForState("provisioning"), "red");
  assert.equal(colorForState("initializing"), "orange");
  assert.equal(colorForState("ready"), "green");
  assert.equal(colorForState("error"), "red");
  assert.throws(() => colorForState("unexpected"));
});

test("counts reflect actual readiness, including failures", () => {
  assert.deepEqual(summarize([
    { state: "provisioning" }, { state: "initializing" },
    { state: "ready" }, { state: "error" },
  ]), { total: 4, provisioning: 1, initializing: 1, ready: 1, error: 1 });
});

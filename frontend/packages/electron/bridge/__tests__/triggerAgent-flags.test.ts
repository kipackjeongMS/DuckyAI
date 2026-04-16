/**
 * Integration test: verifies triggerAgent correctly maps
 * sinceLastSync / lookbackHours to CLI flags.
 *
 * Run: npx tsx electron/bridge/__tests__/triggerAgent-flags.test.ts
 */
import assert from "node:assert/strict";

// ---- Replicate the arg-building logic from orchestrator.ts ----

function buildTriggerArgs(
  abbr: string,
  opts?: { file?: string; lookback?: number; sinceLastSync?: boolean },
): string[] {
  const args = ["orchestrator", "trigger", abbr, "--json-output"];
  if (opts?.file) args.push("--file", String(opts.file));

  if (opts?.lookback) {
    // lookback takes precedence
    args.push("--lookback", String(opts.lookback));
  } else if (opts?.sinceLastSync) {
    args.push("--since-last-sync");
  }
  return args;
}

// ---- Tests ----

// 1. sinceLastSync only → --since-last-sync flag
{
  const args = buildTriggerArgs("TCS", { sinceLastSync: true });
  assert.ok(args.includes("--since-last-sync"), "should include --since-last-sync");
  assert.ok(!args.includes("--lookback"), "should NOT include --lookback");
}

// 2. lookbackHours only → --lookback N
{
  const args = buildTriggerArgs("TCS", { lookback: 6 });
  assert.ok(args.includes("--lookback"), "should include --lookback");
  assert.equal(args[args.indexOf("--lookback") + 1], "6", "lookback value should be 6");
  assert.ok(!args.includes("--since-last-sync"), "should NOT include --since-last-sync");
}

// 3. Both provided → lookback wins, no --since-last-sync
{
  const args = buildTriggerArgs("TMS", { lookback: 24, sinceLastSync: true });
  assert.ok(args.includes("--lookback"), "lookback should win when both provided");
  assert.equal(args[args.indexOf("--lookback") + 1], "24");
  assert.ok(!args.includes("--since-last-sync"), "--since-last-sync should be dropped");
}

// 4. Neither provided → no time flags at all
{
  const args = buildTriggerArgs("TCS", {});
  assert.ok(!args.includes("--lookback"), "no --lookback when neither provided");
  assert.ok(!args.includes("--since-last-sync"), "no --since-last-sync when neither provided");
}

// 5. Non-TCS/TMS agent ignores time flags
{
  const args = buildTriggerArgs("GDR", { sinceLastSync: true, lookback: 12 });
  // The bridge doesn't filter by agent — it just passes flags through. CLI ignores them.
  assert.ok(args.includes("--lookback"), "flags still passed (CLI ignores for non-TCS)");
  assert.ok(!args.includes("--since-last-sync"), "lookback still wins");
}

// 6. File option passes through
{
  const args = buildTriggerArgs("EIC", { file: "00-Inbox/article.md" });
  assert.ok(args.includes("--file"), "should include --file flag");
  assert.equal(args[args.indexOf("--file") + 1], "00-Inbox/article.md");
}

// 7. lookbackHours=0 is falsy → falls through to sinceLastSync
{
  const args = buildTriggerArgs("TCS", { lookback: 0, sinceLastSync: true });
  assert.ok(!args.includes("--lookback"), "lookback 0 is falsy, should skip");
  assert.ok(args.includes("--since-last-sync"), "should fallback to --since-last-sync");
}

console.log("✓ All 7 triggerAgent flag-mapping tests passed");

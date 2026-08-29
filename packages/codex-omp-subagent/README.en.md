[Repository index](../../README.en.md) · [中文](README.md)

# Codex OMP Subagent

This component lets a Codex parent delegate complex refactors, repository-wide investigations, AST/LSP-assisted work, and longer coding tasks to the external **OMP (Oh My Pi)** coding harness while keeping Codex's native `spawn_agent` parent/child structure.

V2 changes the execution boundary: **OMP is no longer launched by a `SubagentStart` Hook before the child starts. The native `omp_worker` Codex child launches OMP itself from inside its `workspace-write` sandbox.**

## V2 flow

```text
Codex Parent
  -> stage assignment
  -> UUID handoff
  -> spawn_agent(agent_type="omp_worker", fork_turns="none")
  -> native Codex omp_worker child
  -> omp_bridge.py --mode run --handoff-id <UUID>
  -> OMP
  -> bounded structured result + local raw logs
  -> child verifies workspace diff/tests
  -> concise native callback to Parent
```

## Handoff protocol

Stage a self-contained assignment via stdin:

```bash
printf '%s' 'Refactor src/foo.py and run focused tests.' | \
  python3 "${CODEX_HOME:-$HOME/.codex}/hooks/codex-omp-subagent/omp_bridge.py" --mode stage
```

The bridge returns schema 2 JSON containing a unique `handoff_id`. Multiple UUID handoffs may coexist.

The native child then executes:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/hooks/codex-omp-subagent/omp_bridge.py" \
  --mode run \
  --handoff-id <UUID>
```

When `OMP_ARGS` is not set, OMP is launched as:

```bash
omp --print --mode json --no-session -- "<assignment>"
```

The `--` separator prevents assignments beginning with `-` from being parsed as CLI options.

## Results and logs

Full OMP stdout/stderr are not injected into the Codex child context. The bridge returns a bounded JSON result with status, exit code, final summary, usage when available, a bounded stderr tail, and artifact paths.

Raw artifacts are stored under the bridge state directory:

```text
<state-root>/
  pending/<uuid>.json
  running/<uuid>.json
  completed/<uuid>.json
  failed/<uuid>.json
  jobs/<uuid>/
    envelope.json
    omp.jsonl
    stderr.log
    result.json
```

The default state root is `~/.local/state/codex/omp-subagent-handoff` on POSIX (or `$XDG_STATE_HOME/...` when set) and `%LOCALAPPDATA%/Codex/omp-subagent-handoff` on Windows. Override it with `CODEX_OMP_HANDOFF_DIR`.

## Installation

Prerequisites:

1. Codex with native custom subagents / `spawn_agent` support.
2. A working OMP installation (`omp --version` or `omp`).
3. The desired provider/model configured inside OMP.

For automatic installation, copy [`prompts/install-with-codex.md`](prompts/install-with-codex.md) into Codex.

V2 installs:

```text
<codex-home>/agents/omp-worker.toml
<codex-home>/skills/use-omp-worker/
<codex-home>/hooks/codex-omp-subagent/omp_bridge.py
```

**V2 does not require a `SubagentStart` Hook.** If V1 was installed, remove the old OMP matcher `^omp_worker$` from `~/.codex/hooks.json` so the same job cannot be executed twice.

## Parent workflow

The parent follows `$use-omp-worker`:

1. Build a self-contained assignment with targets, constraints, and acceptance criteria.
2. Stage it with the bridge.
3. Capture the returned UUID.
4. Spawn `omp_worker` with `fork_turns="none"` and include the UUID in the message.
5. Wait for the native child callback.
6. Review the child's workspace diff and validation evidence before integrating the result.

Recommended spawn message:

```text
Execute staged OMP handoff <UUID>. Inspect and verify the resulting workspace changes, then report a concise result to the parent.
```

## Configuration

- `OMP_BIN`: OMP executable, default `omp`
- `OMP_ARGS`: override the default OMP CLI arguments
- `OMP_TIMEOUT`: OMP process timeout in seconds, default 600
- `CODEX_OMP_HANDOFF_DIR`: override the local state directory

The bridge also exposes `--timeout-seconds` and `--ttl-seconds`.

## Concurrency and idempotency

V2 uses one UUID file per handoff instead of a single global pending file, so separate OMP workers can process different jobs concurrently.

Calling `--mode run` again for a completed UUID returns the stored `result.json` instead of launching OMP again.

## Tests

Offline tests do not call a real model provider:

```bash
python -m unittest packages/codex-omp-subagent/tests/test_omp_bridge.py -v
python packages/codex-omp-subagent/tests/test_agent_templates.py
```

A real end-to-end probe is documented in [`prompts/quick-smoke-test.md`](prompts/quick-smoke-test.md). It may incur charges from the provider configured in OMP.

## Security boundary

`omp-worker.toml` defaults to `sandbox_mode = "workspace-write"`. In V2 the external OMP process is started by the native child rather than by the Codex Hook runner outside the child execution path. OMP is still a full coding harness and can use tools within the permissions available to that child. Do not send sensitive repository data to an untrusted third-party provider.

This is an independent community integration and is not officially affiliated with or endorsed by OpenAI or OMP.

# Install OMP Subagent V2 with Codex

Copy the prompt below into Codex. It installs the personal `omp_worker` subagent, its lazy-loaded skill, and the V2 stage/run bridge.

```text
Install the OMP (Oh My Pi) custom subagent from the `packages/codex-omp-subagent` component in https://github.com/feiyushaw/mixagents into my personal Codex configuration.

Scope and invariants:
- Preserve my current main model, model provider, ChatGPT login, and provider configuration.
- Install the standalone agent file as <codex-home>/agents/omp-worker.toml.
- Install the skill as <codex-home>/skills/use-omp-worker/ (including SKILL.md and agents/openai.yaml if present).
- Install the bridge script to <codex-home>/hooks/codex-omp-subagent/omp_bridge.py.
- This is the V2 child-executed bridge. Do NOT register a SubagentStart hook for omp_worker.
- If ~/.codex/hooks.json (or the active CODEX_HOME hooks.json) already contains a legacy OMP SubagentStart entry matching ^omp_worker$, remove only that legacy OMP entry while preserving all unrelated hooks.
- Append/update the snippets/AGENTS.md routing snippet in my personal AGENTS.md if the component provides one, without duplicating it.
- Verify the installed bridge with offline/local checks only: Python syntax, `--help`, and the repository unit tests when practical.
- Do not make a paid provider/model call during installation.
- After installation, tell me exactly which files changed and whether a legacy V1 hook was removed.
```

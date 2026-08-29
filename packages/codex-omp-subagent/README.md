[仓库索引](../../README.md) · [English](README.en.md)

# Codex OMP Subagent

让 Codex 主任务把复杂代码重构、全库探索、AST/LSP 辅助分析和长程执行任务委派给外部 **OMP (Oh My Pi)** coding harness，同时保留 Codex 原生 `spawn_agent` 的父子会话结构。

V2 的关键变化是：**OMP 不再由 `SubagentStart` Hook 在 child 启动前执行，而是由真正的 `omp_worker` Codex child 在自己的 `workspace-write` sandbox 中启动。** 这样执行边界、并发语义和上下文控制都更清晰。

---

## V2 架构

```text
Codex Parent
    │
    │ stage assignment
    ▼
UUID handoff envelope
    │
    │ spawn_agent(agent_type="omp_worker", fork_turns="none")
    ▼
Codex native child: omp_worker
    │
    │ python omp_bridge.py --mode run --handoff-id <UUID>
    ▼
OMP (Oh My Pi)
    │
    ├─ configured model/provider
    ├─ LSP / AST / search / shell
    └─ OMP internal subagents if configured
    │
    ▼
structured JSON result + local raw logs
    │
    ▼
omp_worker verifies workspace diff/tests
    │
    ▼
concise native Codex callback to Parent
```

### 为什么不再使用 SubagentStart Hook

V1 在 Hook 中直接 `subprocess.run("omp")`。这会让 Hook 本身承担长时间执行，而且 Hook 启动的外部进程并不等价于 child shell 命令的 sandbox 边界。V2 把 OMP 执行移动到 `omp_worker` child 内部，使 OMP 成为真正由该 child 发起的 harness-level delegation。

---

## Handoff 协议

Bridge 现在有两个模式：

### 1. `stage`

从 stdin 读取完整 assignment，生成 schema 2 的 UUID handoff：

```bash
printf '%s' 'Refactor src/foo.py and run focused tests.' | \
  python3 "${CODEX_HOME:-$HOME/.codex}/hooks/codex-omp-subagent/omp_bridge.py" --mode stage
```

返回示例：

```json
{
  "staged": true,
  "schema": 2,
  "handoff_id": "...uuid...",
  "agent_type": "omp_worker"
}
```

每个 UUID 都有独立状态，因此可以同时存在多个 pending/running OMP 任务。

### 2. `run`

由 `omp_worker` child 调用：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/hooks/codex-omp-subagent/omp_bridge.py" \
  --mode run \
  --handoff-id <UUID>
```

默认启动 OMP：

```bash
omp --print --mode json --no-session -- "<assignment>"
```

`--` 用于避免以 `-` 开头的 assignment 被 CLI 误解析为参数。

---

## 结果与日志

Bridge 不再把完整 OMP stdout/stderr 注入 Codex context。默认只返回有界结构化结果，包括：

- `status` / `exit_code`
- OMP 最终摘要
- usage（若 JSONL event 提供）
- stderr 尾部
- job artifact 路径

完整日志留在本地状态目录：

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

默认状态根目录为：

- POSIX: `$XDG_STATE_HOME/codex/omp-subagent-handoff`，未设置时为 `~/.local/state/codex/omp-subagent-handoff`
- Windows: `%LOCALAPPDATA%/Codex/omp-subagent-handoff`

也可通过 `CODEX_OMP_HANDOFF_DIR` 覆盖。

---

## 安装

### 前置条件

1. 已安装 Codex，并可使用原生 custom subagent / `spawn_agent`。
2. 已安装并配置 OMP，终端执行 `omp --version` 或 `omp` 正常。
3. OMP 内部使用哪个 provider/model 完全由 OMP 自己管理。

### 推荐：让 Codex 自动安装

把 [`prompts/install-with-codex.md`](prompts/install-with-codex.md) 复制给 Codex。

V2 安装内容：

```text
<codex-home>/agents/omp-worker.toml
<codex-home>/skills/use-omp-worker/
<codex-home>/hooks/codex-omp-subagent/omp_bridge.py
```

**V2 不需要注册 `SubagentStart` Hook。** 如果机器上安装过 V1，应删除 `~/.codex/hooks.json` 中 matcher 为 `^omp_worker$` 的旧 OMP Hook，避免一个任务被重复执行。

---

## 使用

Parent 应按照 `$use-omp-worker`：

1. 组织自包含 assignment；
2. 调用 bridge `--mode stage`；
3. 获取 `handoff_id`；
4. `spawn_agent(agent_type="omp_worker", fork_turns="none")`，message 中只需包含该 UUID 和要求 child 验证结果；
5. 等待 native callback；
6. Parent 再决定是否接受、继续修改或执行更高层验证。

推荐的 spawn message：

```text
Execute staged OMP handoff <UUID>. Inspect and verify the resulting workspace changes, then report a concise result to the parent.
```

---

## 配置

- `OMP_BIN`: OMP executable，默认 `omp`
- `OMP_ARGS`: 覆盖默认 OMP CLI 参数；如果不设置，使用 `--print --mode json --no-session`
- `OMP_TIMEOUT`: OMP run 超时秒数，默认 600
- `CODEX_OMP_HANDOFF_DIR`: 覆盖本地 handoff/job 状态目录

Bridge 还支持 `--timeout-seconds` 和 `--ttl-seconds`。

---

## 并发与幂等

V2 不再使用单一 `omp_worker.pending.json`，每个任务都有自己的 UUID 文件，因此不同 OMP worker 可以并行处理不同 handoff。

同一个 UUID 完成后再次调用 `--mode run` 不会再次启动 OMP，而是返回已保存的 `result.json`。这避免 callback/retry 导致重复修改代码。

---

## 测试

离线测试不会调用真实 provider：

```bash
python -m unittest packages/codex-omp-subagent/tests/test_omp_bridge.py -v
python packages/codex-omp-subagent/tests/test_agent_templates.py
```

测试覆盖：

- 多 pending UUID handoff
- mock OMP JSONL 解析
- `--print --mode json --no-session --` 参数约定
- completed handoff 幂等
- 非法 UUID
- agent TOML 的 V2 执行契约

真实端到端验证见 [`prompts/quick-smoke-test.md`](prompts/quick-smoke-test.md)。真实 smoke test 会使用你在 OMP 中配置的 provider，可能产生对应费用。

---

## 安全边界

`omp_worker.toml` 默认使用：

```toml
sandbox_mode = "workspace-write"
```

V2 的 OMP 是由这个 native child 内部发起，而不是由 Codex Hook runner 在 child 外部发起。仍需注意：OMP 自身是一个完整 coding harness，能够在 child 允许的工作区范围内调用其工具。不要把包含敏感数据的任务发送给不受信任的第三方 provider。

本项目是独立社区集成，与 OpenAI 或 OMP 均无官方隶属或背书关系。

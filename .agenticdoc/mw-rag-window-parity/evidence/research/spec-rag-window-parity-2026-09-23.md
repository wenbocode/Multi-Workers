# 调研：mw-rag-window-parity（spec 阶段）

日期: 2026-09-23 · 来源: 本仓代码实读（file:line 均为当时快照）

## 1. R-1 `skill.dir` 跨语言不一致（确认）

| 侧 | 位置 | 行为 |
|---|---|---|
| Python | `mw_common.py:551-559` | `cli_entry` 必须非空；`dir` 允许缺省/`null`（"must be a non-empty string or null"），返回 `"dir": None` |
| TS | `rag/config.ts:260-270` | `parseSkill`：`const dir = requireString(raw.dir, …)` → 缺省/`null` 直接 `fail("invalid-shape", "field 'server 'X'.skill.dir' must be a non-empty string")`；`cli_entry` 用 `optionalString` 后判空（`skill-missing-cli`） |
| TS 类型 | `rag/config.ts:92-96` | `interface RagSkillEntry { dir: string; … }` —— 无法表达 `null` |
| TS 调用点 | `rag/tools.ts:735` | `const dir = path.resolve(runtime.controlRoot, skill.dir)` —— 若 `dir` 为 `null` 会 `TypeError`（所以不能只放宽校验） |

复现（手册承诺面）：写 `skill: {cli_entry: python x.py}`（不给 `dir`）→ `mw rag list` exit 0（Python），
worker 侧 `loadRagConfig` 失败。T-23 报告 §4 #5 已给同一结论（静态推得，未实跑 TS）。

## 2. fingerprint 合约（决定修法）

- Python：`mw_common.rag_fingerprint(config)`（`mw_common.py:~947+`）把 `skill` 整块原样进 canonical JSON，含 `"dir": skill.get("dir")`（缺省 = `None`）。
- TS：`rag/config.ts:616-700`（`ragFingerprint`）自称与 Python **byte-identical**（D-009/VC-022 锁定；`rag/block.ts:99` 把它写进 `<!-- mw-rag: v1 -->`）。
- 结论：**不能**把 `dir` 归一化成 `"."`（会让两侧 canonical JSON 不同 → fingerprint 不同 → `config torn (rag)` 误报）。
  正确修法：TS 解析层保持 `null`（类型 `string | null`），只在 `cliCall` 处 `skill.dir ?? "."` 落控制工作区根。

## 3. golden / fixture 影响面（确认无字节风险）

- `test/fixtures/rag/machine-servers.yml` 的 server `A` 显式给了 `skill.dir: skills/overcode` → 放宽「缺省/null」不改这份 fixture 的解析结果；
  `rag-block.golden.md`（347 B，sha256 `00f85e64…4035`）与 parity 测试不受影响。
- `test/fixtures/rag/phase-only-target.yml` 同属既有 parity 面，本次不动。

## 4. pi 窗口使用面（R-2 现状）

| 项 | 位置 | 现状 |
|---|---|---|
| 命令注册 | `pm/ui-bridge.ts:~1820`（`registerCommand("mw", …)`） | 白名单：`build / init / doctor / update / status / start / stop / restart / target / partition / model / ack`；无 `rag`，无透传 |
| 薄封装先例 | 同文件 `runMwTargetCommand` / `runMwPartitionCommand` / model 分支 | 见子命令 → 调 `mw.py <sub>` → `ctx.ui.notify(output, level)`；Python 保持解析/校验唯一源 |
| `/mw doctor` 渲染 | `ui-bridge.ts:1452` `formatDoctorReport(report, fix)` | 行：服务/代理端口/孤儿代理/launcher 日志/队列/worker 活性/路由凭证/扩展 bundle/pi shell/派发模型/fix/整体/建议 —— **无 rag 行** |
| doctor 数据 | `mw.py:517` `report["rag"] = _doctor_rag(project_dir)`；`mw.py:2248` `_doctor_rag`；`mw.py:2297` `_format_rag_doctor_line` | JSON 已含 `exists/machine_file/project_file/skill{status}/error?/enabled[]/default_server/fingerprint/probe{name:{reachable,transport,error}}/required_missing`；文本行形如 `rag: enabled=A; probe=A=reachable; fingerprint=<12>; skill=installed[; required_missing=N]` / `rag: not enabled (skill missing)` / `rag: ERROR - <detail>` |
| TS 类型 | `shared/mw-runner.ts:341` `interface DoctorJson` | 无 `rag` 字段（需补可选字段） |
| RAG CLI | `mw.py:4926` `cmd_rag` 分派 + `_RAG_ACTIONS`；`mw.py:4848-4876` argparse | 子命令 `init / list / probe / sync / audit`，**共同必填 `--project`**；exit 0/1/2 语义已文档化 |

## 5. 参考纪律（沿用既有 key 的教训）

- `[VERIFY]` 在 TS 里必须 `process.stdout.write`（vitest `silent: "passed-only"`，T-02/T-12/T-13 踩过）。
- 证据行必须含实测数据（AC-108；`mw-rag-integration-fix` T-20 因「纯布尔断言」被独立验证降级）。
- 测试子进程显式 `encoding="utf-8"`（D-211，本机 `PYTHONIOENCODING=utf-8` 会假红）。

# Quality Gate Report: mw-worker-progress-persist

**时间**: 2026-09-23T17:05+08:00
**触发**: Stage 完成（T-1~T-6 全部 done，独立验证 PASS-with-gaps，gap 已收口）
**范围**: 全量（AC-001~011 / VC-001~011 / F1~F5）

## 前置检查

| 检查项 | 结果 |
|--------|------|
| spec.md 含 AC 编号 | ✅ AC-001~011 |
| design.md 含 VC 编号 | ✅ VC-001~011（+ Coverage Matrix F1~F5） |
| AC→VC 覆盖 100% | ✅ 11/11（design §7 每 VC 标注 `Source: AC-xxx`） |
| 每个 task 有非空 ac_refs/vc_refs | ✅ T-1~T-6 |
| evidence/baseline | 本 key 用「改造前源码基线」等价物（`git show HEAD:` 归一化比对 + Python parity 快照），无独立 baseline 目录（⚠️ 记录，见 §2） |

## 问题清单与核查结果

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-AC-001 | 只读角色到检查点时 `progress.md` 含机器行 | ✅ 充分 | `checkpoint-wiring.test.ts` `[VERIFY] VC-001: progress_exists=true machine_lines=1`；真模型冒烟 `progress.md` 首行机器行 | L1 + L2 |
| Q-AC-002 | 机器行 append-only，既有内容逐字节保留 | ✅ 充分 | `[VERIFY] VC-002: machine_lines=1 sentinel_first=true` + `machine_lines=3 sentinel_first=true` | L1（单元直调 3 次 + 集成 1 次） |
| Q-AC-003 | 写工具角色不写机器行、steer 逐字不变 | ✅ 充分 | `[VERIFY] VC-003: machine_lines=0`；T-6 `NORMALIZED_EQUAL: true`（`git show HEAD` 基线插值归一化，132 字符逐字同） | L1 |
| Q-AC-004 | steer 按角色分化，无写角色无写文件指令 | ✅ 充分 | `[VERIFY] VC-004: writeless_write_instr=false coding_identical=true` | L1 |
| Q-AC-005 | 窄工具写入落在 taskDir、内容一致、`[TOOL]` 行 | ✅ 充分 | 工具层 9/9（append/write/bytes）；真管道 `[TOOL] worker_file progress.md` | L1 + 真管道 |
| Q-AC-006 | 12 类非法目标全拒、不产生新文件、`[TOOL_ERR]` 留痕 | ✅ 充分 | `[VERIFY] VC-006: rejections=12 new_files=0 schema_rejections=12`；真管道两例（execute 抛错 oversize + schema 拒绝 `task.md`）各得 `[TOOL_ERR] worker_file` | L1 四层 + 真管道两路径 |
| Q-AC-007 | 集合单一来源；表逐项不变 | ✅ 充分 | `[VERIFY] VC-007: table_unchanged=true extra_only_writeless=true types=10` | L0/L1 |
| Q-AC-008 | TS 表 ↔ Python REGISTRY parity 全绿 | ✅ 充分 | `pytest` 28 passed（含新 10-key 快照）；`test_autopilot_l0.py` 逐字节未改 | L0 |
| Q-AC-009 | `npm run check` exit 0；新增用例全绿；既有不新增失败 | ✅ 充分 | `npm run check` EXIT=0；10 文件 94 passed/1 skipped；T-6 独立跑 13 文件 430 passed + 8 文件 83 passed/1 skipped；89 项 Windows 基线不含本次触达文件 | L1 |
| Q-AC-010 | CHANGELOG + 文档与实现一致、零悬空 | ✅ 充分 | 两包 `[Unreleased]` 各一条；`rg 'progress\.md'` 命中逐处核对（practice guide §7 已改写；`pm-orchestrator.ts:556` 措辞已同步） | L1 |
| Q-AC-011 | 真派发冒烟三点成立 | ✅ 充分 | `evidence/verify-run-2026-09-23.md`：机器行 + 模型自评行（经 `worker_file`）+ 终稿无「无法写入/代为追加」+ `exit=0`；PM 直接读临时项目产物复核 | L2 真模型 |
| Q-VC-001 | 检查点机器行断言 | ✅ 充分 | 同上 Q-AC-001 | — |
| Q-VC-002 | append-only 断言 | ✅ 充分 | 同上 Q-AC-002 | — |
| Q-VC-003 | coding 无机器行断言 | ✅ 充分 | 同上 Q-AC-003 | — |
| Q-VC-004 | steer 分化断言 | ✅ 充分 | 同上 Q-AC-004 | — |
| Q-VC-005 | 工具写入 + `[TOOL]` | ✅ 充分 | 同上 Q-AC-005 | — |
| Q-VC-006 | 12 反例 + `[TOOL_ERR]` | ✅ 充分 | 同上 Q-AC-006（G1 补齐后 schema 路径也有真管道证） | — |
| Q-VC-007 | active set 逐 type | ✅ 充分 | `[VERIFY] VC-007`；T-6 逐 type 复现 | — |
| Q-VC-008 | parity | ✅ 充分 | 同上 Q-AC-008；变异 M-3 证明该用例真的能红 | — |
| Q-VC-009 | check + 基线 | ✅ 充分 | 同上 Q-AC-009 | — |
| Q-VC-010 | 文档同源 | ✅ 充分 | 同上 Q-AC-010 | — |
| Q-VC-011 | 真进程 e2e | ✅ 充分 | 同上 Q-AC-011（源码扩展 + tsx，非 bundle —— 见 ⚠️-2） | — |
| Q-COV-F1 | F1 正常/边界/异常三路 | ✅ 充分 | 锚点缩小（`timeout: 1/2`）、连续 3 次追加、append 到既有文件 | — |
| Q-COV-F2 | F2 三路 | ✅ 充分 | 无写角色替代动作 / 写角色逐字不变 / 短预算下文本仍含替代动作 | — |
| Q-COV-F3 | F3 三路 | ✅ 充分 | `progress.md` append、`report*` write、空名/超长名/仅扩展名/超大内容拒绝 | — |
| Q-COV-F4 | F4 三路 | ✅ 充分 | 逐 type 比对 + 未知 type 走 fallback 全量集 | — |
| Q-COV-F5 | F5 三路 | ✅ 充分 | 快照相等 + 变异 M-3 变红 | — |
| Q-X-001（交叉） | 分区任务（read scope）是否误拦窄工具 | ✅ 充分 | PM 源码核验 `worker-mode.ts:761-790`：非 read/ls/find/grep 的工具直接 `return undefined` | — |
| Q-X-002（交叉） | RAG 配置坏掉时只读角色是否丢落盘通道 | ✅ 充分 | 注册点在 RAG `try/catch` 之后（`worker-mode.ts:722-730`），设计期 D-106 已定；`npm run check` + 既有 rag 测试全绿 | — |
| Q-X-003（交叉） | 窄工具落盘是否让只读角色看起来「有产出」 | ⚠️ 不足 | 冒烟实测 `reads=16 writes=0 risk=high` | R-4：`writes` 语义有意不变（GC-4），PM 侧靠 `progress.md` 自评行 + `[TOOL] worker_file` 区分；已写入 design §9 / practice guide §7。验收接受 |
| Q-X-004（交叉） | 空内容写入（schema 之外的调用方） | ⚠️ 不足 | 写层不校验空串；schema `minLength: 1` 已断言拒绝 | R-5：真实调用必经 pi 校验；已登记 PM 复核日志。验收接受 |
| Q-X-005（交叉） | 全局 bundle 是否已含本次改动 | ✅ 充分 | `python mw.py build --install` EXIT=0；安装件与仓库 bundle SHA256 相同（`A7FCC952…64C`）且含 `worker_file`/`[machine]`；用**已安装 bundle**（默认发现，无 `-e`）真模型 re-smoke：机器行 + `[worker_file]` 两种模式（report 写 / progress 追加）+ `exit=0` | 原 ⚠️ 已由用户授权的构建 + bundle 路径 re-smoke 关闭 |

## 汇总

- **总问题数**: 29
- **通过（充分）**: 27（93%）
- **有条件通过（不足）**: 2（Q-X-003 / Q-X-004）
- **未通过（无证据）**: 0

**质检结论**: ✅ 通过（2 项 ⚠️ 均为「已记录并接受的残留」，非证据缺失；每项都有明确去向）

## 未通过问题行动计划

| 问题 | 根因 | 所需动作 | 负责 |
|------|------|---------|------|
| Q-X-003 | `writes` 只统计 `write`/`edit`（D-108 有意） | 不变更 GC-4 判据；如需区分另立 key 加独立计数 | 用户决定 |
| Q-X-004 | 写层只守安全属性（文件名白名单） | 若出现绕过 schema 的调用方，补写层空值守卫 | 未来 key |

## 二次印证结论

- 检查 1（约束覆盖）：GC-1（无服务端状态）/GC-2（仅 Extension API：`registerTool` + `on("tool_call")` + `before_agent_start`）/GC-3（只读角色仅 basename 白名单写入，框架文件 `task.md`/`trace.log`/`worker.log`/`output.md` 不可达）/GC-4（判据数值未动）均有 Q 覆盖。
- 检查 2（Function Flow 节点）：检查点定时 → 机器行落盘 → steer 分化 → 窄工具执行/拒绝 → trace 留痕，每个节点都有对应 Q-AC/Q-VC/Q-COV。
- 检查 3（异常路径行）：F3 的异常路径（12 类非法名 + 超大内容）有 Q-COV-F3 + Q-AC-006 双覆盖；F4 的未知 type 有 Q-COV-F4。
- 检查 4（绑定遗漏）：T-1~T-6 的 ac_refs/vc_refs 均非空；无遗漏绑定。
- 追加发现：G1（schema 拒绝路径缺真管道用例）已在 17:03 补齐（`agent-team-loop-checkpoint-wiring.test.ts` 新增 1 例，10/10 绿），不遗留。

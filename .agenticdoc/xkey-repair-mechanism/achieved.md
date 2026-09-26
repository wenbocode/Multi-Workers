# Achieved: xkey-repair-mechanism

key: `xkey-repair-mechanism` · phase: execute→verify · 基线: `6d98c5ee3` · ac_fingerprint `b944d7646135`

## 系统行为变化

**新增功能（全部默认关闭，per-project opt-in）**

1. **跨 key 冻结面修复通道**（`autopilot/xkey.py` 新模块 + `conductor.py` 挂载）——把"一个 key 合法更新的冻结期望在另一个 key 里变成无 owner 的红"从散文协议变成机器回路：
   - L3 prompt 的**必含节内**新增一行机器行（`cross_key_test=<path>::<test_id> owner=<key> handoff=registered not_fixed_by_this_key=True`），读侧从**全部 sources** 解析并折入 verdict-provenance sidecar 的新 `registration` 键；
   - 项目级账本 `.agenticdoc/_autopilot/xkey/ledger.json`（append-only history、锁内 RMW、`tmp`+`os.replace`），按 `(file, test_id, 冻结块 sha)` 幂等去重；
   - 一工单文件/请求（含 `request_id`、冻结块 `{file,symbol,line_range,old_block_sha256}`、`untouchable[]`、允许改的行集合）；
   - **只有完整登记**（可解析的 `(file,test_id)` + owner 能落到具体 key）才提案；散文形与角色值（`兄弟 key`/`PM`/`conductor`）一律只升级，**不猜 owner**；
   - 冻结块定位 = `fail_line → test_id → ast.FunctionDef → 模块级唯一引用 → Assign 行范围`，字节精确 sha256 + EOL 归一化副字段；定位歧义即降级"仅提案"。
2. **`xkey-authorize` gate**（两侧 kind 闭集镜像）+ `_gate_open` 的 `request_id` 维度（同一 pending 工单只抬一个 gate，封 6684 条/12h 洪泛）。
3. **仅人可答的可观测拒绝**（TS `shared/xkey-gate-guard.ts`，注册于 `index.ts` 全模式位置）：agent 工具层（`write`/`edit`/`bash`）触及 `.agenticdoc/_autopilot/gates/**` 被硬拦 + `[XKEY_GATE]` trace 行；读与 `xkey/` 提案树放行。
4. **追认后派发提案 worker**（恰好一次、有界重试、从盘重派生幂等）→ **边界前置校验**（越界/触 untouchable/涉及其它文件 ⇒ 零写盘）→ **应用**（写前按字节快照 `pre-apply.bak`）→ **conductor 侧 subprocess 验证**（未转绿 ⇒ 字节还原 + `verify_failed` + 不闭合）→ **五项证据包** → **账本闭合 + 两处标注**（幂等）。
5. **新配置键**：`xkey_repair`(false) / `xkey_verify_cmd`([]) / `xkey_verify_timeout_s`(1800)，**两侧逐字段一致**（Python `config.py` ↔ TS `status-model.ts`，均 fail-closed）。

**影响面**

- 关闭时（默认）：`conductor.py` 在 4 处门控 + 惰性 import 下零行为变化（实测 `tick=ok`、零 xkey 目录、零 xkey 事件）；既有默认套件 978→**1007 passed**（+29 新增），红数不变。
- 开启时：新增工件树 `.agenticdoc/_autopilot/xkey/`；L3 verdict-provenance sidecar 多一个 `registration` 键；新增一种 gate kind。
- 不改判定契约：`_l3_qualifies` 语义不变；`_parse_l3_output`/`_md_section` 区零改动；4-tuple arity 保持（登记经 `registration_out` sink 传出）。
- 不改护栏语义：越界修复仍是"作废"，只是从"散文禁止"变成"机械判定 + 零残留"。

**验证证据（本轮实测）**

| 层 | 结果 |
|---|---|
| 默认套件 | `2 failed, 1007 passed, 10 deselected`（红为两条外域先在，见遗留） |
| e2e_l2 重活套件 | `8 passed`（marker 迁移后无丢失） |
| 新增 L1（`test_autopilot_xkey_registration.py`） | `26 passed, 0 skipped`（含 VC-008/011/012 三条 `[VERIFY]` 行） |
| 新增 L2/e2e（3 例） | VC-009 合成全链 `fixture_red=1->0`；VC-010 FM 语料重放 `fm_replay_red=1->0` + `relaxed_assertion=False`；VC-002 散文形 `tickets=0 escalates=1` |
| 真实 FM 文件（只读） | `locate_frozen_block` → `TOP_LEVEL_GROUPS [243,244]`，sha 未变；FM 工作树零污染（锚点 sha 全等） |
| 跨包 config 一致性 | 我的独立对照：7 个用例 Python 与 TS 报错文本逐字段一致 |

## 遗留

| # | 遗留 | 去向 |
|---|---|---|
| 1 | **`packages/multi-workers/dist/extensions/agent-team-loop.js` 是 tracked 构建产物、仍含旧 5 类 kind 数组** | **接受并记录**：跑 dist 包的窗口在下次重建前拿不到新 kind/guard；发布流程会重建。与 D-009（conductor 必须与 kind 同版本上线）同源，已写入 CHANGELOG |
| 2 | 两条外域先在红：`test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below`、`test_autopilot_readcap_injection.py::test_baseline_left_end_bound` | **不属本 key**：均为外部项目 fixture 漂移（round 一致性/冻结件不一致），基线 `6d98c5ee3` 即红（T-01/T-03 各以 pristine 副本独立复现）；已通报对应域会话 |
| 3 | `xkey_repair` 目前**没有任何项目 opt-in**（FM/E2/MW 均关） | 立新 key 或用户指令后再启用；启用前须先配 `xkey_verify_cmd` |
| 4 | AC-004 的诚实残余面：**绕开工具层的同权限进程仍可直写 gate 文件** | 已写进 spec §2.3/design D-008 并作为证据披露项；非密码学证明，不声称更强 |
| 5 | 提案 worker 走真实派发通道（需 serve/配额），无 serve 时按有界重试后升级 | 接受；失败方向不覆盖，工单留 `approved` + escalation |
| 6 | 本 key 与前一 key 的提交（`9db229422` / `6d98c5ee3` / 本次）均**只 commit 未 push** | 待用户指令 |

# Research: partition parent 语义修正——扩展可写工作区（spec）

## 决策问题
回答 spec §1（parent 语义与范围：无切出、可写回）、§2（约束：fail-closed 与 parity 保持）、§4（风险：改动面清单与测试翻转点）。

## 调研方法与出处
- 现有实现通读（代码事实，2026-09-20）：
  - `packages/multi-workers/autopilot/dispatch.py:146-176`（`_expand_read_scope`：dual/partition 相对条目锚定 game/partition root；control root 缺失才追加；**parent root 明确不追加**——注释标注 "AC-008 red line"）
  - `packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts`（拦截算法：deny glob → scope 包含 → file cap → byte cap；`scope=null`（deny-only）无包含检查；`read_scope:` 存在但空 → 全拒 fail-closed）
  - `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:516-529`（拦截 wiring 仅覆盖 `read`/`ls`/`find`/`grep` 四工具；write/edit/bash 不经过 read-scope 层——**写路径现状即零拦截**）
  - `packages/multi-workers/mw.py:1302、2812`（`--parent` 缺参报错与 argparse help 均称 "read-only context for the partition"）
  - 双侧 profile 渲染 line protocol：`task-dispatcher.ts` `renderPartitionProfileBlock`（`Parent root: <path>` 行）↔ `mw_common.py:2239` `render_partition_profile_md`；golden：`packages/multi-workers/test/fixtures/partition-profile-block.golden.md:6` 与 TS 断言 `agent-team-loop-profile-injection.test.ts:345`
  - 旧 AC-008 断言位置：`test_partition_dispatch.py:604-620`（`test_partition_anchors_at_partition_root` 断言 parent 不在展开结果）
- 用户对话（2026-09-20 本 session）：
  - 修正 1：mw partition 功能中 "parent 只读不写回" 不对——partition 是把 parent 的功能切出完整的一块单独开发，开始内容要在 parent 内
  - 修正 2（追问澄清）：不需要专门的"切出"动作；就当 parent 是（分片的）扩展目录，直接开发就行，可以写回

## 发现
1. **唯一机械拦截点是读包含性**：带 `read_scope:` 的任务在 worker 侧受 scope 硬包含检查，parent root 不在允许集（Py 展开不追加 + worker 侧无 union）→ 今天有 scope 的 partition 任务读不了 parent。
2. **写路径本就无防火墙**：read-scope 层只 gate read/ls/find/grep；write/edit/bash 对任意路径（含 parent）不经该层。"可以写回"机械上已成立，无需新建，仅需回归锁定。
3. **两条派发路径不对称**：read_scope 展开只发生在 Py conductor 路径（`autopilot/dispatch.py`）；PM 窗口 TS 路径派发的任务 scope 原样进 task.md。只在 Py 侧追加 parent 会留下 TS 路径语义窟窿——worker 侧 union（从 profile 块解析 `Parent root` 行）使"parent 是扩展区"成为模式属性，两路径一致。
4. **deny 优先序不受影响**：`checkReadScopeCall` 中 deny glob 先于 scope 包含判定，parent 并入允许集不会绕过 deny_globs——partition 仍可对 parent 局部路径设防。
5. **空 read_scope 的 fail-closed 形态**：`read_scope:` 存在但空 = 全拒（任务配置错误的防御）。union 若作用于空 scope 会凭空造出包含集，违反"只扩大已声明的包含"红线 → union 仅作用于非空 scope。
6. **标签变更触点**：profile 块 `Parent root:` 行标签改动需同步 Py golden fixture、TS 注入断言、双侧渲染（既有 golden parity 用例保障一致性）；撕裂校验只解析 `[mw] mode:` 模式行，不受标签影响。
7. **根关系边界**：现行校验只约束 parent↔partition（相等/互嵌拒绝）；parent↔control 无约束（可能相等或嵌套）→ 追加 parent 时须与 control 同样的 normcase 去重。

## 结论 → 决策映射
- 支撑 §1.1：parent 语义 = 分片工作区的**扩展可写目录**（无切出/复制动作、无合并流程、写回=开发中直接写）；worker（cwd=partition root）默认可读（scope 并入 parent root）可写（现状锁定）。
- 支撑 §1.4 范围：不做切出命令、不做 merge-back 流程、不做写路径防火墙、roots 命名根仍显式声明、dual/single 与 cwd/撕裂/doctor/trace 语义零改动。
- 支撑 §2：fail-closed 既有路径不变（含空 scope 全拒）；TS/Py 渲染 parity；P-001/P-002 沿用。
- 支撑 §3 AC 与 §4 风险：AC-001（Py 展开）/AC-002（worker union）/AC-003（deny 优先）/AC-004（写零拦截回归锁定）/AC-005（措辞+标签+golden）/AC-006（零回归与修改面限定）；测试翻转点 = 旧 AC-008 断言 + golden/标签断言。

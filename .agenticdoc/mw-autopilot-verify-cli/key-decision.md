# Key Decision: mw-autopilot-verify-cli

- spec 锁定：v2（14 AC）· ac_fingerprint `9c90fbb3e171` · 基线 `b0a30bc12`
- 用户确认：**「按建议」**（U-1…U-6 全部采用 PM 建议）

## 用户可见决策（U-1…U-6，spec 期）

| 编号 | 问题 | 采用 | 理由 |
|---|---|---|---|
| U-1 | 是否纳入「机器级配置层」 | **纳入** | 这是让 `mw autopilot verify` 在**所有项目**可用的前提（跨机器/跨项目默认值），否则每项目手配 |
| U-2 | 是否纳入 cwd 根锚定 + 占位符展开 | **纳入（AC-013/AC-014）** | 不修则 verify 在 partition 模式下跑错目录 ⇒ 工单永不闭环（真实故障面） |
| U-3 | dist 防复发是否含 (c) 修 fail-open + (d) 脏树护栏 | **全纳入** | 只做"重建一次"是止血；fail-open 与并发构建污染才是复发机制 |
| U-4 | Python 侧 JSON 序列化是否改 `ensure_ascii=False`；整值 float 统一方向 | **改；方向以 RQ-D6 实测为准** | 实测 reviver 可精确判定 ⇒ 取 TS 拒绝非整数字面量（零 Python 语义改动） |
| U-5 | `clear` 是否删文件 | **永不删文件，只删键** | 文件缺失 = "autopilot 从未启用"（`config.py:8-9`、`monitor.ts:79`），删文件会改变语义 |
| U-6 | 防呆告警判 issue 还是 suggestion | **issue**（翻 healthy、退出码 1） | 显式启用后功能必然失效 = 链路正确性，非便利配置 |

## 设计期决策（U-7…U-12，RQ-D4 提出，PM 采纳全部建议）

| 编号 | 决策 | 结论 |
|---|---|---|
| U-7 | 锁路径 | **专用** `<root>/.mw/autopilot-config.lock`（不共用 `workers.lock`，避免配置写与派单串行） |
| U-8 | TS 侧改动是否属本 key | **属**（`status-model.ts` + `console.ts`）：只加 CLI 侧锁时实测 console 丢 28/30 次更新，AC-011 会空心 |
| U-9 | 残锁策略 | **不自动抢占** + 错误提示人工删除；不引入双写风险 |
| U-10 | 写前重读校验 | **不作为 AC 判据**（有 TOCTOU，仅单向兜底） |
| U-11 | 重试预算 | **可注入常量**（Python 模块常量 / TS `lockOpts`），避免用例真等 1.26 s |
| U-12 | AC-011 措辞 | 三段式：CLI 断言 + TS 断言 + 明确 TS 改动在范围内 |

## 技术决策（D-001…D-014，详见 design.md §1）

- **D-001** 删除 `cached_load` 的 mtime+size 短路：实测命中 85–109 µs **慢于**全读 60–70 µs，且同长度改写漏读 23.8% ⇒ 缓存净负收益，直接删（同时更快、更正确）。
- **D-002** 机器层 = JSON 文件 `~/.agents/autopilot-defaults.json`，覆盖域仅 xkey 四键，错误 **fail-soft 逐字段**（不整份作废）。
- **D-003** 新建 `autopilot/effective_config.py`；不改 `load_config` 语义；删除 AC 中的 "cli 层"（消费者是独立 conductor 进程）。
- **D-004** `load_config` 补默认键（`{**default_config(), **data}`）——新增键的前置修复，否则旧 config 文件让 conductor KeyError。
- **D-007** TS 侧用 `JSON.parse` reviver 第三参 `context.source` 拒非纯整数字面量（`4.0` 可判）；Python `save_config` 改 `ensure_ascii=False` ⇒ 两侧产物字节可完全相同。
- **D-008** 新增 `mw_common.render_argv`（逐元素 whole-token，嵌入占位 fail-closed）；`render_toolchain_command` 一行不改；同族 5 处 control 根锚点**必须一起重锚**。
- **D-009** dist 防复发 = A1b kind 集合锚点 + A2b sourcemap `sourcesContent` 内容锚点 + `_apply_update_env` S1 先 build 后 deploy + `_deploy_bundle` 顺序修正；判据带 `-c core.fileMode=false`。
- **D-010** 脏树护栏拦 `packages/*/src`，`--allow-dirty` 绕过，非 git 跳过。
- **D-013** 跨语言判据主载体在 TS vitest（CI 覆盖），Python 侧半表；**对端缺失即硬失败**。

## 诚实记录

- **PM 直执的 dist 重建**（`d52694cc4`）发生在用户即时指令早于本 key 立项之时；证据固化于 `evidence/spec-dist-rebuild-performed-20260926.md`，AC-009 因此收窄为"判据固化 + 可机器检测"，不重复造检测。
- **执行期波次修订**：T-02 原定波 1，因其断言依赖 T-01 的 13 键/合并语义 ⇒ 实际移至波 2（plan.md §1 已记）。

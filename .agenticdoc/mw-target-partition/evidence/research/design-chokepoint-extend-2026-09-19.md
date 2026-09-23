# Research: 共享解析入口的扩展方式与零回归手段（design）

## 决策问题
支撑 design D-001（单一 choke point 内部分支 vs 双入口）、D-002（TS 类型策略）、D-007（错误消息）、D-009（doctor/probe 兼容）、D-011（parity 测试布局）。

## 调研方法与出处
- `load_target_config` 全部调用点（git grep）：mw.py:623（target show）、mw.py:644（model set 兼容检查）、launcher.py:631（_worker_cwd）、autopilot/dispatch.py:264（派发 scope/deny 解析）；`resolveWorkspaceConfig`：pm/task-dispatcher.ts:100（profile 注入）+ 测试两侧。
- parity 夹具机制：`packages/multi-workers/test/fixtures/target-config-cases/`（case.json：env/expect/error/render），双跑——Py `test_common_target_config.py`（_run_case，fixtures 目录拷贝到 tmp）与 TS `agent-team-loop-target-config.test.ts:288-360`（cross-package URL 引用同一目录，stubEnv 映射）。既有 case 001-012+。
- profile 注入已有独立测试文件 `agent-team-loop-profile-injection.test.ts`（AC-007 可镜像其模式）。
- `/mw target` 命令模式：ui-bridge.ts:1371-1450——flag 解析 + 可注入 runner（`runner: (projectDir, args) => MwCliResult = targetMw`），测试用 fake runner 断言转发参数与 usage 通知（agent-team-loop.test.ts:4227+ describe "/mw target"）。mw-runner.ts 已有泛化 `runMwCli(sub, ...)`（mw-dispatch-models 引入），partitionMw 只需一行包装。
- 错误字符串断言检查：git grep "is unusable" 仅命中源码（launcher.py:633、dispatch.py:268），无任何测试断言该字面量 → 错误包装消息可按活跃文件名动态化，不破坏测试。
- doctor/probe 现状：mw_common.py `_doctor_target`——section JSON 键 = config{mode,source,game_root,engine_root,vcs,uproject} + checks + probe_cache；缓存 `.mw/toolchain.json` = {probed_at, probed_at_epoch, checks}，新鲜度按 target.yml mtime 比较（mw_common.py:1800 附近）。旧缓存无 active-file 字段。
- AC-016 基线可行性：dual/single 样例的期望输出可直接在 main 上先录制（测试先行）：解析字段、_worker_cwd、_expand_read_scope、注入块全文（profile-injection 测试已能全文断言）、target show 输出（test_mw_target.py 模式）、doctor 段 JSON（除时间戳）。

## 发现
1. 单一 choke point 只有 5 个产品调用点 + 2 个测试入口；双入口方案会把"选哪个解析器"扩散到所有调用点且 doctor/show 还要先探文件——违背 D-005（mw-dual-workspace）确立的单点解析原则。
2. TS `WorkspaceConfig.gameRoot` 的产品消费面：task-dispatcher（dual 分支内）、renderToolchainCommand（{game} 分支）、discoverUproject（仅 dual 路径调用）、launcher 用 Py 侧。改为 `string | null` 的波及面=类型收窄处，行为波及=0（partition 下这些路径不走）。
3. parity 夹具 schema 需增量字段（parent_root_rel / partition_root_rel / roots / partition_root_equals_control）；两侧 runner 的字段断言都是 optional-guard（undefined 跳过），加字段是纯增量。
4. doctor 段 JSON 对 dual 若新增键会破坏 AC-016(e) 逐字节一致 → active-file 信息只进 cache JSON，不进 doctor 段；partition 模式才在 config 子键中加 parent_root/partition_root/roots。
5. 旧缓存无 active-file 键 → 按"陈旧"处理重探测一次（探测是幂等 isdir 检查，一次性成本可接受）。

## 结论 → 决策映射
- D-001 选单入口内部分支：入口前置于 `_decide_active_mode(P,T,EP,ET)` 纯函数（AC-014 参数化测试的单点）。
- D-002 选 interface 增量扩展 + gameRoot 可空：判别联合需全下游 narrowing，零回归风险大。
- D-007 错误包装消息按活跃文件名动态化：无测试断言字面量，dual 语义不变。
- D-009 doctor 段 schema 零新增（dual/single）；active_file 进 cache JSON；旧缓存视为陈旧。
- D-011 parity 复用既有 fixtures 目录 + 两侧 runner 增量字段 + 续号 case；CLI 新文件 test_mw_partition.py；TS /mw partition 新 describe；AC-016 基线先行录制。

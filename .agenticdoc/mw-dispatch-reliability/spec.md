# Spec: mw-dispatch-reliability

> Key: mw-dispatch-reliability
> 创建时间: 2026-08-28
> 状态: confirmed

## §1 功能概述

### 1.1 目标

让 Multi-Workers 的多 worker 调度从当前的"崩溃循环"变为**可靠可跑通、可诊断、可回归验证**。

现状断点（2026-08-28 实测）：队列中一个缺 `ANTHROPIC_AUTH_TOKEN` 的 pending claude 任务
导致 launcher 抛 FATAL → mw serve 整体退出 → PM 自动重启 → 无限循环；该任务永远卡在
pending；PM 播报"[mw] Background service started."假成功。同时存在陈旧条目无治理、
全局扩展 bundle 与源码不一致、单测不密封（读真实 `~/.timi-anthropic-proxy/config.toml`）、
smoke_test.sh 假阳性等问题。

三个交付面：

1. **可用性修复**：单任务缺凭证隔离处理（不杀服务）；路由凭证可用性预检；陈旧条目归档；假成功播报修复。
2. **可诊断性**：`mw doctor`（CLI + pi 内 `/mw doctor` 双入口）全链诊断与自动修复。
3. **可测试性**：L0 单测密封化；L1 集成测试（假 CLI 注入，零 LLM）；L2 E2E smoke（真实调用）。
   全部测试并入正式测试文件，不保留游离脚本。

### 1.2 技术栈 / 语言

| 组件 | 语言 / 运行时 | 角色 |
|------|-------------|------|
| launcher.py / mw.py | Python ≥3.10 | 调度循环、服务管理、预检、doctor、归档 |
| agent-team-loop 扩展 | TypeScript（Pi Extension） | PM 播报修正、/mw doctor 入口 |
| providers.json（扩展 schema） | JSON | 路由 + 凭证来源配置（env / 配置文件） |
| test_launcher.py / test_integration.py | pytest | L0 / L1 |
| packages/coding-agent/test/ 下新 vitest 文件 | vitest | TS 侧 store/lock 断言（并入原 test-l1-full.ts） |
| smoke_test.sh / E2E 脚本 | Bash + 真实 pi | L2 |

### 1.3 核心用户场景

1. **S1 混合队列隔离调度**：队列同时含缺凭证的 claude 任务与凭证可用的 pi/timi 任务。
   缺凭证任务被标 `failed`（exitReason 注明缺失 env var），服务存活，其余任务照常调度完成。
2. **S2 启动预检**：mw serve 启动时枚举各路由凭证可用性写入 mw.log；全部路由不可用时
   拒绝启动并输出缺失清单；部分不可用时告警继续。
3. **S3 陈旧条目治理**：task.md 已不存在的 pending/running 条目，由周期扫描移入专门归档，
   队列不再被死条目阻塞。
4. **S4 doctor 诊断与自愈**：`python mw.py doctor` 或 pi 内 `/mw doctor` 一条命令输出
   服务/端口/日志/队列/凭证/bundle/孤儿 proxy 全链诊断；可自动修复项自动执行并汇报。
5. **S5 真实成功反馈**：mw 启动失败时 PM 不再播报假成功；mw_status 短时间内如实报告。
6. **S6 回归防线**：L0/L1 全绿且密封（不依赖机器上的真实凭证文件）；L2 用真实 pi/timi
   小任务验证全链（pending→running→done、output.md、PM 播报）。
7. **S7 凭证来源可配置扩展**：新 provider/新凭证来源（配置文件路径+字段）通过配置声明即可用，
   不改 launcher/mw 代码。

### 1.4 范围说明（不做什么）

- 不新增 `blocked` 之类的新任务状态（缺凭证复用 `failed`，靠 exitReason 区分）
- 不自动重建扩展 bundle（doctor 仅警告过期并提示 `/mw build`）
- 不自动杀孤儿 proxy（仅检测报告 + 给出处置建议）
- 不改 proxy_multi 上游路由逻辑、不引入中心化调度器（文件总线 + 文件锁不变）
- L2 真实调用仅覆盖 pi/timi 路由（本机唯一有凭证的路由）；claude/codex 路由由 L1 假 CLI 覆盖
- 不做 Web UI / dashboard，不做 CI 集成

## §2 业务约束

### 2.1 平台 / 环境

- 主开发/验证平台：Windows（PowerShell），launcher/mw 现有 POSIX 分支保持不回退
- Python ≥3.10（本机 3.14），Node ≥22.19；pytest 本地直接运行，TS 侧测试走根仓 `./test.sh`
- 多写者环境：PM（TS）、launcher（Python）、doctor 并发读写 `_workers.parallel`，
  跨语言锁协议（O_CREAT|O_EXCL）必须两侧一致

### 2.2 性能指标

- doctor 单次执行 < 5s，不做网络调用（仅本地进程/文件/端口检查）
- 预检开销 < 1s；陈旧条目归档时延 ≤ 2 个 poll 周期（≤10s）

### 2.3 安全约束

- 任何日志/诊断/归档输出不得泄露明文凭证（沿用 mask 规则；归档文件只含队列行 + 原因）
- 凭证隔离语义不变：worker 子进程仍只拿到自己路由所需凭证

### 2.4 集成依赖

- timi-proxy-cli（LocalProxyServer，端口 7001/7003/7004）
- pi 扩展机制（全局 bundle `~/.pi/agent/extensions/agent-team-loop.js`，`/mw build` 重建）
- 根仓 `./test.sh`（vitest，无 e2e env 时跳过 LLM 相关）；pytest 本地运行

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-08-28T16:30:00+08:00，编号永不回收

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在 `_workers.parallel` 含 1 个缺 ANTHROPIC_AUTH_TOKEN 的 pending claude 任务与 1 个凭证可用的 pending pi/timi 任务的条件下，launcher 处理后，claude 任务状态为 failed 且其 worker 侧产物（output.md 或 worker.log）注明缺失的 env var 名，pi/timi 任务状态进入 running 或 done，且 launcher 与 mw serve 进程持续存活 ≥ 60s |
| AC-002 | 在所有已配置路由凭证均缺失的条件下，mw serve 启动在 10s 内以非零退出码退出，mw.log 列出每个路由缺失的凭证来源清单 |
| AC-003 | 在至少一条路由凭证可用的条件下，mw serve 启动后 mw.log 记录全部路由的预检结果，每路由 1 行 available/missing 标记 |
| AC-004 | 在 `_workers.parallel` 存在 task.md 已不存在的 pending 条目的条件下，mw serve 运行中该条目在 ≤ 10s 内从队列移入归档文件（`.agenticdoc/_workers.stale.parallel`），归档行含原行内容 + 归档时间 + 原因 |
| AC-005 | 在 mw serve 启动后实际死亡（如预检失败退出）的条件下，PM 会话播报中不出现 "Background service started" 字样，且 mw_status 工具在 10s 内报告 not running |
| AC-006 | 在任意项目目录运行 `python mw.py doctor --project=<dir>` 的条件下，命令在 5s 内完成并输出 ≥ 7 项诊断（mw 进程、proxy 端口、launcher.log 尾部、非终态任务及 task.md 存在性、路由凭证可用性、bundle 与源码 mtime 比较、孤儿 proxy），每项 1 行结论，健康时退出码 0、异常时退出码 1 |
| AC-007 | 在 pi PM 会话内执行 `/mw doctor` 的条件下，TUI 播报与 CLI 同源的诊断摘要（复用同一 doctor 数据来源，非两套实现） |
| AC-008 | 在 doctor 以修复模式运行（`--fix` 或 `/mw doctor fix`）的条件下，可自动修复项（陈旧条目归档、陈旧 mw.pid 清理）被执行并输出修复清单，不可自动修复项（bundle 过期、孤儿 proxy）仅输出建议不动手 |
| AC-009 | 在存在真实 `~/.timi-anthropic-proxy/config.toml` 的机器上运行 `python -m pytest test_launcher.py test_integration.py` 的条件下，全部用例通过，且无任何用例发起真实 LLM 请求或 spawn 真实 pi/claude/codex 子进程 |
| AC-010 | 在 L1 集成测试以假 CLI 注入 PATH 并放入 exit 0 与 exit 1 两个 pending 任务的条件下，launcher 在 30s 内分别将其置为 done 与 failed，且两个任务目录下 worker.log 均生成 |
| AC-011 | 在 L1 集成测试以 `--max-workers=1` 放入 2 个 pending 任务的条件下，第二个任务的状态变为 running 的时间晚于第一个任务进入终态的时间（串行可观测） |
| AC-012 | 在 8 个并发 WorkerStore.upsert 与 launcher 状态写同时运行的条件下，最终 `_workers.parallel` 包含全部并发写入的行，无丢失行（L1 测试内断言） |
| AC-013 | 在 L2 E2E smoke 以真实 pi/timi 执行 prompt 为 "Say exactly: ok" 的任务的条件下，任务在 120s 内状态为 done，output.md 含 "## Summary" 节且文件 > 50 字节 |
| AC-014 | smoke_test.sh 的任务检测断言在任务未被检测到时判 FAIL（删除现有 else 假阳性分支），修复后脚本在该失败场景下退出码为 1 |
| AC-015 | 原 test-l1-full.ts 的全部断言并入 `packages/coding-agent/test/` 下正式 vitest 文件，`./test.sh` 运行通过，且游离脚本 `packages/multi-workers/test-l1-full.ts` 被删除 |
| AC-016 | 在 providers 配置中为某路由声明配置文件凭证来源（文件路径 + 字段定位）的条件下，launcher 从该文件读取凭证并完成该路由预检与 worker env 注入，无需设置对应 env var |
| AC-017 | 在仅修改 providers 配置（增删路由或凭证来源、不含内置 CLI 语义）的条件下，预检、env 构建、doctor 输出反映新配置，launcher.py / mw.py 代码零改动 |

## §4 风险与未决项

### 风险

- **跨语言文件锁一致性**：归档重写 `_workers.parallel`（launcher/doctor 侧）与 PM 侧 upsert
  并发，锁协议不一致会丢行或死锁——L1 并发用例（AC-012）作为防线
- **detached env 继承偏差**：预检反映 mw serve 进程的 env，可能与用户交互 shell 不同
  （例如用户 profile 里设了 token 但 pi 启动环境没有）——doctor 需明示"以 mw 进程 env 为准"
- **L2 依赖真实上游**：timi 上游故障会让 smoke 误报——L2 脚本标注"需真实凭证可用，失败时人工判断是否上游问题"
- **Windows 端口 TIME_WAIT**：mw serve 快速重启受 7001/7003 重绑影响（已有 retry，保持）

### 待确认（默认按 AI 推荐执行，spec 审核时可否决）

- 归档文件名 `.agenticdoc/_workers.stale.parallel`，追加式（不清空）[AI 推荐]
- doctor CLI 输出英文（键名机器可 grep），`/mw doctor` TUI 播报中文摘要 [AI 推荐]
- 周期扫描的实现载体（launcher poll 内 vs PM 轮询内）属设计决策，留待 design.md [AI 推荐：launcher 侧，保持 PM 只增不改]

## §5 记忆前馈（对接项目级记忆门禁）

> 三份记忆文档（_project_log.md / _arch_snapshot.md / _pitfalls.md）当前均不存在，
> 项目记忆门禁自动跳过。本节为占位。

### 可复用资产

（项目记忆尚未建立；本 key 完成后建议沉淀：文件锁双实现、假 CLI 注入测试法、
预检/doctor 模式）

### 需规避坑点

（项目记忆尚未建立；本 key 已知坑点将随 evidence 落盘：FATAL 连坐、
config.toml 兜底导致测试不密封、smoke T5 假阳性、bundle 过期静默）

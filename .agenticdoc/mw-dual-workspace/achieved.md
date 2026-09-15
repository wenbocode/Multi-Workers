# Achieved — mw-dual-workspace

## 做了什么

在 agent-team-loop / mw 框架上实现「双工作区」：控制工作区（框架协调文件所在仓库）与目标工程（UE Game/Engine 源码树）物理分离，目标树零框架污染。按 4 stage × 12 task 交付：

**S1 配置层**
- TS `shared/target-config.ts`：`.agenticdoc/target.yml` 解析（mode/game/engine/vcs/uproject + toolchain/ignore/contract 三节）、`{game}/{engine}/{uproject}` 占位符渲染、game 根唯一 `.uproject` 发现、fail-closed 校验（invalid-yaml/invalid-config/missing-field/uproject-not-found/ambiguous-uproject 与 Py 侧错误类别 parity）
- Py `mw_common` 镜像实现 + 14 个共享 parity fixture（`test/fixtures/target-config-cases/`，双侧同 fixture 跑，36+5 用例）
- `mw target set/clear/show` CLI（行级键更新保全手维三节）+ `mw doctor` target 检查节 + `.mw/toolchain.json` 探测缓存

**S2 worker 层**
- read-scope deny globs：`deny_globs` frontmatter → 四类工具（read/ls/find/grep）调用级防火墙，双基准匹配（绝对 + game 根相对）、deny 优先于 scope allow、deny-only 模式（无 scope 也防火）；执行期抓出并修复纯 minimatch 的「裸目录列内容」漏洞（尾部 `/**` 额外匹配目录本身）
- worker 双根：launcher dual spawn cwd=game（每次 spawn 解析配置，`mw target` 切换即时生效）；控制根由 PI_WORKER_TASK 五层推导（零新增 env）；trace/output/phase/goal-check 全锚控制根

**S3 dispatch 层**
- Py `dispatch.py`：dual 下相对 scope 锚 game 根展开 + 控制根附加（去重）、deny_globs 默认注入（显式覆盖胜出）、broken yml fail-closed 拒派（`target-config-rejected` 事件）；single 无 yml 快照逐字节不变
- TS `task-dispatcher.ts`：派发时注入 profile 三节要点（toolchain 占位符**派发时解析**、ignore 防火墙、contract 含 docs 引用行）+ 控制根绝对路径 + deny_globs frontmatter（与 Py 同格式）；幂等/任务级覆盖尊重/逐任务隔离失败自愈

**S4 集成验证**
- 跨盘 e2e（env 门控，真实 F:/E:/）：dispatch→跨盘 worker→game/engine 树框架文件计数 0、控制根齐全
- goal check（AC-008）与 staleness（AC-009，控制根源码 mtime 基准、game 新产物不误报）双根用例
- serve 根绑定锁定用例（AC-009，零代码改动）
- 全量回归：check 0/0/0、multi-workers 402 全绿、agent/coding-agent 相对 89 例基线 new-failures=0

## 收益达成（9 AC → 证据）

| AC | 内容 | 证据 |
|---|---|---|
| AC-001 | single 模式零回归 | runs/011（check 0/0/0、new-failures=0、快照断言） |
| AC-002 | 目标树零框架文件 | runs/008（跨盘全链 target-tree-hits=0）+ runs/005 |
| AC-003 | worker 双根执行（cwd=game、协调写锚控制根） | runs/005（VC-004/005/009） |
| AC-004 | toolchain 占位符渲染 fail-closed | runs/001/002（T-17 parity）+ runs/007（派发时解析） |
| AC-005 | 配置/指令切换即时生效 | runs/003（CLI）+ launcher 逐 spawn 解析（005） |
| AC-006 | deny globs 防火墙 | runs/004（VC-011/012，100% block）+ runs/006/008 |
| AC-007 | profile 三节注入 task.md 自包含 | runs/007（VC-013）+ runs/006 |
| AC-008 | goal.md 追踪双根不变 | runs/009（VC-014） |
| AC-009 | serve 全锚控制根 + staleness 基准 | runs/010（VC-015）+ runs/009（VC-016） |

测试资产：TS 新增 4 文件 + 扩展 2 文件（36+7+24+4+2+2 ≈ 75 用例）；Py 新增/扩展 5 文件（14+5+12+7+1+3+1 ≈ 43 用例）；双侧共享 14 fixture。

## 遗留什么

- **P4 工作区无 .gitignore**（F:\ProjectH 实证）：find/grep 遍历不排除 DDC/Intermediate，但每次调用被输出截断与 read-scope caps 限流，洪泛有界（D-004 已知限制）；L1 deny 防火墙不受影响
- **LongPathsEnabled=1 机器依赖**（D-008）：本机实测 319 字符路径 OK，未开启的机器属环境问题，未做 `\\?\` 前缀守卫
- **目标工程 VCS 与游戏 CI 后置**（D-012 用户拍板）：框架 git 子命令继续作用于控制工作区；Game=P4/Engine=git 的操作是任务内容由 worker bash 直跑，先手动提交；VCS/CI 抽象必要性后续讨论
- **口径外测试观察**（非本 key，runs/011 §4）：ai timi-models 1 败（已提交的 catalog 18 vs 测试快照 15 漂移，ai-baseline-repair 清零后再次漂移，需独立处理）；evals artifacts 1 败；server 30 败全 Unix socket 类（Windows 结构性）
- **CHANGELOG**：coding-agent [Unreleased] Added 追加 4 条；multi-workers 新建 CHANGELOG（首次成文）——均未 commit，待用户决定

# Quality Gate Report: mw-dispatch-role-escape

**时间**: 2026-09-20T21:05:00+08:00
**触发**: Stage 完成（EXECUTE 出口，合入前自检）
**范围**: 全量（AC-001~011 / VC-001~013）
**执行者**: PM 窗口自查（无独立 review worker；用户如需独立评审可另派）

## 前置门禁

| 检查项 | 结果 |
|--------|------|
| spec.md 存在 AC 编号 | ✅ AC-001~AC-011（fingerprint `b944d7646135`） |
| design.md 存在 VC 编号 | ✅ VC-001~VC-013 |
| AC→VC 映射 100% | ✅ 11/11（AC-011→VC-012） |
| evidence-requirement.md 存在 | ✅ 含锁定指纹与逐条充分性标准 |
| ac_fingerprint 一致 | ✅ `b944d7646135` |
| evidence/baseline/ 非空 | ✅ 缺陷态基线（口径见文件头：新参数改动前不存在，无法构造 L2 运行基线） |
| 每个 task 有非空 ac_refs/vc_refs | ⚠️ 本 key 的 tasks/*.md 以「覆盖: AC-xxx / VC-xxx」文本行绑定，未用结构化字段；已逐条人工核对，无空绑定 |

## 问题清单与核查结果

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-AC-001 | pi 任务可声明 type，review/research role 可达 | ✅ 充分 | VC-001 单测 + smoke `source=config:review` + trace `type=review` | 端到端三处一致 |
| Q-AC-002 | 非法 type 拒绝且无半成品 | ✅ 充分 | VC-001（目录不存在 + 队列无行） | — |
| Q-AC-003 | `/worker --type` 与工具同语义 | ✅ 充分 | VC-002（TS 单测 handler）+ live RPC 证据（2026-09-21，见文末补记） | 命令路径 live 证据已闭环 |
| Q-AC-004 | 偏离必须给理由 | ✅ 充分 | VC-003 + VC-013 + smoke 拒绝返回 + 无目录 | 含 BOM 配置分支 |
| Q-AC-005 | 等值不 pin | ✅ 充分 | VC-004 + smoke `smoke2-ok/task.md` 无 model 行 | — |
| Q-AC-006 | 理由落盘单行 | ✅ 充分 | VC-003（多行折叠）+ smoke 产物 `model-reason:` | — |
| Q-AC-007 | 模型 id 校验 | ⚠️ 不足 | VC-005 矩阵 + VC-006 + VC-008 + smoke 拒绝 | 欠债：非 pi 窗口直接调用 `mw.py model set` 无 id 校验（设计 D-004 明确边界） |
| Q-AC-008 | 成功派工回显 type/role/模型层 | ✅ 充分 | VC-001/003/004 + smoke 三次返回原文 | — |
| Q-AC-009 | launcher override 证据行 | ✅ 充分 | VC-009（note 四分支 + spawn capsys）+ 真实 launcher.log 两行 | — |
| Q-AC-010 | 零回归 | ✅ 充分 | VC-010 逐字节 + 168/168 + 692 passed + check 0/0/0 | — |
| Q-AC-011 | 文档同步 | ✅ 充分 | 三份文档 diff（CHANGELOG ×2 + README 小节） | — |
| Q-VC-001 | type 三值/省略默认/非法拒绝 | ✅ 充分 | runs/run-2026-09-20.md §2.1、§2.5 | — |
| Q-VC-002 | /worker 命令路径 | ✅ 充分 | 同 Q-AC-003（live RPC 证据） | 与 Q-AC-003 同一欠债，已闭环 |
| Q-VC-003 | reason 门 + 理由落盘 | ✅ 充分 | §2.1 + §2.5 | — |
| Q-VC-004 | 等值不 pin | ✅ 充分 | §2.1 + §2.5 | — |
| Q-VC-005 | 校验矩阵（10 分支） | ✅ 充分 | §2.1 | — |
| Q-VC-006 | 生效 role 值非法 fail-closed + 逃生口 | ✅ 充分 | §2.1 | — |
| Q-VC-007 | readRoleModel / role 映射 / legacy 推导 | ✅ 充分 | §2.1 | — |
| Q-VC-008 | `/mw model set` 前置校验 | ✅ 充分 | §2.1 | — |
| Q-VC-009 | launcher override 行 | ✅ 充分 | §2.1 + §2.5 | — |
| Q-VC-010 | legacy frontmatter 逐字节 | ✅ 充分 | §2.1、§2.5（smoke2-ok 无 model 行） | — |
| Q-VC-011 | Python 全量 + role parity | ✅ 充分 | §2.2 | — |
| Q-VC-012 | check 0/0/0 + 文档 | ✅ 充分 | §2.3 | — |
| Q-VC-013 | BOM parity（双侧） | ✅ 充分 | §2.6 + 双侧测试 | 执行期新增发现，已修复并锁定 |
| Q-COV-001 | 首次 smoke 暴露的 BOM fail-open 分支 | ✅ 充分 | §2.6（修复前/后对照 + 双侧测试） | 发现即修复 |
| Q-COV-002 | tmux 交互式冒烟（AGENTS.md 推荐路径） | ✅ 充分（替代口径） | §2.5（print 模式 + 文件系统断言） | 本机无 tmux；已用安装后 bundle 的 `-p` 无人值守替代并落盘产物证据 |
| Q-COV-003 | 重新派工 smoke 对既有 serve/其他窗口的副作用 | ✅ 充分 | §2.7（临时项目独立 serve 已停、清理完成、框架 serve 未受影响） | — |

## 汇总

- **总问题数**: 26
- **通过（充分）**: 25
- **有条件通过（不足）**: 1（Q-AC-007 的 CLI 直调边界；Q-AC-003/Q-VC-002 已于 2026-09-21 补证关闭）
- **未通过（无证据）**: 0

**质检结论**: ⚠️ 有条件通过（剩余验证欠债 1 项，建议接受）

## 未通过问题行动计划

| 问题 | 根因 | 所需动作 | 状态 |
|------|------|---------|------|
| Q-AC-003 / Q-VC-002 | 本机无 tmux；`pi -p` 无法输入 slash 命令 | ~~用户在交互窗口执行一次~~ → 已用 RPC 模式（`pi --mode rpc`，extension command 可经 `prompt` 执行、notify 经 `extension_ui_request` 回传）代跑全 8 用例 | ✅ 已闭环（2026-09-21，见文末补记） |
| Q-AC-007（边界） | Python 侧无模型表，无法校验 `mw.py model set` 的 id | 已由 `/mw model set`（pi 窗口）前置校验 + 派发期校验覆盖主路径；纯 CLI 用户依赖 pi 侧报错 | 建议接受；如需彻底覆盖需引入模型表 artifact（新 key） |

## 二次印证结论

- 检查 1（spec 约束全覆盖）：pi 路由校验、CLI 前缀豁免、registry 缺失容错、BOM 容错均已建 Q 并核查。
- 检查 2（Function Flow 节点）：mermaid 六个分支（拒绝/等值/覆盖/无显式/校验/落盘）均有对应 VC。
- 检查 3（异常路径）：非法 type、缺 reason、非法 id、非法 role 默认值、registry 缺失、未知 prefix、BOM —— 全部有对应用例。
- 检查 4（task 绑定）：T-01/T-02/T-03 的「覆盖: AC/VC」行与本文问题清单一致，无遗漏绑定。
- 未发现新增遗漏问题。

## 补记（2026-09-21）：Q-AC-003 / Q-VC-002 live 证据闭环

原报告认为「本机无 tmux、`pi -p` 无法输入 slash 命令」导致命令路径无 live 证据。
2026-09-21 改用 **RPC 模式**解决：`pi --mode rpc --no-session`（真实 pi 进程，加载全局安装的
agent-team-loop bundle）中，extension command 可经 `prompt` 命令直接执行，notify 以
`extension_ui_request(method=notify)` 回传 stdout，无需 TTY 即可采集通知原文。

按 `evidence/runs/manual-test-worker-command-2026-09-20.md`（2026-09-21 修订版）在本仓
执行全 8 用例（TC-0~TC-7），**全部通过**：type 声明可达 review role、无理由覆盖被拒、
带理由覆盖落盘 `model-reason:`、非法 type / 非法模型 id 拒绝且无半成品、等值不 pin、
`/mw model set` 写盘前校验。全程序日志与逐用例证据见
`evidence/runs/manual-test-worker-command-2026-09-20.md` 结果表与
`evidence/runs/rpc-driver-2026-09-21.log`。

附带行为发现 F-1：`/worker` 的 flag 解析按空白切分，不支持带引号的多词 `--reason`
（会吞掉后续 `--key`，见测试文档「执行发现」）；多词理由需连字符或改用工具路径。
后续改进候选，不阻塞本欠债关闭。

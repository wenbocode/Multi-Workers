type: research
images: no
write_scope: .agenticdoc/mw-dp-consolidation/workers/dpc-t05-handoff-audit, .agenticdoc/mw-dp-consolidation/evidence
card_path: tasks/T05-handoff-audit.md
card_sha256: f8013aded34e40b352c15b1bb738057a80c674028afd4a9580b67e897adc90a2
envelope_producer: agent-team-loop-pm@0.83.0
write_face: .agenticdoc/mw-dp-consolidation/evidence/implementation/t05-handoff-audit-20261027.md

<!-- mw-write-surface: v1 -->
- 允许写：本任务目录下的 worker_file（progress.md | report.md | report-<slug>.md）；write_scope: .agenticdoc/mw-dp-consolidation/workers/dpc-t05-handoff-audit, .agenticdoc/mw-dp-consolidation/evidence
- 不得写：本任务目录之外的任何路径（pm-state.md、workers/_workers*、_index.parallel、其他 key、packages/**、.git/**）
- 越界后果：运行期 bash 写面守卫 block + [TOOL_ERR] + trace 审计行
<!-- /mw-write-surface: v1 -->

<!-- mw-dispatch-card: v1 -->
## 上下文

项目目标 `.agenticdoc/goal.md:5`；原卡 `.agenticdoc/mw-dp-consolidation/tasks/isolated/T05-eight-cases.md:35`，当前测试 `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_workbench.py:1`；同key spec/design/plan及implementation-isolated-dag.json只读。原36逻辑任务/7stage/目标/依赖不变，本卡仅T05交接证据补核，不新增第37实现任务，不提前执行T27/T28/T29或正式T33～35审计。
T05-R2-envelope已done/exit0/acked，PM原负例byte-identical重跑及更强模板控制三个rc0见 evidence/implementation/t05-r2-envelope-pm-handoff-20261027/。两根因修复/原28函数字节及AST保持已独立确认，整文件worker仍12F18P、PM尚未重跑；T10五输入当前稳定但完整资格待核。八case合法不意味着生产权限或整体完成。

## 要求

1. 完整分段读当前采用workbench测试到实际EOF(当前2368LF)，截断继续；读真实失败原stdout到EOF：evidence/implementation/dpc-t05-eight-cases/rework-r2-envelope/logs/full-workbench-suite-window.stdout，与原dpc-t05-eight-cases/comparison-baseline-vs-final.json及对应旧日志比较。只读当前生成器/模板和PM新probe必要段，不把搜索/AST/worker声明冒充EOF。
2. 精确列出12个失败名、实际异常/断言、fixture输入→production call→失败位置；逐项追到当前隔离源码根因和最小必要修改路径，区分registry(T03)、context(T04)、history(T27)、server(T28)、web(T29)、测试(T05)或未列面。不是沿用原报告owner口号；给可解析path:line和原卡exact权限佐证。采用的production主文件须读EOF或明确未读范围及结论限制。
3. 核原DAG T11/T12/T17等依T05/T10，T27/28/29的前置路径。判断是否存在“必须全workbench绿才能完成T05，而修这些测试所需owner反依T05”的验证顺序循环。原DAG本身是否无环与资格策略是否循环分开；不得擅改DAG/降低验收/先放行。给可选最小工程编排处置及各自权限/承诺影响：原owner范围返工是否可解、分阶段局部交接是否需明确批准、哪些必需整体验收必须始终保留。
4. 静态检查R2 tools/run_isolated.py的run_tool与run_exec差异：环境是最小白名单还是仅DROP继承？socket patch是否传到pytest子进程？实际suite fixture是否另有fake backend/网络拒绝？不以harness docstring证明安全。标出未证范围，不推断真实网络已发生，也不洗历史。
5. 不运行任何产品测试、static product import、generator、CLI、服务/HTTP/决策/模型；不创建fixture/OS sink/脚本/缓存；不读凭证/活config/gate/ledger/其他key文件或图片。允许read/find/grep/ls及纯读取bash；如用Python纯AST读取也必须-B/PYTHONDONTWRITEBYTECODE=1、不import产品、不多行python-c、不落任何额外文件。不要修改产品/旧报告/PM状态/原卡/run/output或原历史。
6. 产出足够PM安排下一实际工程动作的具体结论，不重新设计/无限研究，不以done/exit0/acked/当前hash推导全面合规。原12失败/14pyc既有1漂移、失日志/T10外部sink未批准等事实保留；未验证事实写未知。

## 交付格式

唯一证据与最终回复含五节：`## 结论`、`## 证据`、`## 改动清单`、`## 残留与未验证`、`## 上下文来源`。12行根因/owner表、实际依赖链、最小处置候选及权限影响、EOF真实范围和具体未验都必须给出。改动表头“文件”，仅新唯一证据；回读确认文件完整。不得给正式QG/PASS/签收或伪造receipt；终态PM吸收后ack。

## 唯一证据文件

.agenticdoc/mw-dp-consolidation/evidence/implementation/t05-handoff-audit-20261027.md

## 写入允许面

- .agenticdoc/mw-dp-consolidation/evidence/implementation/t05-handoff-audit-20261027.md

## 写入禁止面

唯一证据以外全部，含全部implementation-worktree/现存worker与PM证据/卡片/state/DAG/外部OS目录。研究role不能创建临时工具或copy/shadow共享模块。

## 交付段契约（本角色）

本角色（type: research）的恢复契约段：report.md / output.md 必须按下列标题成节（可直接复制；缺任一段即 settle 判缺失）：

- `## 结论`
- `## 证据`
- `## 残留与未验证`
- `## 上下文来源`

以上为种子，不是探索上界；可自行检索补充上下文
<!-- /mw-dispatch-card: v1 -->

执行原逻辑T05只读交接补核。按卡完整读真实12失败日志和current测试/所采用源码EOF，逐个查实根因及原owner写面，核验证顺序循环而非擅改DAG；核R2 runner子进程网络/env纪律。只写卡列唯一证据，不测试/import产品，不创建OS sink/fixture/脚本，不修改旧历史。给能立即组织下一实际原面修复的具体结论，五节证据并回读。不替代正式S6审计，不声明T05/S2完成。

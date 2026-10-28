# T08 PM independent verification

## 结论

`semantic_handoff_verified=false`。指定套件两次新鲜73 passed，但问题数边界与 replay lookup 非布尔结果没有可靠的失败结果；不适用 basis 的业务拒绝发生在通用传输成功记录之后，仍需按层核验其后继采纳边界。不据 done/acked/单测放行T09/T10，也不把传输成功行直接称为新增有效业务决定。

## 证据

证据根：`.agenticdoc/mw-dp-consolidation/evidence/implementation/t08-pm-handoff-20261026/`；本报告内相对路径均相对此根。

- PM 当前 `decision.py` 2683LF、backend1216LF、指定测试977LF 完整读到 EOF。`check.py` 实跑 rc0，观察 2026-10-26T12:43:45.717597+00:00 ～ 12:43:47.324716+00:00。
- 禁 socket/urlopen 的 bootstrap 指定套件 **73 passed in 0.22s/rc0**；字面 `python -B -m pytest -p no:cacheprovider -q test_dp_consolidation_materials.py` **73 passed in 0.26s/rc0**。`pm-green.stdout/.stderr`、`pm-literal.stdout/.stderr` 是完整输出；字面进程没有全局 socket hook，已全文读测试，其 HTTP 都走 fake seam，关键 test 另毒化 urlopen，不冒称字面进程有全局 hook。
- `pm-probe.stdout/.stderr`、`probe.json`：六个当前接口单变量观测，仅 fake `decision_backends._http_post`；真实socket/urlopen均禁用。POST URL/model/question ids 是缝收到的数据，不是实际网络请求。
- `check.json`/before-after inventory：1883→1883完全相等，复验净副本变化0；对1864frontier只有七授权产品及14现存 `.pyc`。保存十四越面文件字节，不删除、不认独占进程归因。
- 三产品 before/after字节、SHA/EOL与worker一致：decision116092B/2683LF/`89500080e9f59c80e98b757a3a2b547b1db06985edc04a7489d068cb5f80a5e5`；backend48970B/1216LF/`a13a8597bba7abe796022148bd50d02b26fc6a85e1d7d3b1af9f5129f0a3e22b`；test36376B/977LF/`2ab2d758350eb0a3b714512e9a70d81e14c645459f94cc8c850b98a4638454f8`；均CRLF0。
- `pm-full.diff`63954B/SHA256 `6f727690ca2f4be4aba3d07801ff53d648af6d9959108c338b53f7eca90ec454`，worker真实before与PM当前after机械重构，另存各文件diff；不称整diff逐行人工审计。
- 三个对应 live 路径核对：两existing bytes仍worker/S2 before且与副本非samefile；新test live不存在。并非完整live dirty/历史写入审计。

### 复现与责任边界

源码均相对于隔离 `implementation-worktree/packages/multi-workers/decision.py`。

1. **问题数边界未返回失败结果**：合法两问 prepared request 使用合法通用配置 `max_questions=1`，在 line1917 的 `self.decide` 进入 `_validate_input`（line2310的异常消息）直接抛 `DecisionInputError: questions has 2 entries > max_questions=1`；HTTP0、无prepared返回值。与 `request_prepared` doc的不抛异常/超界可见阻塞合同不一致。不得通过提高/放宽现有额度来修复；应保留原通用传输接口及预算拒绝语义，具体修复待授权。
2. **novelty lookup unknown 被强制真假化**：line1843 `bool(replay_check(...))`；callback返回字符串 unknown，被输出 `available=true,replayed=true`，HTTP0且无真实已录决定；返回null，被当miss发一个fake POST并得到 `business_decisions=1`。boolean true control确实零HTTP。typed callback约定bool，但运行输入非法/未知时不应证明已有决定或未执行；这里只测传输 seam，未读/执行实际T10 store/T23 CLI，未证明生产重复请求已发生。
3. **传输记录与业务采纳需严格分层**：合法 choice coding + catalog合法但只适用于其它choice的 basis-other，业务返回正确 `available=false,reason=bad-response,business_decisions=0`；同fixture的 `triage-decisions.jsonl` 却已有 `available=true,reason=null` 及该答案。源头是通用 `decide` 的 `_emit`/`_append_evidence` 先记录传输答案，之后 `request_prepared` line1941 才核选择配对。**此行证明传输回答，不单独证明有效业务决定**；后继若把它用于replay/业务成功则有风险，实际采纳链未验。不可静默改变冻结通用response/reason合同、另造决策账本或要求第二reason请求；先保持这项明确未验证与技术事实。

### 已核本层能力及限制

73tests在实际副本fake seam核同次两问、完整material/preparation、不适用/缺/错basis、分支拒绝、25retired先拒绝、bare Authorization/jev-latest/原retry、box零HTTP及不截核心。此为传输层结果，不是全入口AC/VC或实际QG/签收/效果验收。原worker red61failed3passed与后续green历史未改。

## 残留与未验证

- 原T08有界返工尚未获得本轮具体授权，无新R2或产品写入。T07原处理 `blocked on decision dp4-failure-handling` 继续保留，不重问失败服务、不单断bridge缺陷、不造receipt。
- actual CLI active-before-replay/T23、lifecycle有效业务记录与replay/T10、book/T09、TS消费者/T11+、human/H12生产资格、真实锁/effect、全部53VC/L2/QG/signoff未证；三个semantic handoff均不释放。
- raw transport success≠有效业务成功/执行；fixture ledger为生产writer写入私有测试对象，不是live记录，也不是第二业务ledger。
- 原14pyc越面事件保留。T08自报产生，PM只独立证存在；清理无权限，不因gitignore/worker请求删除。
- 未全回归/npm check（写式formatter需T32保护等价工作区）、build/install/restart/copyback/配置或依赖改动/commit/push。UTF8与minimal env是局部前提，不是locale修复授权。

## 上下文来源

- `.agenticdoc/goal.md`；锁定spec/53AC、approved design D002/D012A、§4.4/4.7、原T08 card合同。
- `tasks/isolated/T08-transport.md`、`implementation-isolated-dag.json` 原T03/T04依赖与三文件限定面。
- 原 `workers/dpc-t08-transport/{task.md,run.json,output.md}`、worker `evidence/implementation/dpc-t08-transport/{report.md,results.json,before-bytes,after-bytes.json}`。
- PM当前三源码EOF、`check.json`、`probe.json`、完整指定套件输出与精确fixture传输证据。

## 改动清单

只新增本key私有 `bootstrap.py` / `check.py` / 当前证据及本报告；T08三产品、peer产品、原worker证据、live源码/框架/配置均未改。7stage36task、目标53AC/VC、权限预算、phase和部署边界不变。

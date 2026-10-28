# T08 R2 — prepared 边界明确失败 + replay 非法结果失败关闭（隔离副本）

## 结论

本层（传输层，隔离副本）R2 已修完并复验通过：`max_questions` 超界不再让 `DecisionInputError` 逃逸，改为 `budget-exhausted` prepared 拒绝（0 HTTP / 0 业务决定 / 额度不上调）；replay 仅接受合法 bool，`null`/未知字符串/数字/容器一律 `entry-unavailable` 失败关闭（0 HTTP / 0 业务决定），`True`/`False` 正例语义不变；25 retired 仍先于 replay/credential/backend 拒绝。指定套件 `73 → 110 passed`（原 73 用例未改未删，纯新增 37 例），`rc=0`。

不构成：全入口 AC/VC、L2、QG、签收、真实并发、生产授权或全链生效。transport 行 `available=true` 与 prepared 业务 `business_decisions=0` 并存只是**分层事实**，不等于已新增有效业务决定；T10 store / T23 CLI 的采纳链本层未执行、未验证。

## 证据

证据根（key-relative）：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t08-transport/rework-r2/`
完整路径：`H:/git/Multi-Workers/.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t08-transport/rework-r2/`
产品根：`.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/`

### 1. 执行前基线（before bytes / SHA / EOL / 既有 diff / 单 writer）

- 三个产品完整读到 EOF（decision.py 2683LF、decision_backends.py 1216LF、测试 977LF）。
- `before-bytes/packages/multi-workers/`：decision.py 116092B / 2683LF / CRLF0 / `89500080e9f59c80e98b757a3a2b547b1db06985edc04a7489d068cb5f80a5e5`；decision_backends.py 48970B / 1216LF / CRLF0 / `a13a8597bba7abe796022148bd50d02b26fc6a85e1d7d3b1af9f5129f0a3e22b`；test_dp_consolidation_materials.py 36376B / 977LF / CRLF0 / `2ab2d758350eb0a3b714512e9a70d81e14c645459f94cc8c850b98a4638454f8`。与 PM `t08-pm-handoff-20261026/report.md` 独立记录的字节/哈希逐项一致（说明本 worker 拿到的是 PM 复验后的同一状态）。
- 既有（本轮之前）副本 vs live 的 diff 原样留存，未覆盖：`diff/decision.py.vs-live.diff`（41932B）、`diff/decision_backends.py.vs-live.diff`（14594B）。live `packages/multi-workers/decision.py`=99249B、`decision_backends.py`=44577B、live 无 `test_dp_consolidation_materials.py`（只读观察，未写入）。
- 单 writer：`_workers.parallel` 三个 R2 worker 同时 running，写面互不交叠，本卡唯一覆盖 decision.py / decision_backends.py / 本测试 —— 见 `single-writer-check.txt`（含三条 write_face 原文）；执行前三个产品 mtime 分别为 12:15:28Z 侧（backend）与 PM 复验后状态，无第二个 writer 触碰的证据仅限本卡写面。
- 与臂相关的只读快照：`face-check.json`（我的三文件 after 哈希 + peer 四文件观测哈希/mtime，明确标注 peer 变更不归本 worker）。

### 2. 运行环境与命令（全部 python -B）

`scripts/run_pytest.ps1 -Label <name> [-Extra ...]`，实际 argv：

```
python -B -m pytest -p no:cacheprovider -q \
  --basetemp <evidence>/fixture/basetemp \
  test_dp_consolidation_materials.py
```

cwd = 隔离副本 `.../implementation-worktree/packages/multi-workers`（测试内 `sys.path` 与导入断言钉在副本，`test_imports_and_http_seam_bind_the_isolated_copy` 仍通过）。
env（`fixture/` 私有最小 UTF-8 集，不继承 provider/worker/项目配置）：`PYTHONDONTWRITEBYTECODE=1`、`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`、`PYTHONNOUSERSITE=1`、`HOME/USERPROFILE=<evidence>/fixture/home`、`TEMP/TMP=<evidence>/fixture/temp`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、`-p no:cacheprovider`；显式删除 `TIMI_API_KEY/TIMI_BASE_URL/OPENAI_API_KEY/ANTHROPIC_API_KEY/PI_WORKER_*/PYTHONPATH/PYTEST_ADDOPTS/PYTEST_PLUGINS`。每次运行落 `runs/<label>/{pytest.stdout,pytest.stderr,rc.json}`。

### 3. 红测（先红，真实业务断言失败，非 import/collection 错误）

- `runs/red-1-new-tests`（rc=1）：9 failed / 53 passed / 48 deselected。
- `runs/red-2-new-tests`（rc=1，修好捕获编码后同结果）：9 failed / 53 passed / 48 deselected。red-1 的 stdout 是 PS 5.1 重定向默认 UTF-16LE（内容同一，留史不覆盖）。

两项红：

1. 超界抛异常：`test_question_ceiling_is_a_prepared_refusal_not_an_exception`（测试 985 行），调用点直接抛出 `decision.DecisionInputError: questions has 2 entries > max_questions=1`，栈定位 `decision.py:2309`（修复前 `_validate_input` 的 `max_questions` 分支），HTTP 0、无 prepared 结果。
2. 非法 replay 被真假化：`test_non_bool_replay_lookup_result_fails_closed`（测试 1055 行，8 个非法值），8 例均在测试 1086 行 `assert result["available"] is False` 处 `assert True is False`。失败形态与 PM `probe.json` 观察一致：`null`/`0`/`[]`/`{}` 被当 miss → `available=true`、1 次 fake POST、`business_decisions=1`；`"unknown"`/`"true"`/`1` 被当 hit → `replayed=true`、`"already has a recorded decision"`。

### 4. 产品差异（只动 `request_prepared`，不动冻结面）

`diff/decision.py.r2.diff`：+62/−5，位置全部在 `DecisionClient.request_prepared` 及其 docstring。

- `decision.py:1862` 新增 `if not isinstance(lookup, bool)` 的失败关闭（`entry-unavailable`，detail 只报类型名 `bool`，不含值）；`decision.py:1851` 改为 `lookup = replay_check(dp, logical_id)`，不再 `bool(...)`；`decision.py:1879` 起保留原 `if lookup:` 命中分支。
- `decision.py:1939` 新增 `ceiling = int(getattr(self.cfg, "max_questions", 0) or 0)`；`len(questions) > ceiling` 时返回 `budget-exhausted` prepared 拒绝，detail 写明“需要 N 问 > max_questions=M，未发请求、未上调上限、未裁剪问题集”。未修改 `DecisionConfig.max_questions` 默认 8、未改 `_validate_input`（generic `decide` 契约保持）。
- `decision.py:1965` 新增 `except DecisionInputError` 兜底：prepared 层把 generic 输入拒绝转成 `input-incomplete` 可见拒绝（`_scrub_detail` 脱敏），保证“本方法不抛”的既有 docstring 承诺。
- 未改：`REASON_CODES` / `_PREPARED_REASONS` 值集、`_RESPONSE_FIELDS`、`_PREPARED_RESULT_FIELDS`、`_EVIDENCE_FIELDS`、evidence 账本、`decision_backends.py`（`diff/decision_backends.py.r2.diff` 0 字节，未写）、retry/budget/box 拒绝、POST `/v1/decisions`、`jev-latest`、bare `Authorization`。

`diff/test_dp_consolidation_materials.py.r2.diff`：+290/−0，**纯追加**，原 73 用例一行未改未删。

### 5. 绿测

- `runs/green-1-new-tests`（rc=0）：62 passed / 48 deselected（新 37 例 + 同 -k 命中的原控制用例）。
- `runs/green-2-full-assigned`（rc=0）：110 passed。
- `runs/green-3-final`（rc=0，最终态再跑一次）：110 passed。
- 断言定位（after 测试文件行号）：超界 `1008`（available=false）、`1009`（reason=budget-exhausted）、`1010`（business_decisions=0）、`1011/1012`（attempts/transport_attempts=0）、`1016`（fake.calls==[]）、`1018`（detail 含 `max_questions=1`）、`1020`（cfg 仍为 1）；replay 非法 `1086`（available=false）、`1087`（replayed=false）、`1088`（entry-unavailable）、`1090/1091`（0 尝试/0 HTTP）、`1094`（fake.calls==[]）、`1095`（detail 含 bool）。
- 量化：原 73 → 110（+37 = 4 个普通用例 + 8 个 replay 参数化 + 25 个 retired 参数化），逐条见 `summary.json` 的 `red_items`/`guard_items`。

### 6. 红线守卫（红测同批次里本来就绿，如实标注为 guard / 控制，不算红→绿）

- `test_question_ceiling_control_still_accepts_a_legal_pair`（测试 1023 行）：`max_questions=2` 下同次两问照旧 1 POST、1 业务决定；并断言 `DecisionConfig().max_questions == 8`——证明修复是“拒绝超界”，不是“放宽额度”。
- `test_bool_replay_lookup_controls_still_prove_hit_and_miss`（1098 行）：`True`→`replayed=true`/0 POST/0 业务；`False`→1 POST/1 业务。
- `test_retired_id_is_refused_before_replay_credential_and_backend`（1143 行，25 个旧 id 全参数化）：replay 回调一次未调用（`seen == []`，1177 行）、`credential_snapshot` 被替换为抛错桩仍不触发、`_http_post` 被替换为 `pytest.fail` 仍不触发，结果 `entry-unavailable`（1178/1180 行）、`replayed=false`（1179）、0 尝试/0 HTTP（1183/1184）、`fake.calls == []`（1185）。顺序根因是 `decision_points.require_active_dp`（`decision_points.py:1356`）先于 replay/credential/backend。
- `test_transport_record_and_business_refusal_stay_separate_layers`（1193 行）：非法 basis 组合下 prepared 业务层 `bad-response`/`business_decisions=0`/`choice=None`，传输层 `attempts=1`/`transport_attempts=1`/1 次 fake POST；同一 fixture 的 `triage-decisions.jsonl` 恰 1 行，`set(row) == set(decision._EVIDENCE_FIELDS)`（1254 行）且不含 `choice/basis_id/basis_text/business_decisions/replayed/prepared_at`。

**分层结论（本轮唯一可下的结论）**：generic evidence 行是传输记录（它结构上无法表达业务选择/依据/业务计数），业务真值只在 prepared 结果上。因此本层能证明的是“传输成功记录与业务拒绝可区分”，不能证明“已新增有效业务裁决”。T10 store / T23 CLI / lifecycle replay 的采纳链本轮未读未跑，属后继验收。

### 7. 越面与卫生

- 未写：decision_backends.py（空 diff 即证据）、decision_validity.py / decision_policy.py / 两个 peer 测试、T03/T04/TS/框架/config/budget/watchdog/权限/live 源码/旧证据/goal/spec。
- 未跑：生成器、其它 suite、`npm check`/build/install/CLI/provider/服务、真实 HTTP（测试只替换 `decision_backends._http_post`；有效路径用例另毒化 `urllib.request.urlopen`）。
- pyc：`__pycache__` 仍 7 项、最新 mtime `2026/10/26 20:16:49`（早于本 worker 首次写入 23:55），本轮未新增/未删除任何 pyc。
- 本卡 `task.md` 的“改动历史”未改写（write_face 不含卡文件），本轮历史即本报告。

## 残留与未验证

- 仅本层：传输/prepared 边界。未证：全八入口 AC/VC（AC-002/004/007/012/014/040/042/043/051 的完整链）、L2、QG、签收、真实并发、真实锁/effect、human/H12 生产资格。
- 采纳链未验：T10 业务 store 写入、T23 CLI active-before-replay、lifecycle 有效业务记录与 replay 复用。本层不新增第二决策账本、不改冻结 generic response/REASON_CODES、不越面修 T10/T23；后继若把 evidence 行直接当有效业务决定使用，风险仍在，需 T10/T23 自己的验收证明。
- replay 契约仍只保证“bool 才算证明”：真实 store 的返回值类型（例如是否可能返回 record 对象而非 bool）本层未定义也未验证；`replay_check` 由调用方提供，本层只拒绝非 bool。
- 真实 endpoint/凭证/模型/provider 行为、`retry-after` 真实时序、生产 capture 未验证（全部 fake seam）。
- 未跑全回归与 `npm run check`（写式 formatter 需 T32 等价保护副本）；未 build/install/restart/copyback/commit/push；未改配置/依赖/预算/watchdog/权限。
- 14 个越面 pyc 原样保留（本轮计数未变，无删除授权）。
- T07 原 `dp4-failure-handling` UNAVAILABLE 阻断记录不因本报告改变；peer 并行写（T06/T07 R2）只观测、不归因。
- 本报告不声明 T08 原任务终态通过；PM 独立复验后再定原 DAG 后继。

## 上下文来源

- 任务卡 `.agenticdoc/mw-dp-consolidation/workers/dpc-t08-transport-r2/task.md`（含 R2 有界覆盖与 AC/VC 摘录，完整读到 EOF）。
- 授权 `.agenticdoc/mw-dp-consolidation/evidence/implementation/s2-r2-approval-20261026.md:1`（用户批准 T06/T07/T08 在原写面内定点返工）。
- PM 复验 `.agenticdoc/mw-dp-consolidation/evidence/implementation/t08-pm-handoff-20261026/report.md:1` 与 `probe.json`（三项缺陷：`max_questions=1` 抛异常、replay 非 bool 被真假化、transport 行 vs 业务拒绝未分层）；未执行任何会覆盖 PM 证据的脚本。
- 项目目标 `.agenticdoc/goal.md:5`、锁定 spec `.agenticdoc/mw-dp-consolidation/spec.md:128`、已批设计 `.agenticdoc/mw-dp-consolidation/design.md:201`、`implementation-isolation.md` / `implementation-isolated-dag.json`。
- 隔离副本当前源码：`.../implementation-worktree/packages/multi-workers/{decision.py,decision_backends.py,decision_points.py,test_dp_consolidation_materials.py}`；原 worker 证据 `evidence/implementation/dpc-t08-transport/{report.md,results.json,before-bytes,after-bytes.json,t08-diff}` 只读留史。
- 并发只读观测：`.agenticdoc/_workers.parallel`（三个 R2 worker 行）与三张卡 frontmatter 的 write_face。

## 改动清单

写面内（本 worker 实际写入，`file: bytes / LF / CRLF / sha256`）：

| 文件 | before | after | 增量 diff |
| --- | --- | --- | --- |
| `packages/multi-workers/decision.py` | 116092B / 2683LF / CRLF0 / `89500080…a0e5` | 119248B / 2740LF / CRLF0 / `ef9c2c68eee18bb93ad716c76c7b146279ac5f111c9f626c68a01d1c35ed691e` | `+62/−5`（`diff/decision.py.r2.diff`） |
| `packages/multi-workers/decision_backends.py` | 48970B / 1216LF / CRLF0 / `a13a8597…a22b` | 同 before（未改） | 0 字节（`diff/decision_backends.py.r2.diff`） |
| `packages/multi-workers/test_dp_consolidation_materials.py` | 36376B / 977LF / CRLF0 / `2ab2d758…54f8` | 47252B / 1267LF / CRLF0 / `b404fc0a9e94b35a198051ed43a8f755d6a61ab5c36b2d43919695cab6b45a1b` | `+290/−0`（纯追加） |

证据目录新增（`.../dpc-t08-transport/rework-r2/`）：`report.md`、`summary.json`、`face-check.json`、`single-writer-check.txt`、`before-bytes/`、`after-bytes/`、`diff/{decision.py.vs-live.diff,decision_backends.py.vs-live.diff,decision.py.r2.diff,decision_backends.py.r2.diff,test_dp_consolidation_materials.py.r2.diff}`、`runs/{baseline-before,red-1-new-tests,red-2-new-tests,green-1-new-tests,green-2-full-assigned,green-3-final}/`、`scripts/run_pytest.ps1`、`fixture/`（私有 home/temp/project/basetemp）。

不变量：7stage36task、53AC/VC、权限/预算/watchdog、phase、部署边界、旧证据与 peer 文件均未改；未派后继、未交接通过、未改 Phase。

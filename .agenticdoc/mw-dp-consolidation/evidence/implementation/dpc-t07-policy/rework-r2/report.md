# T07 R2 有界返工报告（decision_policy / test_dp_consolidation_recovery）

## 结论

原 T07 逻辑任务的定点 R2 在产品写面内完成：只改 `implementation-worktree/packages/multi-workers/decision_policy.py` 与其唯一测试 `test_dp_consolidation_recovery.py`，补上 PM 交接报告列出的七负例与 supplement 中“policy 规则 ref 已撤权、请求换 otherref 绕过”的 fail-closed 缺口。唯一 assigned pytest 文件最终 `35 passed` / rc=0；此前同一文件在真实业务断言上先观测到红（4 failed/31 passed，rc=1），再对同一断言观测到绿。

本层已验证（仅限纯只读 verdict 层）：

- pending-review 现在同时核 policy.scope 与请求 required_scope；缺失或越 scope 不再 allowed=true 空 scope；合法非空范围正例仍 allowed 且 resume_scope 非空，事件/到期仍只触发评估。
- 恢复（halted/breaker）除请求引用外，还核验 `policy.recovery.authority_ref` 的解析、撤权、受控 writer 与 scope；不同引用只有在受控 writer 记录了显式 `supersedes` 关系时才被接受，未强制两 ref 相等，因此 H11 真实新人工授权路径保留。
- halted 硬 guard 缺失/非法、停止 origin 未知、只给自报清除字符串均保持阻塞；人工停止/撤权仍须明确人授权（`recovery:user-stop` + 人授权 kind），受控 config 记录不能替代。
- breaker 的缺失/非布尔 `user_disabled` 不再按 False 处理，未知/伪 origin 保持阻塞，合法 disable 与原熔断事实、预算单位/累计消耗、observation/stop 条件全部保留。
- 冻结 21 键/defaults、预算数值、时限、watchdog、权限、goal/spec、live 对象均未改动；14 个既有 pyc 未删未改。

不声称：生产授权/真实 human 或 H12 资格、L2、真实并发、QG、签收、原 stage 通过、生产 fail-closed 全链已经证明。

## 证据

证据根：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t07-policy/rework-r2/`（以下路径均相对该目录）。所有 Python 命令均 `python -B` + `PYTHONDONTWRITEBYTECODE=1`，私有 minimal UTF-8 env（PATH/SYSTEMROOT/WINDIR + PYTHONUTF8/PYTHONIOENCODING、HOME/USERPROFILE/TEMP/TMP/TMPDIR 与 `DPC_T07_FIXTURE_ROOT` 全部在 rework-r2 内），`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、`-p no:cacheprovider`，无 HTTP/CLI/provider/服务/live 对象；测试导入路径绑定实际副本（negative-control 断言 `decision_policy.__file__` 等于副本路径）。

### before 状态（改动前，两个产品文件均 0 CRLF）

`before.json` / `before-inventory.json` / `before-bytes/`：

| 文件 | bytes | SHA256 | EOL |
|---|---|---|---|
| `decision_policy.py` | 60498 | `f4c44456316b8c60c7934a209de389ef6366aa864f026f9ba5fba40569dde6bb` | 1785 LF / 0 CRLF |
| `test_dp_consolidation_recovery.py` | 53478 | `434412b3ea60e60807ea23b52cdc474e892457a0a1747ecf7cb6bf809380a974` | 1520 LF / 0 CRLF |

与 PM 交接 `t07-pm-handoff-20261026/report.md` 记录的 before 值逐项一致。既有 diff 用 `existing-diff.py` 从 before-bytes 机械重建为 `before-full.diff`：117458 bytes / `120b978c475d86145eaffe26f4bd94b1551ddb0d7c7d24a63e8f61f9c253b62f`，与 PM `pm-full.diff` 逐字节相同（`existing-diff.json.equal_to_pm_diff=true`），说明改动起点就是 PM 复验过的状态。live 同名文件仍不存在（`packages/multi-workers/decision_policy.py`、`..._recovery.py` 均为 False）；worktree inventory 1883 文件。

单 writer 核对：`_workers.parallel` 中同窗口只有 `dpc-t06-validity-r2`、`dpc-t07-policy-r2`、`dpc-t08-transport-r2` 为 running；三者写面不交叠（T06: `decision_validity.py` + `test_dp_consolidation_concurrency.py`；T08: `decision.py` + `decision_backends.py`/`test_dp_consolidation_materials.py`）。本卡只写本报告 frontmatter 列出的两个文件。

### red（真实业务断言失败，非 import/collection）

命令（`run-tests.py`，等价 card 验收命令，最小环境）：`python -B -m pytest -p no:cacheprovider -q test_dp_consolidation_recovery.py`，cwd = 副本 `packages/multi-workers`。

- `red-01`：rc=1，`4 failed, 31 passed`（改动起点，确认缺口存在）。
- `red-02`（pending 用例已把“authority 覆盖、policy 不覆盖”隔离出来）：rc=1，`4 failed, 31 passed`，原始定位：
  - `test_dp_consolidation_recovery.py:1008` `assert outside.allowed is False` → `PendingReviewVerdict(allowed=True, resume_scope=(), reasons=())`
  - `:1260` `assert bypass.allowed is False`（policy rule ref 已撤权 + 换 ref）→ `allowed=True/reasons=()`
  - `:1324` `assert self_reported.allowed is False`（自报清除字符串）→ `allowed=True/reasons=()`
  - `:1661` `assert bypass.allowed is False`（breaker 规则 ref 已撤权 + 换 preauth ref）→ `allowed=True/reasons=()`
  - 日志：`red-01.stdout/.stderr/.rc.json`、`red-02.*`
- `red-03`：rc=1，`1 failed, 34 passed`，`test_dp_consolidation_recovery.py:1409` `assert silent_lift.allowed is False` → 人工 stop 的 lift 越过已撤权的 policy 规则 ref 仍 `allowed=True`（第二轮加固的行为红）。日志：`red-03.*`

### green（同一断言转绿，两次连续绿）

- `green-01`：rc=0，`35 passed in 0.24s`（首轮修复后）。
- `green-02`：rc=0，`35 passed in 0.25s`（第二轮 guard 加固后）。
- `green-final`：rc=0，`35 passed in 0.23s`（终态、after 取样前）。日志：`green-01.*`、`green-02.*`、`green-final.*`。
- 断言级 red→green 对应：`1008`（pending scope/缺 scope）、`1260`（halted 规则 ref/撤权/适用关系）、`1324`（halted guard/origin/人授权 lift）、`1409`（人工 lift 不得绕过已撤权规则 ref）、`1703`/`1731`（breaker 规则 ref、`user_disabled` 未知）。正例控制（合法非空 scope、合法 rule ref、`supersedes` 显式替换、machine-verified guard clearance、合法 disable、H11 新人工 lift）在 red 阶段即为绿，green 阶段仍绿，未靠放宽换取通过。

### 独立负例复演（`negative-control.py` / `negative-control.json`，rc=0）

12 行全部符合预期：`failed_expectations=[]`、`failclosed_bypasses=0`、`legal_controls_granted=4`。

| 复演项 | 结果 | 保留的具体原因 |
|---|---|---|
| pending-control / halted-control / breaker-control | allowed=true，scope 非空 | 合法非空范围、原规则 ref |
| pending-outside-policy | allowed=false，scope=() | `review-scope-uncovered (scope): policy does not grant: key:outside` |
| pending-missing-scope | allowed=false，scope=() | `required-scope-missing (required_scope)` |
| halted-unverified-guard | allowed=false | `guard-clearance-unverified` |
| halted-unknown-origin | allowed=false + 具体问题 | `halt-origin-unknown` |
| halted-unrelated-authority | allowed=false | `recovery-authority-unrelated` |
| halted-revoked-policy-ref-bypass（换 ref） | allowed=false | `authority-revoked (rule-ref)` + `recovery-authority-unrelated` |
| halted-h11-fresh-human-lift（`recovery:user-stop`） | allowed=true，scope 非空 | 未强制 ref 相等，人授权路径保留 |
| breaker-unrelated-preauthorization | allowed=false | `recovery-authority-unrelated` |
| breaker-unknown-disable | allowed=false + 具体问题 | `breaker-disable-unknown` |
| breaker-revoked-policy-ref-bypass（supplement 最小复现） | allowed=false | `authority-revoked (rule-ref)` + `recovery-authority-unrelated` |

PM 的 `probe.py`/`supplement.py`/`check.py` 未执行（避免覆盖原证据）；上述为我方在 rework-r2 内自建、只读、内存 fixture 的复演，`fixture_authority_in_memory_not_production=true`。

### after 状态与增量 diff

`after.json` / `after-inventory.json` / `after-summary.json` / `r2-increment.diff`：

| 文件 | after bytes | after SHA256 | EOL | 增量 |
|---|---|---|---|---|
| `decision_policy.py` | 68600 | `77a9282fb8e7cbcd5ec6ffcea8cf2ded73e16f87a06a7808f6ef6d14e06c259c` | 1989 LF / 0 CRLF | +243 / -39 行 |
| `test_dp_consolidation_recovery.py` | 68653 | `3947d05db48887ac15df9a7ab5cfe58492e1e017497d0c9d603c5dde4cd94761` | 1910 LF / 0 CRLF | +399 / -9 行 |

`r2-increment.diff`：34857 bytes / `358431b0246f653d717714a7d4a7a375ae4ca0d7fe0e7f0cd21f51d4d4b6931e`（18 个 policy hunk、6 个 test hunk；`ast` 解析通过，测试文件 35 个 `test_` 函数、无重复定义）。

inventory（同 worktree，1883 → 1883，无新增/删除文件）：`pyc_before_count=pyc_after_count=14` 且逐字节相同（未删、未新建）；`autopilot/config.py` 等冻结/受保护文件 hash 未变。变更集内另含 4 个 **peer** 产品文件（`decision.py`、`decision_validity.py`、`test_dp_consolidation_concurrency.py`、`test_dp_consolidation_materials.py`），由同窗口授权并行的 T06R2/T08R2 改动，本 worker 未写、未读其内容、不据净 hash 声称独占作者；mtime 亦分层（peer 23:54–23:55 本地，本卡两文件 23:57）。

## 残留与未验证

1. 本层只证明纯 verdict 判据的 fail-closed 边界；调用方真实受控 writer、真实 grant/资格、锁内再核与 T21 的 live 恢复处理仍依原责任，未由本层创造或证明。
2. 生产 fail-closed 全链、L2、真实并发、QG、签收、原 stage 通过均未验证；`[VERIFY]` 计数只是被测纯 verdict 的计数器。
3. `AuthorityRecord.supersedes` 是本模块新增的只读记录字段（由受控 writer 写入）：无 TS/消费者改动，T21 接线时须按原接口责任评估；不属于本卡写面，未改。
4. fixture 是内存/私有目录合成授权，非生产 trust 源；H11/H12 实际人资格与运行切换仍未验证。
5. 未运行任何生成器、其它测试套件、`npm run check`/build/install/reload/restart，未 commit/push；T32 的完整 check 与 TS 依赖等价性仍按原计划由 T32 串行负责。
6. 14 个越面 pyc 保持原字节（PEER 报告归因于 T08 早先未禁 pyc 的 python 调用）；未清理、未绕守卫，精确清理仍需人批准。
7. peer 文件（T06R2/T08R2）的最终内容与 pass 声明未由本 worker 验证；共享镜像的净 hash 不能证明作者独占或历史瞬时无写。
8. live 仓中 `packages/multi-workers/*` 的既有 modified/untracked 属其他 session 的既有工作，本卡未写；本次 live 侧仅只读。

## 上下文来源

- 本卡 `workers/dpc-t07-policy-r2/task.md`（完整读到实际 EOF）、R2 授权 `evidence/implementation/s2-r2-approval-20261026.md`、原 T07 隔离卡/验收命令。
- PM 交接 `evidence/implementation/t07-pm-handoff-20261026/report.md:1`、`probe.json`、`supplement.json`（其 `probe.py`/`supplement.py` 只读参考，未执行）。
- `goal.md`、锁定 `spec.md`、已批 `design.md`、`implementation-isolation.md` / `implementation-isolated-dag.json`、`isolation-baseline-20261026/`。
- 当前副本两产品文件完整读到 EOF（policy 1785 行、test 1520 行）以及只读 `autopilot/config.py`（21 键由既有测试断言，未改）。
- 本次 `rework-r2/` 内全部脚本、日志、rc、hash、inventory、负例输出（见上）。历史 RQ/T03/T04 证据只读，不作本轮源码审计。

## 改动清单

产品（唯一写面，均在 `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/`）：

1. `decision_policy.py`（60498B → 68600B，`f4c44456…dde6bb` → `77a9282f…c259c`，1785 → 1989 LF）
   - `AuthorityRecord.supersedes` + `parse_authority_record` 校验（受控 writer 记录的显式替代/恢复关系）；
   - `HALT_ORIGINS` / `_HUMAN_HALT_ORIGINS` / `_required_scope`（显式非空 scope）；
   - `evaluate_pending_review`：required_scope 必填 + policy.scope 覆盖检查 + 空 resume_scope 判负；
   - `evaluate_halted_recovery`：policy 规则 ref 解析/撤权/scope 与请求引用的适用关系、未知 halt origin、guard 状态必须布尔、清除须 machine-verified、resume_scope 非空；保留 stop 事实/`superseded-authority` 记录/预算单位与累计消耗；
   - `evaluate_breaker_recovery`：`user_disabled` 必须布尔、未知/缺失 origin 判负、policy 规则 preauth ref 与适用关系、resume_scope 非空；保留 tripped-chain/preauthorization 事实与 observation/stop 条件。
2. `test_dp_consolidation_recovery.py`（53478B → 68653B，`434412b3…80a974` → `3947d05d…cd94761`，1520 → 1910 LF）
   - fixture writer 支持 `supersedes`，`_full_grants` 的 `grant-breaker` 以显式 `supersedes=["grant-recovery"]` 记录替代关系；
   - 新增 4 个行为用例：`test_pending_review_requires_policy_and_request_scope`、`test_halted_recovery_verifies_the_policy_rule_authority_and_supersession`、`test_halted_recovery_unknown_guard_and_halt_origin_stay_blocked`、`test_breaker_recovery_verifies_the_policy_rule_authority_and_disable_state`（含合法正例与 H11 新人工 lift）。

证据（`evidence/implementation/dpc-t07-policy/rework-r2/`）：`capture.py`、`existing-diff.py`、`run-tests.py`、`negative-control.py`、`after-summary.py`；`before.json`/`after.json`、`before-bytes/`、`before-full.diff`、`existing-diff.json`、`before-inventory.json`/`after-inventory.json`、`red-01|red-02|red-03.*`、`green-01|green-02|green-final.*`、`negative-control.json`、`r2-increment.diff`、`after-summary.json`；`fixture-<label>/` 为各次运行的私有 fixture。

未改动：live 仓、冻结 config/默认值、预算/授权/时限/watchdog/权限、gate/brake/ledger/签收/goal/spec、其他 key 与四旧 case、T03/T04、peer 模块、mirror/dist/install、14 个既有 pyc。

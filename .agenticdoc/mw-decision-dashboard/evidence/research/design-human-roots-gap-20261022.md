# D-RQ4：人工记录入口与 control/target 根归属（只读负空间核查）

> 卡片 `tasks/D-RQ4-human-roots.md`；spec AC-003/014/002/008；goal `.agenticdoc/goal.md`。
> 只读：未改代码/配置/档案，未发网络请求，未调用真实模型。行号为 2026-10-22 工作树快照，按符号优先。

## 0 结论

1. **AC-014 的人工两腿今天不存在**：`append_override` 只有测试调用（`decide_archive.py:1024`，调用点仅 `test_decide_archive.py`/`test_decide_report.py`）；`mw decide` 子命令只有 run/probe/show/set/ask/book/report/sign/dp（`mw.py:10735` 起），无 `record`、无 `settle`。direct human answer 只有 `mw decide ask`，它写的是证据行（`dp=dp-human-ask`，`mw.py:1195,1670` + `decision.py:1227`），没有 `decision_id`/`questions_version`，不能当 dp 答复。
2. **不能复用 `append_override` 当“人工答复”载体**：override 行的 `_NOT_APPLICABLE` 把 `answer/state_digest/questions_version/available/acted` 全部钉成 null（`decide_archive.py:145-172`），装不下答复、版本或候选；且 `fold` 一见到 override 就置 `human_override=true`（`:916`），`mw decide report` 据此改 `override/override_rate/agree_wilson_lb` 与“分歧样例”（`mw.py:3211-3215,3232,3408`）——记录会变成业务消费，违反本卡禁令。
3. 推荐**独立 lifecycle 旁账 + 记录型 CLI**（案 B），并让该文件对 `fold`/`collect`/`report`/`verdict` **完全不可见**；答案是“append-only 事实”，不是授权、不是消费、不改任何生产档案。
4. 字段上必须删掉 outcome 类字段（`available/acted/outcome/settled_by`），而不是填 false：只要 schema 里存在，下游就有误读可能。记录只带 `decision_id/archive_seq/questions_version/answers/reason/actor/target/supersedes`。
5. **`authority` 不能当来源列**：`decide_for` 在机器升级路径上写 `authority="human"`（`decision_points.py:2454,2499,2536,2609,2641,2671`），`mw decide report` 又把 `authority=="human"` 当升级（`mw.py:3220`）。任何“机器标成人工”的核对必须用新 `actor{kind,id}` 或 `signed_via`，不能读 `authority`。
6. **动态候选无法事后校验**：候选是输入 state（dp3 `local_candidates`，`worker-mode.ts:5463,5712`），档案只存 `state_digest`（`decide_archive.py:260`）；`questions_version` 只 hash 问题形状、明确不含候选（`decision_points.py:244-252,1108-1128`）。唯一可核的是 `book-receipts.jsonl` 的 `file_sha256`（`decision_book.py:1107` 起），且只有 `--book` 路径才写回执。
7. **根归属今天没有单一 resolver**：dp3 用 `process.cwd()`（`worker-mode.ts:4145`），而 dual/partition 下 worker cwd 是 game/partition root（`launcher.py:2780-2795`）；`mw decide run` 直接用 `args.project`（`mw.py:4077`）不做归一；settle 旁账由 TS 直接给绝对 `archive_path`（`pm-orchestrator.ts:1091,1019`）。design §3.1 “同一 control_root” 是目标，不是现状。
8. **写根 fail-open 会造第二套档案**：`_agenticdoc_root` 只拼路径不校验存在（`decide_signoff.py:138-146`），`write_signoff` 会 `mkdir(parents=True)`（`:694`）。从 game/partition root 启动会静默新建 `.agenticdoc/<key>/evidence/review/sign-final.md`。
9. **`decision_id` 不是安全路径段**：`_split_decision_id` 只拒空白（`decide_archive.py:734-750`），`Trigger.resolved_id` 原样透传（`decision_points.py:211-218`），`/`、`..`、`#`、`@` 都合法。RQ1 证据 §8 的 `GET /api/decisions/<decision_id>` 必须改成不透明 id 或 archive `seq`。
10. TS 采纳/消费今天只有 **trace 文本**（dp1 头行 + `[DECISION]` 行），没有结构化 ID 事件；design 的 “TS 采纳与消费 → W” 边没有定义传输方式，与“decision_wire.py 单写者”直接冲突（见 §4、§6）。

## 1 两案：复用 `append_override` vs 独立 lifecycle

| 维度 | 案 A：复用 `append_override`（写 `decisions.jsonl`） | 案 B：独立 lifecycle 旁账（新文件） |
| --- | --- | --- |
| 真实入口 | 无 CLI；仅 `decide_archive.py:1024` 函数，调用点全在测试 | 新 `mw decide record ...`；写者 `decision_wire.py`（新） |
| 目标校验 | `_split_decision_id` 强制 `<dp>:` 前缀；`ref_seq` 可选，给了才校验是同一 decision 的 decide 行（`:1051-1063`）；不给则允许**悬空 override** | 必须命中 `kind=decide` 行且 `ref_seq` 必填；悬空/不存在/多义 → rc≠0 |
| 答复 | **不可能**：`answer` 为 N/A（`:145-172`） | 可带 `answers` + 每问 `candidate_id/candidate_source` |
| questions_version | N/A | 可带；与档案行/当前 registry 三方比对 |
| 候选闭集 | 不可能 | 静态 enum 可核；动态候选只有 book 回执命中时可核，否则 `candidate_source=unverified` |
| 理由 | `_require_text(override_reason)`（`:496`），无长度/脱敏 | 非空 ≤512B，过 `decision._redact`（`decision.py:531`） |
| 来源/actor | 只认 `override_by ∈ human|human:<acct>`（`:287-295,490-495`），机器被拒；无 OS 身份 | `actor{kind:"human",id:"user-explicit"}`，局限写明 |
| 幂等 | 无；重复调用写两行，`override_count` 累加（`fold :921`） | `(kind,decision_id,archive_seq,idempotency_key)` 去重，重复返回既有行 |
| 写失败语义 | fail-loud、锁等待无上限预算（`:637-712`） | 人类记录必须 fail-loud；测试/事件仍可 best-effort 但返回 `record_status` |
| 对业务口径影响 | 改 report 的 override/agreement/分歧样例；`chain_ok` 纳入新行（`decide_signoff.py:248` 对全部行验链） | 0（读侧只被 monitor/history 显式加载） |
| 签收 | `rows_sha256` 只快照 `kind=decide`（`decide_signoff.py:296-315`，快照键 `:101`），override 不改 hash；但档案字节/链变了 | 完全不动签收面（AC-008 最干净） |
| 可覆盖对象 | 仅档案里已有的 decision_id | 可指向 `call-only`，但必须标 `call_ref.status=unverified-no-wire` |

**裁定**：`human-answer` 只能走 B。`human-override` 也走 B（记录“人工改判+理由+被覆盖的模型答复”），`append_override` 保持现状（无生产入口、仅测试），不声称已接线。若产品确实要“反转被签收的决策”，那是一次独立的授权动作，必须另立 DP/入口，不能混进 AC-014 的记录型 CLI。

## 2 最小真实契约（记录型 CLI，非执行/非授权）

```
mw decide record answer   --project DIR --decision-id ID --input-file F [--json]
mw decide record override --project DIR --decision-id ID --ref-seq N --input-file F [--json]
mw decide record event    --project DIR --kind adopted|consumed|steered|signoff \
                          --decision-id ID [--call-id C] [--evidence-ref P#L] [--result ok|failed] [--json]
```
- `record answer|override` 固定 `actor=human`；`record event` 固定 `actor=system`。actor **由入口决定，不做 flag**（flag 只是诚实标注，不是安全边界）。
- `--project` 必填且过 §5 的 `resolve_control_root(..., require_control=True)`；不接受 JSON 里的 project/root/archive 路径。
- 输入闭集（`--input-file` ≤64KiB，UTF-8，未知键拒绝）：`schema_version=1, decision_id, call_id?, questions_version, answers?[{qid:{value, candidate_id?, candidate_source?}}], reason, supersedes_event_id?, responded_at?`。
- 校验顺序（全在写锁**之前**）：① dp 由 `decision_id` 前缀得出并 `get_decision_point`（`decision_points.py:876`）；② 档案中 `kind=decide` 且 `decision_id` 命中，取其 `seq/questions_version/answer`；③ `--ref-seq` 必须等于该 seq（override 必填）；④ 输入 `questions_version` 必须等于档案行；与当前 registry 不一致 → rc=5，`--allow-stale-questions` 才继续并写 `questions_version_matches=false`；⑤ answers 逐问按 registry `type` 校验（choice/noul/score/box），`dynamic_choices` 无 book 回执命中时只接受 `candidate_source=unverified`，拒绝“已验证候选”的措辞；⑥ reason 非空且过 `decision._redact`，`redacted=true` 时原值不落盘；⑦ 重算 `idempotency_key`，命中既有行返回 `duplicate=true`（rc=0，不追加）。
- 写：`decision_wire.append_lifecycle(control_root, row)`，`O_CREAT|O_EXCL` 锁 + `O_APPEND` 单行 + short-write 检查（复用 `mw_common.acquire_lock:2388` 协议）；失败 rc=4 且 stderr 明确“未落盘”，绝不返回成功。`project_id=sha256(normcase(realpath(control_root)))[:16]` 写入行，跨根复制出的行被读侧标 `foreign-project`。
- 禁止（用真实入口 spy 证明）：不调用 `DecisionClient.decide`/`_http_post`/`decide_for`/executor/`append_decide`/`append_override`/`append_authority_change`/`write_signoff`；不写 `.mw/decide-points.json`、`decisions.jsonl`、`sign-final.md`；生产调用计数 0。
- `decide_for` 里加一个“人工已答复”分支是**禁止**项：那会把记录当授权。

## 3 字段 writer / reader（今天的真实归属）

| 字段 | 今天的唯一 writer | 今天的 reader | 缺口 |
| --- | --- | --- | --- |
| `decision_id` | `decide_for`→`_archive_decision`（`decision_points.py:2067,2075`） | `fold`、report、sign、TS 头行 | 人工记录无 writer |
| `questions_version` | `append_decide`（`decide_archive.py:948` 参数） | `decide_signoff`（引擎校验）、人读 | override 行 N/A；无人工记录 |
| `answer`（模型） | `append_decide`（模型答复） | `fold.base.answer`、report 分歧样例 | 人工答复无处落 |
| `call_id` | **不存在**（RQ2 设计稿） | 无 | record 的 `call_id` 只能标 unverified |
| `state_digest` | `append_decide`（只摘要） | 一致性比对 | 不能反推 state/候选 |
| `book_path/file_sha256` | `append_book_receipt`（`decision_book.py:1107`） | 人读 | 只有 `--book` 路径；TS 自动 dp1/2/3 不写 |
| `override_by/override_reason` | 无生产 writer | `fold`→`human_override`→report | 只测试 |
| `authority` | `_archive_decision`（机器路径也写 `human`） | report `escalated` | **不能当来源** |
| `signed_via` | `decide_signoff.render`（`:568-569`）由 `mw.py:3912` 调用；写入闸门 `mw.py:3643-3671` | `parse_signoff` | 人工/机器签收唯一真凭据 |

## 4 TS 生产 adopted/consumed/responded seam（dp1/2/3/25）

| DP | 现有真实载体 | 位置 | 能声称什么 | 缺口 |
| --- | --- | --- | --- | --- |
| dp1 采纳 | `task.md` 的 `decision:` 头 | `ui-bridge.ts:3049 mergeDecisionHeader`；判定 `:290 dispatchDecisionOf`（需 `available && mode=auto && type 相等 && id 非空`） | “派发采用了该类型”，不证明执行 | 无事件；另一个判定 `actedDecisionOf`（`:673`）用 `result.acted`，两套采纳口径 |
| dp1 消费 | settle 行（终端） | `pm-orchestrator.ts:2778→1059→1004`（`APPEND_SETTLE_PROGRAM:986`，归档路径 `:1091` 由 TS 给定） | 任务终态→outcome | `settled_by` 只有 `pm-auto`；TS 直接传绝对 archive_path，绕过 Python 根解析 |
| dp2 采纳 | `steer-dp2.md` + trace | `pm-orchestrator.ts:2697`（写 steer 成功后）→ `:2476 appendDp2ActedTrace`（`:2480`） | “收窄已执行” | 仅 trace 文本；无结构化事件 |
| dp2 消费 | steer 标记 + trace | `worker-mode.ts:3298`（`consumeDp2NarrowSteer`，id 由 `:3296` 正则从文件抠出） | 注入 follow-up + marker | 文本解析；失败分支 `:3264-3292` 也是 trace |
| dp3 采纳/消费 | trace + follow-up | `worker-mode.ts:4222`（`acted=1`）→ `:4231 sendUserMessage` | “steer 已入队” | 不能声称 agent 已读；3c 本地决策无档案行（`:5697`），id 是本地构造 |
| dp25 签收 | `sign-final.md` + authority-change | `mw.py:3888 verdict`→`_decide_sign_write:3643`（`signed_via` 落文件）→`:3971 append_authority_change(by=signoff:<c>)` | 人工/机器由 `signed_via∈{cli,tui}` vs `{auto-decide,auto-llm}` 判 | 无 lifecycle 事件；`by` 对所有人都是 `signoff:<conclusion>` |

**最小 seam（建议）**：在上述 6 个真实成功点各加一次 `mw decide record event --project <controlRoot> --kind ...`（TS `spawnSync`，`windowsHide`，20s，失败写 trace 但绝不改主流程结果）。理由：它是唯一不破坏“Python 单写者 + 文件锁”的走法；TS 直接 append 会重演 `recordDispatchAlarm`（`pm-orchestrator.ts:666-687`）的无锁无幂等缺陷。根：PM 用 `path.dirname(agenticdocRoot)`（`:2609` 已是 control root），worker 用 `controlRootFromTaskPath(taskPath)`（`shared/paths.ts:47`，`decision-tool.ts:787` 已用），**禁止 `process.cwd()`**。
**不能声称**：dp2 “consumed”只等于注入+marker；dp3 只等于 steer 入队；dp1 的 `[DECISION] state=...` 只是输入路径审计（`ui-bridge.ts:619`），不是采纳。

## 5 control / target / partition / project 根归属

**现有链（事实）**
- `mw_common.load_target_config(control_root)`（`:5085`）→ `{control_root, game_root, partition_root, ...}`；`workspace_root(config)`（`:5382`）= partition→partition_root，dual→game_root，否则 control_root。
- `target.yml` 固定在 `<control>/.agenticdoc/target.yml`（`:4713`），即“哪个目录是 control”有磁盘证据。
- 路径归一只有 `decide_signoff._agenticdoc_root`（`:138-146`，识别 project/.agenticdoc/key 三态，**不校验存在**）和 TS `controlRootFromTaskPath`（`paths.ts:47`）。
- 写根四套：Python `args.project`（`mw.py:4077`）、Python `key_dir.parent.parent`（`:3815`）、TS `dirname(agenticdocRoot)`（`pm-orchestrator.ts:2609`、`ui-bridge.ts:3082`）、TS 显式 `archive_path`（`:1091`）。dp3 是唯一用 `process.cwd()` 的写侧（`worker-mode.ts:4145`）。

**最小签名（建议，Python 唯一实现，TS 只做镜像调用）**
```python
def resolve_control_root(project_dir, *, require_control: bool) -> tuple[Path, str]:
    # source ∈ {"project","agenticdoc","key","target-root","refused"}
```
规则：① `p.name==".agenticdoc"` → `p.parent`；② `p.parent.name==".agenticdoc"` → `p.parent.parent`；③ `(p/".agenticdoc").is_dir()` → `p`；④ 否则向上≤2 层找 `.agenticdoc/target.yml`，`load_target_config(found.parent)` 且 `p==workspace_root(cfg)` 或在其下 → control=found.parent；⑤ `require_control=True` 时其余一律 `E-ROOT-NOT-CONTROL`（不新建、不猜）。`TargetConfigError` 直接冒泡（fail-closed），不回退 single。
- monitor：启动时解析一次，`project_root_key=normcase(realpath(control_root))` 写状态文件（RQ1 §4.6 方向正确，但要加 ④/⑤）；HTTP **永不**接受 project/book/路径参数，只接受不透明 id；历史详情建议用档案 `seq` 而非 `decision_id`（理由见 §0.9）。
- TS 子进程：`decideMw(projectDir, args)` 把 `--project` 追加在末尾（`mw-runner.ts:522,575`），因此调用方必须传 control root；dp3 必须改传 `controlRootFromTaskPath(taskPath)`；settle 建议改为传 `--project/--key` 由 Python 推导 archive（现传绝对 `archive_path` 等于信任 TS 根）。
- 禁止：HTTP 路径、JSON 字段、env（`MW_PARTITION_ROOT` 等）参与写根推导；只能在 CLI 显式 `--project` 上做 ①-⑤。

## 6 design.md 不可行 / 语义过度承诺

1. §3.1 “所有生产历史按同一 control_root/project 身份读写” → 现状四套写根 + dp3 cwd；§5 VC-018 的 `archive_roots=1` 今天必失败（dual/partition 下 dp3 静默 bypass 或落第二棵树）。
2. §4.3 “校验…动态候选” → 动态候选不持久化，只有 book 回执 hash 命中才可核；否则只能标 unverified。不能承诺“候选闭集校验通过”。
3. §4.3 “校验…调用引用” → `call_id` 尚未存在（RQ2 设计稿）。record CLI 必须要么拒绝 `--call-id`，要么写 `call_ref.status=unverified-no-wire`。
4. §2/§5.4 “TS 采纳与消费 → W（decision_wire 单写者）” → 未定义 TS 如何写；若 TS 直写就破单写者，若 spawn 就要接受每事件一个 Python 进程（延迟/失败面）。
5. §4.3 “只追加 lifecycle 人工事件…不冒充已消费” 与 §4.4 把 `human-answer` 放进同一 lifecycle 流 → 需明确 `fold/collect/report/verdict` **不读**该文件，否则 AC-003/014 的“记录”会变成业务事实。
6. §4.4 `authority-change/signoff` 的 actor 推导 → 只能用 `signed_via`；`by` 恒为 `signoff:<conclusion>`（`mw.py:3971`），`authority` 字段机器路径也写 human。
7. §4.4 `decision-end` 的 `archive=created|replayed|skipped|failed` → 现有信号只有 `(archived, replayed)`（`decision_points.py:2137`）；模块缺失静默 `(False,False)`，其余 fail-loud。四态需要新增返回值，不是“透传”。
8. §4.2 `/api/history/<opaque-id>` 与 RQ1 §8 `/api/decisions/<decision_id>` 冲突；后者对 `decision_id` 字符集不安全（§0.9）。
9. §4.1 `monitor status|stop` 子命令与 RQ1 §4.1 的 `--status/--stop` flag 冲突；VC-006/007 前必须二选一。
10. §9 “输出 secret 扫描同一安全策略” → 现有只有 env 值/Bearer/`sk-` 的 `_redact`（`decision.py:514-545`），不是通用 secret 检测；对“自由理由里出现未在 env 的凭证”只能标 `unverified`，不能承诺 0 泄漏（AC-005 的测试必须用配置内已知 secret，spec 已如此写）。
11. §4.3 “CLI 不把 ask 当 human answer；ask 记录 actor=human” → 现 `ask` 只写证据行且与 triage 共用 `triage-decisions.jsonl`（`decision.py:109`，`dp-human-ask` 是唯一区分），没有 decision_id，需要新写者而非“记录 actor”。

## 7 验证契约（真实入口，不使用 fixture 冒充）

- VC-R4-1：`mw decide record answer --project <isolated>` 对一条真实 `decide_for` 产生的档案行执行 → lifecycle 1 行；`decisions.jsonl` 字节 sha、`sign-final.md` 字节、`rows_sha256`、`chain_ok` 全不变；`append_override`/`_http_post`/executor spy=0。
- VC-R4-2：未知 decision_id / 错 `ref_seq` / 悬空 override / 错 `questions_version` / 未知键 / 超 512B reason → 各 rc≠0，lifecycle 行数不变（锁前拒绝）。
- VC-R4-3：重复提交同一 body → 第二次 `duplicate=true` 且不追加；不同 reason 追加新行。
- VC-R4-4：动态候选：book 回执命中 → `candidate_source=book`；无回执 → 只能 `unverified`，且输出不含“已验证”字样。
- VC-R4-5：`mw decide report --json` 与 `decide_signoff.collect` 在 lifecycle 写入前后完全相等（证明记录不被消费）。
- VC-R4-6：dp1 真实 dispatch → `task.md decision:` 头 + 1 条 `record event kind=adopted` 的 decision_id 与档案行一致；dp2 真实 steer → `acted` + 1 条 `consumed`；dp3 真实 follow-up → 只 1 条 `steered`；dp25 `mw decide sign --conclusion continue` → `signoff` 事件 `signed_via=cli`，`--auto` → `auto-*`。
- VC-R4-7：`mw decide record event` 传 `actor=human` 类参数 → 拒绝（入口固定 actor）。
- VC-R4-8（根）：single 根下 `--project` 传 project/.agenticdoc/key 三态 → 同一 control root、同一 archive；dual/partition fixture 下传 game/partition root → 解析到 control 或 `E-ROOT-NOT-CONTROL`，绝不在 game/partition 下新建 `.agenticdoc`；monitor 从 partition root 启动 → 拒绝或复用 control 实例；HTTP 提交带 project/path 字段 → 400 且 0 写。
- Layer/证据：R4-1..7 L1/L2 本地真实 HTTP；R4-8 真实 `load_target_config` + 临时双根 fixture；全部零外网。

## 8 未覆盖与残留

- 未实测 Windows 上 lifecycle 锁 + `O_APPEND` 并发（与 RQ2 §10 同一残留）；未实测 monitor 与 CLI 同时写时的锁竞争。
- 未确认产品是否需要 `human-answer` 覆盖**未归档**调用（call-only）；本卡按“必须有 decide 行”设计，未验证 `call-only` 的合法业务场景。
- 未验证 `--allow-stale-questions` 的产品必要性；选项本身是诚实降级，不是校验通过。
- 未覆盖 dp25 `narrow/revoke` 与 `allow_empty` 的事件字段差异（只按 `signed_via`+`conclusion` 设计）。
- 未覆盖 `mw decide dp apply`（人写签收文件再应用）是否也应发 `signoff` 事件；它今天走 `append_authority_change(by=human|human:p0-confirm)`（`mw.py:1836,2100`），与 `mw decide sign` 不同入口，需 PM 决定是否统一。
- 本卡未运行任何测试、未起服务、未改代码；所有 path:line 均为只读快照。

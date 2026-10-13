# T-12 P1/P2 修复（篡改比对红 + extras 判据统一 + 边界/通道/种子/unlisted）

- Key: mw-dispatch-card-gate｜Wave: 7｜依赖: T-10（已终态）｜type: coding

## 上下文
对抗 QG（`workers/mwd-t11b-adversarial-qg/report.md`，结论 **FAIL**）给出 2 项一票否决（F-01/F-02）与 4 条 P2（F-03/F-04/F-05/F-06）。PM 已独立复核其中的 F-01 与 F-09，确认成立。**P1 未关闭前不得 cutover**（否则过拦与漏拦同时上生产线）。

关键事实（PM 已复核）：
- F-01：`packages/multi-workers/autopilot/card_audit.py` 中 `card_sha256` 命中数 = **0** ⇒ 记录了卡摘要却无读取者；`digests` 只算当前摘要，**不与派发时记录值比对**；而 `packages/multi-workers/test_mwds_t27_card_audit.py:202-227` 把「篡改后 digests 变化」当成通过条件，**固化了被弱化的口径**。
- F-02：`typeExtrasMissing` 在 `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` 内仅出现 1 次 ⇒ G-1 的卡校验只跑 `readEnvelope`（仅三段）；G-3 服务层查的是**派生 task.md**，而 `extractCardSections` 只抽三段、**丢弃 extras 独立段正文** ⇒ 合规卡会被 G-3 误拒（P-03 过拦），同时 description 文字可满足卡未声明的 extras（欠拦）。

## 要求（逐条可验收）

1. **F-01 篡改⇒红（一票否决）**：`card_audit.audit()` 读取每个 `workers/*/task.md` 头部区的 `card_sha256:`，与 `card_digest(<card>)` 比对；不相等 ⇒ 新增 `tampered_cards`（含 task_key 与两个摘要）并**默认判红**（CLI 非零退出，**不依赖 `--strict`**）。
   - 修正被固化的弱化测试：篡改用例的通过条件必须是「红」，不得再断言"篡改后 digests 与之相等"即可通过。
   - 新增真用例：等长篡改 ⇒ 非零退出 ⇒ 恢复原卡 ⇒ 零退出。
2. **F-02 extras 判据统一（一票否决）**：使 G-1 与 G-3 对 extras 是**同一判据、同一对象**：
   - G-1：在 `pm/ui-bridge.ts` 的卡校验路径（`readDispatchCard` 一带）对**卡文本**调用 `typeExtrasMissing`，缺失 ⇒ 拒绝并指名缺项（T-07 已收宽词汇表，`codex` 误拒理由不再成立）；
   - G-2：让 `extractCardSections` 把卡的 **extras 段正文一并注入** 派发 `task.md`，使 G-3 对派生 task.md 的检查**可通过**；
   - 修正 `dispatch_worker` 的参数描述与拒绝文案，使其与代码行为完全一致（现状承诺了工具层查 extras）。
   - 反例证据（必须进报告）：① 含 4 个 extras 独立段的合规 `coding` 卡 ⇒ G-1 放行 **且** 派生 task.md 通过 `launcher._envelope_refusal`（**不得再被拒**）；② 缺 extras 的 `coding` 卡 ⇒ G-1 拒绝并指名。
3. **F-03 边界不可伪造**：`ENVELOPE_ENFORCE_SINCE` 的判定增加交叉校验 —— 若 `task.md` 的 mtime 晚于行内 `dispatched_at`，或 task.md 已含 canonical 段标题，则**无条件判**（不豁免）；同时**删除或实现** `created` 死码分支（二者择一，在报告中说明）。
4. **F-04 bash 通道接入改动历史**：shell 命令中的写目标（复用既有 `extractBashWriteCandidates` 或等价机制）也记为写入事件（`[WRITE_FILE]` 或新 `[BASH_WRITE]`）；「零事件 + 报告有声明」判 **unjudgeable** 并在读回体标注，**不得直接绿**（诚实声明不得被误判为假红，全 bash 写入不得绕过）。
5. **F-05 最小种子判据**：卡须含 `goal.md` 引用 **且** ≥1 处 `路径:行号` 形式引用；缺失 ⇒ G-1 拒绝并指名缺项；据此更新字节金样本（当前金样本卡无任何种子项，属欠判据）。
6. **F-06 `unlisted_dispatches` 引入边界**：`card_audit` 使用与 `launcher.py` **同源**的边界常量（`ENVELOPE_ENFORCE_SINCE`）；边界之后的 unlisted 单列为 `unlisted_after_boundary` 并**默认判红**；边界之前保持不判（历史兼容）。T-10 的合法无卡合成派发按边界规则处理，不得使其把 `--strict` 永久变成不可用。

## 交付格式
- 写入允许面：
  - Python：`packages/multi-workers/autopilot/card_audit.py`、`packages/multi-workers/launcher.py`、`packages/multi-workers/test_mwds_t27_card_audit.py`、`packages/multi-workers/test_mwds_t27_service_envelope.py`、`packages/multi-workers/test_mwds_t29_producer_signal.py`
  - TS：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`、`shared/dispatch-card.ts`、`worker/worker-mode.ts`（F-04 事件源）、`test/suite/dispatch-card-envelope.test.ts`、`test/suite/dispatch-card-injection.test.ts`、`test/suite/change-ledger.test.ts`、`test/suite/dispatch-recovery-terminal.test.ts`
- 写入禁止面：`packages/multi-workers/mw.py`、`mw_common.py`（只读）、`autopilot/conductor.py`（只读）、其他 key 目录、`.agenticdoc/**`（除本 worker 目录 taskDir 外）。
- 交付物：上述改动 + 测试；`report.md` 含结论/证据（原始命令与输出）/改动清单/残留与未验证/上下文来源清单。
- 回收判据：
  - TS（在 `packages/coding-agent` 下）：`node ../../node_modules/vitest/dist/cli.js --run test/suite/dispatch-card-envelope.test.ts test/suite/dispatch-card-injection.test.ts test/suite/change-ledger.test.ts test/suite/dispatch-recovery-terminal.test.ts test/suite/output-recovery-contract.test.ts` 全绿；
  - Python：`python -X utf8 -m pytest packages/multi-workers/test_mwds_t27_card_audit.py packages/multi-workers/test_mwds_t27_service_envelope.py packages/multi-workers/test_mwds_t29_producer_signal.py packages/multi-workers/test_launcher.py -q` 全绿；全量 `python -X utf8 -m pytest packages/multi-workers -q` 失败数 == **2**（既有基线，不得新增）；
  - 报告须含 F-01 的「等长篡改 ⇒ 红 ⇒ 恢复 ⇒ 绿」与 F-02 的「合规卡不被 G-3 误拒 + 缺 extras 被 G-1 拒」两组**原始输出**；
  - 改动清单 ⊆ `trace.log` 的写入事件（cutover 后生效；本卡所属 worker 运行期仍为旧 bundle，属已知项）。

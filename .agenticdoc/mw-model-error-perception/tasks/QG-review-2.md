# QG-2: mw-model-error-perception 终局 review（含 QG 处置核验 + 新增 mini-key 审计）

type: review

## 上下文

- 项目 goal：`.agenticdoc/goal.md`（GC-1/GC-2/GC-3）。
- 主 key `mw-model-error-perception` 已 DONE；前次 QG（`evidence/qg-review-20261015.md`，⚠️ 有条件通过 11✅/6⚠️/0❌）之后 PM 做了处置与一个新 mini-key，本次为终局复审。
- 处置落盘（待你核验）：`spec.md`（AC-002 回填 run=1 语义 + 顶部修订索引）、`design.md`（顶部修订索引指向 §2 D3 修订记录）、`key-decision.md`（裁决 4 = autopilot-protocol 适配授权补记、裁决 5 = QG 处置记录）、`pm-state.md` Evidence Ledger（门禁 PASS + QG 结论两条）。
- 新增 mini-key `.agenticdoc/mw-review-schema-lookaround/mini-spec.md`：worker_file schema 的 `file.pattern` 含 ECMA lookaround（write-surface.ts 旧 `WORKER_FILE_EVIDENCE_SEG`）导致 Azure 严格校验部署（gpt-6.1-sol）首调 502；已改写为无 lookaround 等价正则（段内强制 ≥1 非点字符）。代码锚点：`packages/coding-agent/src/extensions/agent-team-loop/shared/write-surface.ts:64-70`（新常量+注释）、`packages/coding-agent/test/extensions/agent-team-loop-worker-file-tool.test.ts`（LOOKAROUND_RE 防回归断言 + snapshot() 白名单过滤适配）、`packages/coding-agent/CHANGELOG.md` [Unreleased] Fixed 条目。dist 已由用户 `mw build --install --allow-dirty` 重建（可读 `packages/coding-agent/dist/extensions/agent-team-loop/shared/write-surface.js` 核对 schema 无 lookaround；注意 L62 注释与 L120 运行时 drive-relative 判断的 lookaround 属预期无害）。

## 审计目标（QG 问题清单，三态判定 ✅/⚠️/❌）

1. **前次 QG 六项 ⚠️ 处置核验**：逐项对照处置声明与磁盘实况（AC-002 新文本、两处修订索引、key-decision 裁决 4/5、pm-state 证据条目）；未兑现即 ❌。
2. **mini-key 独立复核**：自行构造路径用例矩阵（合法：basename 三型/evidence 多段/.agenticdoc 前缀/点前缀非全点段；非法：`.`/`..`/全点段/空段/大写前缀 `Evidence` 等）对**新旧两个正则**做读码推演比对，验证 mini-spec 的等价性声明；核对防回归断言确实钉死 schema 无 lookaround；核对 CHANGELOG 条目与实现相符。
3. **snapshot() 适配授权**：worker-file-tool 测试的 `snapshot()` 白名单过滤是否保持测试原意、是否最小、是否已在 mini-spec/key-decision 留痕。
4. **全 key 终态证据链复扫**：按修订后 AC-001~010 重走证据链（引用测试用例名 + 实现锚点 + `evidence/quality-gate-report-20261015.md` 门禁输出），三态判定。
5. **dist 生效确认**：读 dist write-surface.js，确认 tool schema 的 pattern 无 lookaround（区分注释/运行时正则的预期残留）。
6. **写面纪律**：mini-key 与 PM 直执的全部改动是否均在声明的写入允许面内（git status 中本会话未提交文件与各卡面/mini-spec 对照）。

## 要求

- 报告写入 `.agenticdoc/mw-model-error-perception/evidence/qg-review-20261015-final.md`（唯一证据文件，勿覆盖前次 qg-review-20261015.md）。
- 每个判定给证据引用（文件:行 / 测试用例名）；结论三态：✅ 通过 / ⚠️ 有条件通过（列欠债）/ ❌ 未通过（列修复项）。
- 只读审计：除该报告文件外零写入。

## 未覆盖面声明（审计边界）

- 不重跑测试/门禁命令（review 角色无 bash；门禁执行证据引用 T-07 报告与 pm-state Evidence Ledger）。
- 不审计其他并行 key（csg 等）的未提交改动；mwds-t02 语料回放的既有失败（本会话新派发卡片致命中集漂移，A/B 已证与 write-surface 改动无关）按已知漂移豁免，不要求修复。
- 不覆盖 `/mw restart` 后 serve 侧 Python 行为的运行时验证（launcher 重试链的进程级生效）。
- 你本人即运行在新 dist 上——若本次派发仍出现 `invalid_json_schema: regex lookaround` 502，这本身是关键审计发现，请写入报告（说明 dist/全局 bundle 路径未刷新）。

## 交付格式

- `evidence/qg-review-20261015-final.md`：判定表（Q-ID/描述/状态/证据引用/备注）+ mini-key 独立复核的用例矩阵摘录 + 汇总 + 三态结论 + 欠债/修复清单。
- 交付说明：结论一句话 + 三态计数。

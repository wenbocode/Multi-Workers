# FIX-J：dp3 3a 消费侧改为「本地候选 + 模型选择 + 本地取引用」

- type: coding
- owner key: mw-decision-substitution
- 前置：用户 2026-10-20 裁定 `3a 要改成 choice/nuol`。FIX-I 已把 dp3 注册表问题集改成
  `answer_kind`(choice) + `answerable`(noul) + `candidate`(choice，动态候选)。本卡改 **TS 消费侧**：
  候选由本地生成，模型只选一条并给可答性，**引用与文本一律来自本地文件**（模型不造句）。

## 冻结契约（与 FIX-I 逐字一致，不得自行改动）

- dp3 `questions_version` 新值：**`q-fcbd3847`**（`DP3_QUESTIONS_VERSION` 必须改成这个字符串）。
- state 新增必填键 `local_candidates`：`[{"id":"c1","label":"..."}, ...]`，1..5 项，`id` 从 `c1`
  连续编号（`^c[1-9]$`），`label` 非空、≤ 80 字符、不含换行。
- 子进程返回的 `answers` 形状：`answer_kind {value:"fact"|"intent"|"reuse", confidence?}`、
  `answerable {value:<0..1 概率>}`、`candidate {value:"cN"}`。

## 本卡要做的（`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`）

1. `DP3_QUESTIONS_VERSION` → `"q-fcbd3847"`。
2. 新增 `buildDp3Candidates(input, question): {id, label, path}[]`（本地、确定性、无网络）：
   - 词元：`question` 按非字母数字切分，长度 ≥ 3 的 ASCII 词 + 长度 ≥ 2 的 CJK 连续串，小写化，
     去掉停用词（`the,and,for,which,where,should,what,how,this,that,file,write,please`）。
   - 固定候选（恒为 `c1`）：research 任务 → `evidence/research/<taskKey>-<YYYYMMDD>.md`；
     coding/review → `evidence/runs/<taskKey>-<YYYYMMDD>.md`。日期用本地当天。
   - 检索候选：在 `evidence`、`docs`、`tasks`、`.agenticdoc/<key>` 四个根下（每根 ≤ 300 个文件、
     深度 ≤ 3、只读文件名不读内容）取相对路径命中词元的文件，按（命中词元数降序，路径升序）排序，
     补到总数 ≤ 5。
   - `label` = 相对路径（超过 80 字符从中间截断加 `...`）。
3. `buildDp3State` 里带 `local_candidates: candidates.map(({id,label}) => ({id,label}))`。
4. 答案消费（3a 分支）改为：
   - `answerable` 概率 `< DP3_ANSWERABLE_MIN`（常量 **0.5**）→ `escalate("unavailable","3a",
     \`model reports unanswerable (<p>)\`)`；
   - `candidate` 的值必须是已发送候选 id 之一，否则 → `escalate("unavailable","3a","unknown candidate id <v>")`；
   - 用该 id 取本地路径：文件必须存在且可读 → 在该文件里按同一组词元（大小写不敏感）找**首个命中行**；
     没有命中行则用首个非空行；文件不可读/全空 → `escalate("unavailable","3a","candidate file unreadable <path>")`；
   - 合成 `answer` = `<该行 trim 后 ≤200 字符> (<相对路径>:<行号>)`，`source` = 正则捕获到的
     `<路径>:<行号>`（复用 `DP3_CITATION_RE`）；**禁止**把模型返回的任何自由文本塞进 `answer`。
   - `answer_kind === "reuse"` 的既有 3c 分支保持不变；`intent` 仍按既有方式 escalate。
   - `confidence` 取 `kind.confidence ?? answerable.confidence ?? null`，`confidence_source === "api"`
     的门控逻辑不变。
5. 每条候选/选中结果写进既有 trace（`[DECIDE]` 行已是既有格式，不改格式；明细放 `detail`）。

## 必做用例（`packages/coding-agent/test/suite/dp3-answer.test.ts`）

用 `runner` 测试缝隙（假 `mw decide run` 输出）而不联网：

1. `fact` + `candidate=c2` + `answerable=0.8` → `kind:"answer"`，`answer` 以本地行文本开头且以
   `(<path>:<line>)` 结尾，`source` 命中 `DP3_CITATION_RE`，且 `answer` 里**不含**任何 runner 返回的自由文本。
2. `answerable=0.3` → `escalate`，`detail` 含 `unanswerable`。
3. `candidate=c9`（未发送）→ `escalate`，`detail` 含 `unknown candidate id`。
4. 候选文件不存在（构造临时目录）→ `escalate`，`detail` 含 `candidate file unreadable`。
5. `buildDp3State` 发出的请求体含 `local_candidates` 且 1..5 项、id 从 `c1` 连续；`questions_version`
   等于 `q-fcbd3847`（快照断言 `DP3_QUESTIONS_VERSION`）。
6. 回归：`intent` 仍 escalate 到 3b；`reuse` 3c 分支行为不变；`mode` 缺失仍 escalate（FIX-E）。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
- `packages/coding-agent/test/suite/dp3-answer.test.ts`

## 写入禁止面

- `packages/multi-workers/**`（Python 侧由 FIX-I 负责）
- 其它 TS 文件（`triage-client.ts`、`ui-bridge.ts`、`decision-tool.ts`、`xkey-gate-guard.ts` 等）
- `docs/**`、`.agenticdoc/**`（含 `tasks/`、`design.md`、`pm-state.md`、`achieved.md`）
- 禁止 `git` 写操作、`npm run check`、`npm run build`、`biome check --write .`、全量 vitest、真实网络调用、`Set-Content`

## 验收命令

```bash
cd packages/coding-agent
npx tsgo --noEmit
npx biome check src/extensions/agent-team-loop/worker/worker-mode.ts test/suite/dp3-answer.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/dp3-answer.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-tool.test.ts test/suite/triage-client-state.test.ts test/suite/decision-association.test.ts test/suite/decision-signoff.test.ts
```

四条命令全绿才算完成；把每条的最后一行输出贴进报告。Windows 已知基线：本包 `test/suite` 有
环境性失败，若出现与本卡无关的失败，逐条列名并说明判定依据（不得笼统称"基线"）。

## 交付格式

`report.md`：结论 / 契约落地点（文件:行）/ 四条验收命令输出原文 / 残留 / 未覆盖面
（**禁止**声称「Jev 已作答」——本卡只用假 runner；真 Jev 需 typesafe 凭据）。

## 种子

- 目标锚点：`.agenticdoc/goal.md`（jev 做决策、worker 澄清自消化）
- 现状锚点：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:4415`（`DP3_ID`）、`:4418`（`DP3_QUESTIONS_VERSION` 旧值 `q-b71e824c`）、`:4708`（`DP3_CITATION_RE`）、`:4772-4790`（`buildDp3State`）、`:4808`（`parseAnswerEntry`）、`:4823`（`decideDp3WorkerClarify`）、`:4908-4960`（3a 消费与引用校验）
- 契约来源：`tasks/FIX-I-dp3-jev-native-questions.md`（Python 侧冻结契约）、`https://api.typesafe.ai/api/system-one.md`（Jev 无自由文本题型）
- 历史：`tasks/FIX-G-box-question-type.md` → `tasks/FIX-H-jev-answer-contract.md` → 本卡

## 改动历史

- 2026-10-20 建卡：dp3 3a 从「模型返回带引用自由文本」改为「本地候选 + choice + noul + 本地取引用」。

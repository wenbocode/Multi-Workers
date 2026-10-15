# T-11 · 账本「声明区」标题识别误取报告正文（H1 标题含「变更」⇒ 把报告头部当声明）

- Key: mw-worker-output-contract
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「文件驱动的去中心化协调」「工具白名单按任务类型」）——账本判定是「产物是否可信」的唯一机器证据；误红会把合格 worker 判成 `needs-clarification`。
- **真实事件（本 key 自己的 T-02 worker，`workers/woc-t02-ledger`）**：worker 交付正常（21/21 新用例、12 个既有套件零新增红），但 settle 判 `exit=2 / needs-clarification`，理由是
  `recovery-incomplete: unrecorded write(s): .agenticdoc/mw-worker-output-contract/tasks/T-02-ledger-extractor-hardening.md, .agenticdoc/goal.md`。
  这两个文件**从未被任何 worker 写过**（`goal.md` mtime 停在 2026-09-09，卡文件 mtime 是本卡写入时刻）。
- **PM 已定位根因（可复跑，见下）**：`shared/change-ledger.ts:416 isLedgerHeading`（与 `:426 extractLedgerBody`）的声明区标题识别用 `includes` + `#{1,6}`：
  - worker 的 `output.md` **H1** 是 `# T-02 · 变更账本抽取器加固（W3 · AC-008 / AC-017）— output`，命中 `LEDGER_SECTION_ALIASES` 里的 `变更`；
  - 于是 `extractLedgerBody` 把 H1 **之后的头部区**（第 2–6 行：`Key/worker/card:`、`目标锚点：.agenticdoc/goal.md`）当成「改动清单」正文 ⇒ 卡路径与 `.agenticdoc/goal.md` 被读成「声明写入」；
  - 两者不在 trace 的 `[WRITE_FILE]` 里 ⇒ `extra` 非空 ⇒ 红。
  - 同一函数在 `### 7. 类型检查与改动面` 这类标题上也会命中 `改动`（本事件里被 H1 抢先，属同一类缺陷）。
- **实测复现（PM 已跑）**：对 `workers/woc-t02-ledger/{output.md,trace.log}` 调 `diffLedger(..., {role:"coding", projectRoot})` 得
  `declared=[卡, .agenticdoc/goal.md]`、`extra=[同上]`；仅把 H1 换成一个不含别名的标题后 ⇒ `declared=[]`、`extra=[]`。⇒ 误红的唯一触发面是标题识别。
- **为什么必须在本 key 修**：这直接卡住本 key 的 **AC-010(b)**（「本 key 交付后新跑的 ≥6 个 worker 受判产物**全部** `exit=0`」）——任何标题里带「变更/改动」的卡（本 key 的 T-02 就是）都会误红。同属 `FW-005`（trace.log 变更账本）语义面。
- **修复方向（不是放宽判据）**：
  1. **H1 永不作为声明区标题**：报告的一级标题是文档标题，不是「改动清单」节（级别必须 ≥ 2）。
  2. **别名匹配改为起始锚定**：剥掉编号/列表前缀后，标题必须以别名**开头**，不再用 `includes` ⇒ `### 7. 类型检查与改动面` 不再命中，`## 改动清单（本卡写面）` 仍然命中。
  3. **真红不许被削弱**：`## 改动清单` 下真实列出、而 trace 未记录的文件仍必须红（给正向用例）。
- 边界：本卡**只改声明区标题识别**（`isLedgerHeading` / `extractLedgerBody` 及其别名用法）。**不改** `unjudgeable` 闸、**不改**抽取器（`worker-mode.ts`）、**不改** `collectDeclared` 的声明位置规则（那是 T-21/mw-write-face-guard 的语义）。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts`（**仅**声明区标题识别：`LEDGER_SECTION_ALIASES` 的用法、`isLedgerHeading`、`extractLedgerBody`）
- `packages/coding-agent/test/suite/mwoc-w11-ledger-heading-scope.test.ts`（新建）

## 写入禁止面

其余一切路径。特别地：`worker/worker-mode.ts`（T-10 正在改、T-04/T-05 待改）、`worker/output-*.ts`、`pm/**`、`packages/multi-workers/**` 只读；`shared/change-ledger.ts` 的 `diffLedger` / `unjudgeable` / `parseWriteFileEvents` / `collectDeclared` **语义只读**（只允许在标题识别处改动，且不得改变 `ChangeLedger` 返回字段形状）。**禁止 `npm run check`**；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **H1 排除**：`#` 一级标题（`#{1}`）永不参与声明区识别；用真实事件夹具断言。
2. **起始锚定匹配**：标题（剥编号前缀、折叠空白、ASCII lower）必须以某别名**开头**；`includes` 语义不得保留。
3. **回归夹具（用真实事件，不要自造）**：以 `workers/woc-t02-ledger/output.md` 的**真实形状**为输入（H1 含「变更」+ 头部 `card:` 行与 `目标锚点：.agenticdoc/goal.md`），断言 `declared` **不含** `.agenticdoc/mw-worker-output-contract/tasks/T-02-ledger-extractor-hardening.md` 与 `.agenticdoc/goal.md`、`extra=[]`。（可把该文件读入或在测试内重建同形文本；重建时逐行注释来源。）
4. **合法变体仍命中**：`## 改动清单`、`## 改动清单（本卡写面）`、`## 变更清单`、`## Changed Files`、`## Files Changed` 各 ≥1 例命中。
5. **负例**：`# 变更账本…`（H1）、`### 7. 类型检查与改动面`、`## 上下文来源` 各自不命中。
6. **真红不弱化**：1 例「`## 改动清单` 声明一个 trace 未记录的真实文件 ⇒ `extra` 非空」的正向用例（可复用既有夹具形态）。
7. **不回归**（给原始输出）：`change-ledger.test.ts` **12/12**、`mwgal-t17b-ledger-infra-writes` **16/16**、`mwgal-t17c-ledger-unresolvable` **15/15**、`mwds-t21-write-intent-soundness` **13/13**、`mwoc-w3-ledger-extractor` **21/21**（T-02 新建，必须继续绿）。
8. `npx tsgo --noEmit` = 0；`git diff --stat` 只含允许面文件。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑命令与原始输出**：真实事件夹具修复前的 `declared/extra`（复现误红）+ 修复后的 `declared/extra`（应为空）、五条合法变体与三条负例的判定表、真红正向用例、五组既有套件条数、新测试条数。末尾一行 `[VERIFY] …`。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwoc-w11-ledger-heading-scope.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/change-ledger.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwgal-t17b-ledger-infra-writes.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwgal-t17c-ledger-unresolvable.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t21-write-intent-soundness.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwoc-w3-ledger-extractor.test.ts
npx tsgo --noEmit
git diff --stat -- packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts packages/coding-agent/test
```

## 改动历史

- 2026-10-14 T-02 收口时暴露：`woc-t02-ledger` 因标题识别误取报告头部被判 `exit=2 / needs-clarification`；PM 用 `diffLedger` 直调复现并定位到 `isLedgerHeading` 的 `includes` + `#{1,6}`（见「上下文」的实测）。
- PM 判定为**框架缺陷**而非 worker 交付问题（worker 实质交付已复核通过），故新建本卡；同时把该误红模式登记进 `_pitfalls.md`（T-09 收口时）。

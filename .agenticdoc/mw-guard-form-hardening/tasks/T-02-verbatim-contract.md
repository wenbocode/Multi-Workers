# T-02 — `verbatim` 判定与 deny 域收敛

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**（不得改写、不得凭记忆猜测）：`design.md` §§4.2.1（逐字符状态机 + 5 态表）+ §4.2.3（求值顺序）（含 L1–L18 落点总表与 VC 定义）+ `spec.md` AC-001 + 下列证据文件
- 证据: `evidence/research/design-write-guard-landing-20261011.md` §1/§2（数据结构改动表 + `verbatim` 伪代码 + 边界例实测）；`evidence/research/spec-direction-contract-20261011.md`（36 条语料 + P-1…P-6）
- **唯一允许改的路径**: `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`；`packages/coding-agent/test/suite/mwds-t03-bash-write-scope.test.ts`；`packages/coding-agent/test/suite/mwds-t12-regression.test.ts`（仅补第 3 实参）；外加自身目录 `report.md`
- 禁止: 运行 `npm run check`/全量 vitest/`mw build`/`mw.py build`（PM 负责）；修改 `design.md`/`spec.md`/`plan.md`；改本卡未列出的文件；删既有测试用例（只能新增或按下卡明示修订）

## 卡元信息
- AC: AC-001｜VC: VC-001…VC-005｜波 2｜链 S1（`worker-mode.ts`，依赖 T-01）
- 验收命令（PM 执行）: `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t03-bash-write-scope.test.ts`

## 必须实现
1. `ShellToken`/`BashWriteCandidate` 各加 **required** `verbatim: boolean`（唯一构造点：tokenizer 3 处、extractor 2 处，逐个补齐；不得给默认值绕过）。
2. `verbatim` 在 **extractor/词法阶段**算出（verdict 层四形态逐字节相同，无法恢复引用状态）。
3. `BashWriteScopeRule` 加 `allow-unknown`；verdict 加 `risk?: "deny-basename"`；判定实现「verbatim → deny 6 规则 → scope → write-scope → allow/deny；非 verbatim ⇒ `allow-unknown` + 审计」。
4. 单引号包裹与反斜杠转义形式**必须仍 deny**（VC-004）；双引号内 `$` **不失活**。
5. **第 3 实参收口（T-01 已落一半，本卡收尾）**：T-01 已让生产侧唯一调用点（`worker-mode.ts:2005-2006`）显式传 `candidate.verbatim`，但为兼容 5 处**旧测试**调用把形参留成了默认 `verbatim = true`。**本卡必须删掉该默认值（改为 required）**，并把 `test/suite/mwds-t12-regression.test.ts:136/137/149/161/173` 这 5 处补成显式 `true`（这些用例全是**字面量**路径，语义不变、断言文本不得改动）。理由：默认 `true` 表示「未标注即视为字面量」，未来任何忘记传参的生产调用都会被静默判为字面量 ⇒ 恢复 A2 的误拦方向。
6. **加守卫断言**：生产路径上含 `$`/glob 的 token 必须得到 `allow-unknown`（行为级断言，不能只断言函数可被调用）；若条件允许，另断「生产调用点不得省略第 3 实参」（例如导出面/调用点的静态检查或行为等价用例）。
7. 测试：36 条语料全量断言 `must_allow=19` 中 `false_positives=0`、`must_block=14` 中 `must_block_currently_allowed=0`（前值：16 误拦 / 0 漏放）；`'$T/...'` 与反斜杠形式具名用例。

## 交付
- 唯一写入（除源码/测试外）= `worker_file file="report.md"`、`mode="append"` 追加、`mode="write"` 覆盖；禁止其它路径。
- `report.md` 必须含：改动文件清单、前后行为对照表（输入/期望/实测）、红→绿证据、未完成项与原因（若有）。

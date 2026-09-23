# Achieved: mw-rag-integration-fix

- key: `mw-rag-integration-fix`（修补 key；上位 `mw-rag-integration` 已 DONE，其质检报告后被独立复核改为 ❌ 需修订）
- date: 2026-09-22
- 目标：闭合独立复核（`mw-rag-integration/evidence/quality-gate-review-2026-09-22.md`）提出的 5 组缺口
  F-1~F-5 / D-1~D-8，并让「用了 RAG」在运行时真的成立、证据可证伪。

## 系统行为变化

**1) RAG 角色/阶段默认真的在运行时生效（本 key 的核心行为变化）**

- 之前：`rewriteDefaults` / 角色·阶段默认解析**在生产中零调用点**（只有测试直调）→ 配置里写 `roles.design`/`phases.design`
  对实际发出的 MCP 工具名**毫无影响**，AC-006 是纸面条款。
- 现在：`rag/config.ts` 的 `resolveDefaults(config, role, phase)` 是**每语言唯一的解析入口**，被 `callRag`（工具调用）与
  `renderRagBlock`（task.md 注入块）共用；`registerRagTools` 接收 `role`/`phase`（`worker-mode.ts:669` 传入
  `roleForTaskType(meta.type)` 与 `meta.phase`）。效果：`role=design` 且 agent 未显式给开关时，实际发出的工具名是
  `rag_search_multi_rounds`；`role=coding` 仍是 `rag_search`；没有 role/phase 时（PM 会话、未启用项目）**零介入**。
- 影响面：任何配了 `rag.roles.*.rewrite` / `rag.phases.*.rewrite` 的项目，行为会与配置一致（此前被忽略）。
  未配这些字段的项目行为不变（`resolveDefaults` 退化为 `defaultServer` / `null` / `false`）。

**2) 默认解析优先级统一为「声明值」：显式 > 角色 > 阶段 > `default_server`**

- 之前 TS 用 `roleRes?.server ?? phaseRes?.server ?? defaultServer`，而 `resolveForRole` 内部**已回落** `defaultServer`
  → 只要设了 `default_server`，**阶段声明的 `server` 永远被吞掉**（Python 侧取声明值，两侧不一致）。
- 现在两侧都取声明值；`resolveForRole`/`resolveForPhase` 被删除（避免留下第二个「有实现没人用」的死角）。
  跨语言用同一 fixture（`test/fixtures/rag/phase-only-target.yml`）钉住：两侧都必须解析出 `{server: A, source: docs, rewrite: true}`。
- 已知且已文档化的边界（design D-102）：注入块的 `[mw] Rewrite:` 行按**默认 server** 解析；agent 显式传 `server:` 时
  运行时按**被调用 server** 的能力复核，两者可能不同——这是「默认值声明」语义，与 Python 一致。

**3) rewrite 兜底口径两侧对齐（Python 侧修正）**

- 之前：TS 认「研究角色**或**研究阶段」，Python 只认研究**角色** → 仅阶段为 `spec`/`design` 时两侧结论相反。
- 现在：`mw_common.py` 新增 `RAG_RESEARCH_PHASES = frozenset(("spec", "design"))`，兜底改为「角色或阶段」。

**4) 未登记 `type:` 的角色回落三处对齐为 `coding`**

`mw.py`（audit）、`mw_common.py`（注入块）、`dispatch-models`（TS 侧）此前各有一套回退；现全部落到 `"coding"`，
`type: foobar` 在两侧判同一个 role、同一个 `required` 结论（`VC-105`）。

**5) 文档/契约与实现对齐，删死变量**

- README 的 `mw rag` 用法以 argparse 为唯一真源：四条命令补上**必填** `--project`、删掉不存在的 `probe --server`、
  补 `--json`/`--key`/`--out`，新增退出码表（`list`/`probe`/`sync` = 0/1，`audit` = 0/1/2）；
  `mw rag probe` 的 help 不再声称「never a non-zero exit」（配置错误确实退 1）；`rag-rewrite-degraded` 澄清为
  「服务端改写失败降级」而非「开了多轮」。
- 删除死变量 `MW_RAG_ENABLED`（`launcher.py` 注入 + 声称 worker 侧据此门控的不实注释）：全仓**无读取方**，
  删除不改变任何行为；env 文档从未登记它，CHANGELOG 保留一处变量名字面提及以便老用户 grep。

**6) VC-018 的证据层级如实声明为 L1**

原声明「VC-018 需 L2 证据」，实际证据是假 pi + 合成事件的进程内集成测试。本 key 补了运行时双用例
（真实 key 布局下预置 `<server>-<slug>.md` → 无 marker；无文档 → 打 `rag-required-missing`）并**独立裁定其层级为 L1**，
上位声明追加 `REVISED → L1` 标记；L2 证据（真实 RAG 服务）进「遗留」。

**7) 证据行可证伪（AC-108 落地）**

`VC-008`/`VC-102`/`VC-105`（两侧）/`VC-111` 的证据行字段改为取自被测数据（fixture 观测的 wire 名、命中数、
trace 正则解析值、audit 记录值），并用 3 条反例试验证明它们会随实现变红（见验证与遗留）。

## 验证

- `evidence/verify-run-2026-09-22.md`（T-18 **独立验证**，第三方视角）：TS `rag-*` `105 passed | 1 skipped`；
  `agent-team-loop*`+`autopilot-*` `488 passed`；Python 全量 `805 passed, 9 deselected`；golden sha256 与本 key 开工前一致；
  `test_autopilot_l0.py` 零 diff；`npm run check` exit 0；bundle 888791 B / `resolveDefaults` ×3 / mtime 晚于全部源。
- **3 条反例**（每条均还原并核对 sha256）：A 反转研究角色 rewrite 能力 → `rag-role-defaults` 红、wire 名随数据变；
  B 断掉 `worker-mode.ts` 的 key 目录 → VC-106「有文档→无 marker」用例红、反例用例仍绿（**PM 亲自复现**）；
  C 清空 `RAG_RESEARCH_PHASES` → Python VC-111 红、TS 侧不受影响。
- T-18 如实降级了两个证据行（VC-102/VC-105 两侧字段为字面量）→ **PM 直执 T-20** 改为实测插值（断言未变），
  复跑 TS `rag-required` + `rag-role-defaults` = 15 passed、Python `test_rag_audit -k vc105` passed、全套件与 `npm run check` 复绿。
- 质检报告：`evidence/quality-gate-report-2026-09-22.md`（23 项：20 充分 / 3 ⚠️ / 0 ❌，判定 ✅ 通过）。

## 遗留

- **R-1（证据层级，接受不处理）**：VC-018/VC-106 的 **L2 证据未做** —— 需要真实 rag-mcp（真实 worker 进程跑 `rag-research`
  并产出带可验证引用的 `<key>/rag/<server>-<slug>.md`）。真实联调在两轮 key 中均被明确排除；本 key 已如实声明 L1 并给上位
  声明加修订标记。将来若做真实联调，把它并入那轮的 L2 清单。
- **R-2（框架级，需用户决定）**：review 型 worker 的**交付通道缺陷** —— 只读工具集使其结论只能靠最后一条消息，
  12 次 review 任务 8 次零交付（`stream closed before response.completed` / 空 settle），而 coding 型 14/14 正常。
  本 key 的处置是流程规避（coding 型 reviewer + 只允许写一个报告文件 + 骨架优先 + 每节 `edit`），**不是修复**。
  已记入 `_pitfalls.md` P-007。去向：待用户决定是否立新 key 在框架层修（给 review worker 受限写通道，
  或 harness 在 stream close 时持久化部分最终消息）。
- **R-3（可选加强，接受不处理）**：VC-106 的证据行载体是测试内直调 `validateResearchDoc`（runtime 主张由 trace 断言承担）；
  若要严格 data-carrying，应让 runtime 的 `emitRagRequiredMissing` 回吐自己的 report。当前已由反例 B 证明可证伪，不阻塞。
- **R-4（未测，接受不处理）**：多份调研文档遍历、`rag_chat` 重复计费语义、`rag-e2e-slow`（`MW_RAG_SLOW`）真实慢调用/看门狗观察。
- **R-5（已记pitfall，接受不处理）**：文档结构图/流程图在符号删除后会静默过期（mermaid 门禁只查语法）——已记入 \_pitfalls.md\ P-008。

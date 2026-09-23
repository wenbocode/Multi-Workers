# Task T-11-VERIFY: 全量验证 / 逐 VC 证据链 / 文档与 CHANGELOG / 结案材料

## 基本信息
- Stage: 6
- 代码状态: 未开始
- 验证状态: 未验证
- 负责 Agent: worker（`coding`，第 1~4 节）+ PM 主窗口（第 5 节结案材料、`achieved.md`、phase 推进）
- ac_refs: [AC-001~AC-018]
- vc_refs: [VC-001~VC-028]
- pattern_refs: []

## 描述

### 1. 逐 VC 证据链

- **`[VERIFY]` 行的发射通道（血泪教训，T-02/T-12 各踩一次）**：本仓库 vitest 配置为 `silent: "passed-only"`，**绿灯用例里的 `console.log` 会被吞掉**，证据行在必跑命令的输出里根本看不见（T-11 采集不到）。必须用 `process.stdout.write("[VERIFY] ...\n")`（末尾自带换行）。Python 侧 `print` 正常，但需 `pytest -q -s` 才显示。
- 汇集 T-01~T-10 各任务的 `[VERIFY] VC-0NN:` 输出行，产出 `evidence/verify-run-<date>.md`：每条 VC 一行（VC ID / 断言命令 / 实际输出 / PASS-FAIL / 来源 task）。
- 缺证据的 VC 必须补跑对应测试或写清"未验证原因"（不许留空）。
- **K1/K2 出口判据**：VC-001~VC-028 全部有实测输出；任一 FAIL → 回退到对应 task 修复后重跑，不得带 FAIL 进 `achieved.md`。

- **T-14 新增的必须现场核实项（阶段轴 + VC-014 的 TS 面）**：
  - `phase:` 头由**两侧**派发器写入：Python 侧用 `render_task_md(..., phase="DESIGN")` 断言 `type:` 后出现 `phase: DESIGN`，且 `phase=""` 时输出**逐字节等于**不传（PM 已用临时脚本复核过 `empty_identical=True`，你要留下自己的命令与输出）；TS 侧 `planDispatchFrontmatter` 同理。
  - `_owner_phase(repo, "mw-rag-integration")` 在真实仓里必须返回 `EXECUTE`（PM 实测值）；`_scratch` / 缺 pm-state → `""`（**不许猜**）。
  - worker 末态：required-but-unused → trace 有 `rag-required-missing` 且 `output.md` 有 `RAG 未生效` 标注；有可核对引用时不发；未启用/未 required **零写入**；重复收尾**幂等**。
  - 与 `mw rag audit` 一致：带 `phase:` 且无引用的任务 → `required_missing` 非空。
- **VC-017 L2 的落地方式（必须真跑一次，不许只写"未验证"）**：把"idle 阈值 60s + 单次 180s 慢调用下 worker 存活到返回、`rag_call` 的 `ms >= 180000`、看门狗处于启用态"做成一个**默认跳过、由 env 开关打开**的慢速集成用例（如 `MW_RAG_SLOW=1 npx vitest --run test/suite/rag-e2e-slow.test.ts`），然后把**打开开关那次**的实际输出贴进 `evidence/verify-run-<date>.md`。要在证据文档里写明这个取舍（默认跳过的原因 = 3 分钟/次的 CI 成本），否则等于没有 L2 证据。
- **上游明确划给本任务的 VC 子项（T-05 只做了 L1，别漏）**：
  - **VC-017 L2**：真实 180s 慢调用下 worker 必须存活到调用返回（`rag_call` 的 `ms >= 180000`），且必须断言 idle 看门狗处于启用态（存在看门狗/检查点日志）；
  - **VC-013 `argv_clean`**：派发/启动侧（T-07/T-08）的 token 不出现在 argv/命令行里；
  - **VC-028 wire 名**：映射结果需在证据链中可核对（`mcp_tool` 字段，见 VC-011 行格式）；
  - **AC-018/VC-028 的真实服务侧**：T-13 全部基于厂商 `references/tools-reference.md` 构造的 fixture，未对线上服务实测——本任务至少要在结论里如实标注这一限制。
### 2. 全量测试与检查

- TS：`packages/coding-agent` 包根跑 RAG 相关套件全绿（`rag-*.test.ts`），再跑既有 `autopilot-*` / worker 相关套件确认零回归；Windows 已知基线（89 项环境失败）按 AGENTS.md 分类口径处理，不得新增失败。
- Python：`packages/multi-workers` 下 `python -m pytest -q` 全绿（含 `test_autopilot_l0.py` 零修改）。
- `npm run check` 0/0/0（**跑完整输出，不截尾**）。
- **扩展 bundle 重建**：跑 `packages/multi-workers/build-extension.sh` 重建已追踪产物 `packages/multi-workers/dist/extensions/agent-team-loop.js`（dist 在版本控制内，`mw init` 分发用），并把 diff 纳入修改面审计；重建后重跑一次 TS 套件确认 bundle 无回归。
- 需要时跑 `./test.sh` 作为可比口径记录（不跑 e2e）。

### 3. 修改面（零回归）审计

- `git status` + `git diff --stat` 逐文件核对：改动只落在 `.agenticdoc/mw-rag-integration/**`、`packages/coding-agent/src/extensions/agent-team-loop/{rag,worker,pm,shared}/**`、`packages/coding-agent/test/**`、`packages/multi-workers/{mw.py,mw_common.py,launcher.py,autopilot/dispatch.py,skills/**,test/**,test_rag_*.py}`、两个 CHANGELOG、`packages/multi-workers/README.md`、`packages/coding-agent/docs/environment-variables.md`。
- 硬性断言：`git diff --stat packages/multi-workers/test_autopilot_l0.py` 为空；既有测试文件（`test_autopilot_*.py` / `test_partition_dispatch.py` / `test_serve_doctor.py` / 既有 `*.test.ts`）**零修改**；**本 key 不改** `index.ts`（它的未提交改动属其它会话的 mw-implementation-gate）。
- **两处"文本层守护的钝边"必须在结案文档里如实记录**（不是缺陷，但会误导后来人）：
  1. `test_rag_cli.py::test_extension_source_never_references_the_installed_skill` 匹配任何 `.ts` 里的 `mw-rag.md` / `mw-rag/SKILL` 字面量 —— T-04 的注释与 T-09 的注释都被它误伤，PM 已改注释（**未放宽守护**）；后来人写注释时会再撞一次。
  2. `test_autopilot_l0.py::test_vc007_static_scan` 禁止 `autopilot/*.py` 里出现 `- Phase:` 字面量（本意是"只有 `advance_phase.py` 能写那条接口行"）；T-14 只是**读**它，为过扫描把前缀拆成 `"- " + "Phase:"` 两个常量。属"读被写守护误伤"，代码与测试都保持原样，但要在文档里点明。
- 环境噪声排除：`packages/coding-agent/Python/_cache/`（Python install manager 自写缓存）不属于本 key 产物，在修改面审计里单独标注为环境噪声（不删、不提交、不算本 key 改动）。
- `packages/multi-workers/dist/extensions/agent-team-loop.js` 必须包含本 key 的重建结果（不得只改 src 不重建 bundle）。
- 未启用项目零影响：现场复跑 VC-001 的四断言（工具数/注入块数/请求数/文件存在性）并在证据里附输出。

### 4. 文档与 CHANGELOG

- `packages/multi-workers/README.md`：新增 "RAG 接入（可配置）" 章节——两层配置位置与逐字段合并规则、`target.yml` 的 `rag:` 段示例（含 `roles/phases.require`）、`mw rag list|probe|audit|sync` 用法、`MW_RAG_SERVERS_FILE`/`MW_RAG_SERVERS_HOME` 测试钩子、凭证只以 `token_env` 名出现。
- `packages/coding-agent/docs/environment-variables.md`：登记 RAG 相关 env（`MW_RAG_SERVERS_FILE`、`MW_RAG_SERVERS_HOME`、`MW_RAG_PYTHON`（skill 形态解释器覆盖，缺省 Windows `python` / 其它 `python3`），以及"token env 由配置声明、值仅存在于 serve 进程环境"的规则）。
- `packages/multi-workers/README.md` 必须写清**逻辑工具名 → 参考服务真实工具名**的映射（AC-018）：`rag_graph` → `graph_query`；`rag_sources` → `list_sources` + `list_collections`（两次调用合并）；重写开关为真时的 `rag_search` → `rag_search_multi_rounds`；其余同名。这是使用者最容易踩的坑（照逻辑名去查服务端工具会查不到）。
- task.md 的 `phase:` 头（阶段轴，AC-015 的前提）要在文档里说明：派发器在知悉 key 阶段时写入、未知不写、`mw rag audit` 与 worker 都读它、`phases.<X>.require` 必须与 pm-state 的阶段值**同大小写**。
- CHANGELOG（`## [Unreleased]` → `### Added`）：`packages/coding-agent/CHANGELOG.md`（工具面 / 降级 / 证据行 / rag-research 类型）、`packages/multi-workers/CHANGELOG.md`（两层配置 / env 注入与撕裂检查 / `mw rag` 四动词 / skill 同步）。遵循仓库格式，不修改已发布版本段。

### 5. 结案材料

- 写 `achieved.md`（含 `## 系统行为变化` 与 `## 经验教训`，后者指向 `_pitfalls.md` 是否需新增条目）。
- 登记 K3 遗留（RAG 硬门禁/gate、`rag-research` 的 conductor 支持、真实 rag-mcp 端到端 smoke）到 backlog 段落，并说明为何不在本 key 范围。
- 人工验收说明：给出 3 条可复现命令（启用项目 `mw rag list` / `mw rag probe` / `mw rag sync`）+ 一次真实 worker 的 `trace.log` 证据行样例。

## 完成判定

- `evidence/verify-run-<date>.md` 覆盖 VC-001~VC-028 且无 FAIL（含 VC-017 L2 与 VC-028 的慢速/映射证据）。
- `npm run check` 0/0/0；两侧测试零新增失败；`test_autopilot_l0.py` 与既有测试零 diff。
- 两包 CHANGELOG 与 README/env 文档更新落地；`achieved.md` 两节齐备。
- 之后才允许 `advance_phase(key, "done")`（quality gate 报告落地后再推进）。

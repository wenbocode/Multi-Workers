# T-16 独立 quality-gate review（由独立 review worker 执行，PM 不参与其结论）

- key: mw-vision-role · 波 5（T-14 之后） · 独占写面：`.agenticdoc/mw-vision-role/evidence/reviews/qg-review-mw-vision-role-20260926.md`（新建）
- ac_refs: 全部活跃 AC（AC-001…AC-017、AC-019；AC-018 = OBSOLETE） · vc_refs: VC-001…VC-017、VC-019
- 依赖: T-14（证据文档产出） · 预估: 45-60min

## 你的角色

你是**独立审查方**，不是实现方。禁止修改任何源码/测试/证据文档（除你的输出文件）；不得 `git add`/commit；不得跑全量 vitest/`npm run build`；`npx biome check` 不加 `--write`；禁止 PowerShell `Get-Content/Set-Content` 改文件。

## 必须独立复算的东西（不得只读结论）

1. **AC/VC 覆盖矩阵**：从 `spec.md` §3 抽 AC 列表、从 `design.md` §7 抽 VC 列表、从 `evidence-requirement.md` 抽映射，**自己重算**是否一致（几对几、有无漏项、AC-018 是否确实标记 OBSOLETE 且未计入 19 条判定）。
2. **两侧镜像逐元素相等**（这是本 key 的核心不变量）：
   - Python `mw_common.py` 的 `DISPATCH_ROLES` / `TASK_TYPE_TO_ROLE` / 工具白名单 ↔ TS `shared/dispatch-models.ts` 的 `DISPATCH_ROLE_BY_TYPE` / `DISPATCHABLE_TYPES` / `TOOL_ALLOWLISTS`，**逐元素**比对（数量、顺序、取值），不接受"看起来一样"。
   - `vision` 的角色默认模型解析优先级是否与既有 4 角色一致（`resolve_dispatch_model`）。
3. **门禁顺序**：`planDispatchFrontmatter` 里 auto-route → capability gate → 任何磁盘写入（`fs.mkdirSync` 等）的相对顺序，自己读代码确认「拒绝时目录不被创建、`_workers.parallel` 不被修改」；并确认 auto-route **只**改 `model:`（`type:` 逐字不变）。
4. **fail-open 契约**：模型值为空 / 带 CLI 前缀 / 未知 provider 时能力判定为 `unknown` 且**不拒绝**（与 `validateModelValue` 同契约）。自己找代码与用例双侧确认。
5. **只改扩展、不动核心**：`git status`/`git diff --stat` 判断本 key 的改动是否**全部**落在 `packages/coding-agent/src/extensions/agent-team-loop/**` + `packages/multi-workers/**` + `.agenticdoc/**`；pi 核心（`src/core/**`、`src/cli/**` 等）零改动；`settings.json` 的 `defaultModel` 优先级未被改。
6. **未引入新 provider/凭证**，也未改 `.mw/dispatch.yml` 的既有角色默认值。
7. **测试非空洞性**：从 `evidence/runs/verify-mw-vision-role-20260926.md` 与各 `workers/*/output.md` 的对照记录判断——每条"还原缺陷 ⇒ 变红"是否**真的**在执行时红过（检查失败输出的具体断言行，而不是只看 worker 的自述）；识别任何"断言恒真/被跳过/未真正运行"的用例。
8. **PM 声称的证据抽检**：对 PM 记录的 E-10 / E-11 / T-15 结论，**你自己重跑一遍**命令（`mw.py model show`、`mw doctor --json` 的 `images` 字段与 suggestion 列表），确认与记录一致。

## 必须主动找反例（对抗式）

- 构造至少 2 个**规则文档没写的边界输入**，判断行为是否仍符合 AC 的**意图**（而非字面）：例如
  - `images: yes` + 显式 `model:` 为**能**看图的模型 ⇒ 是否被错误拒绝（应为通过）；
  - `images:` 头写成不合法值（如 `maybe`）/ 大小写变体 ⇒ 行为是否可解释、是否静默误判；
  - `type: vision` 但 ``（不带任何图片引用）⇒ 是否被误伤；
  - 显式 `images: no` + 自动探测**命中**图片路径 ⇒ 优先级是否如 D-013（显式声明优先）。
- 任一 AC 的**退出码/落盘副作用**（目录是否创建、队列行是否新增）都要有可复现证据，不接受推断。

## 硬约束

- 只读 + 重跑命令；审查结论必须有可复现命令与原始输出支撑，无证据的判断一律标注为「未验证」。
- 发现阻塞级问题 ⇒ 明确写 `BLOCKER:` + 复现命令 + 期望/实际；不得顺手改代码。

## 输出格式（写入 `evidence/reviews/qg-review-mw-vision-role-20260926.md`）

```
# QG Review — mw-vision-role（独立审查）
- reviewer: <task_key> · date: 2026-09-26 · 代码版本: <git status 摘要 + 是否 dirty>
## 1. AC/VC 覆盖矩阵（自算）
<AC → VC → 测试/证据 → 判定(PASS/FAIL/未验证)>
## 2. 不变量核验（逐元素比对 / 顺序 / fail-open / 改动面）
## 3. 对抗式反例与结果
## 4. PM 证据抽检（重跑命令 + 原始输出）
## 5. 测试非空洞性判断
## 6. 结论
- QG verdict: PASS / PASS-WITH-NITS / FAIL
- BLOCKER 列表（含复现命令）
- NITS / 建议（不阻塞）
- 未验证项与原因
```

## [VERIFY] 格式

`[VERIFY] VC-QG: acs_total=<n> acs_pass=<n> invariant_violations=<n> blockers=<n>`

## 交付

上述审查文档（含所有重跑命令的原始输出片段）。

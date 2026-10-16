# Mini-Spec: mw-model-fallback-cli

- Date: 2026-10-15
- Mode: pm mini fast path (direct execution, no plan/tasks)
- Deps: mw-model-error-perception（T-02 配置层已落地：validate_fallback_models/_model_write 读改写/doctor dispatch_fallback）
- Origin: 用户需求——fallback_models 的设置入口应走 CLI（现状只能手编 YAML）

## Problem

`.mw/dispatch.yml` 的顶层 `fallback_models`（每类别 1..4 个有序 `provider/model` 备用链）没有 CLI 设置入口：`mw model set` 只写 `models.<role>`，fallback 只能手编 YAML。

## Change

1. `mw.py` model 子命令组新增：
   - `mw model set-fallback <role> <model[,model...]>`：逗号分隔 1..4 个 `prefix/model`，校验复用 `validate_fallback_models` 同规则（格式/上限/`*_cli` 传输前缀拒绝/去重），写入顶层 `fallback_models.<role>`（经 `_model_write` 读改写，保留其余键）；空串/全空白参数拒绝（非零退出）。
   - **规格修订（实现后由 R-01 复核认定，以本节为准）**：原稿写「空串/全空白视为清空该链（等价 clear）」与「无链时每 category 显式 `-`」；实现改为 **空值报错拒绝**（静默清空是危险的配置动作——用户很可能是拼错参数而非想删链）且 **show 仅在整体无链时打印一行 `fallback: (none configured)`**（有链时按 category 打印，避免刷出十行 `-`）。位置参数名在补弃的 `spec.md` 中统一为 `TASK_TYPE`（任务类型非角色）。
   - `mw model clear-fallback <role>`：移除该 role 键（链空则连 `fallback_models` 顶层键一起移除，不留空对象）。
   - `mw model show` 追加 fallback 链展示（每 role 一行，无链显式 `-`）。
2. 校验与错误出口与 `model set` 同风格（exit 码/中文错误行）。
3. 测试（`test_dispatch_models.py` 追加）：set-fallback 写入/读改写保留 models 键/上限 4 拒绝/非法前缀拒绝/去重/clear-fallback 移除含空对象清理/show 展示。
4. TS `/mw model` 转发：若为子命令白名单，追加两个子命令透传（保持与 CLI 同名）；若为透传式则无需改动（核实后定）。

## Files（写入允许面）

- `packages/multi-workers/mw.py`
- `packages/multi-workers/test_dispatch_models.py`
- `packages/coding-agent/src/extensions/agent-team-loop/`（仅当 TS 转发需白名单登记时的最小改动）
- `packages/multi-workers/CHANGELOG.md`、`.agenticdoc/mw-model-fallback-cli/mini-spec.md`

## Acceptance Criteria

| AC | 内容 | 验证 |
| --- | --- | --- |
| AC-1 | set-fallback/clear-fallback 写入语义正确且保留既有顶层键 | pytest 新用例 |
| AC-2 | 校验规则与 validate_fallback_models 一致（上限 4/前缀/去重/格式） | pytest 新用例 |
| AC-3 | doctor dispatch_fallback 与 show 展示一致 | pytest/doctor 手验 |
| AC-4 | 既有套件零回归 | test_dispatch_models + test_mep_fallback_config 全绿 |

## Out of Scope

- pi 窗口 `/mw model` 的 UI 交互美化；per-phase fallback；自动降级策略变更。

## Outcome (2026-10-15)

实现与规格的差异已按上节「规格修订」记录（空值处理 / show 形态 / 参数命名），其余按稿实现；R-01 独立复核后追加 F1/F2/F3 修复与 D1-D4 测试补充，见下。

| 面 | 落点 |
| --- | --- |
| `mw.py` | `_model_write` 增 `fallback_models` 参数（`None`=原样保留 / 非空=替换 / 空=删顶层键）；`cmd_model` 新增 `set-fallback` / `clear-fallback` 分支；`show` 追加 `fallback <type>: m1, m2`（无链显式 `fallback: (none configured)`）；argparse 两个子命令（`TASK_TYPE` 用 `FALLBACK_TASK_TYPES` 做 choices） |
| 校验复用 | `mw_common.validate_fallback_models({task_type: raw_list})` 单一事实源：顺序保留、大小写归一、去重、`*_cli` transport 前缀拒绝、未知前缀拒绝、1..4 上限；拒绝时文件零字节变化 |
| TS 转发 | `runMwModelCommand` 新增 `set-fallback` / `clear-fallback` 分支（薄转发，逗号链作为单个 argv 元素；用法守卫不调用 runner）；总用法行同步 |
| 测试 | `test_dispatch_models.py` 新增 `TestModelFallbackCli` 10 例（roundtrip 保 models 键 / 归一化去重 / 上限拒绝 / CLI 前缀拒绝 / 未知 type + 空值 / 损坏块拒绝且文件不变 / clear 逐级删到顶层键消失 / 未配置 noop / show 展示两种形态）；`agent-team-loop.test.ts` 新增 3 例（转发 / 用法守卫 / clear 守卫） |
| 文档 | `packages/multi-workers/README.md`（命令表、用法示例、`/mw model` 行、fallback 段落注明 CLI 写入 + 注释不保留）；两个包的 CHANGELOG `[Unreleased] ### Added` 各一条 |

### Evidence

- Python：`python -m pytest test_dispatch_models.py test_mep_fallback_config.py -q` → 104 passed（其中新增 10）
- TS：`vitest --run test/extensions/agent-team-loop.test.ts` → 199 passed / 1 failed（该失败为已登记基线：`.agenticdoc/mw-guard-form-hardening/design.md → worker/worker-mode.ts:747` 行漂移锚点校验，与本改动无关）；`-t "fallback"` → 5 passed
- 静态：`npx biome check` 本改动两文件 → No fixes applied；`npx tsgo --noEmit` → 无输出（通过）；`npm run check` 全链被他人窗口 mwoc-* 测试的已知 3w+2i 基线阻断（biome `--error-on-warnings`），非本改动
- 真实 CLI 手验：临时项目 set-fallback（2 条，含大小写/重复输入）→ 文件 1 条归一化结果且 `models` 保留；clear-fallback 到空 → `fallback_models` 键整体消失；5 条 / `codex_cli/` / 未知 task type 均正确拒绝；`mw model show --project .`（本仓）→ `fallback review: timi/deepseek-v4.1-flash`；`mw doctor --project .` → `dispatch_fallback: review=timi/deepseek-v4.1-flash`

### 遗留

- 生效面：Python CLI 立即生效；pi 窗口内的 `/mw model set-fallback` 需 `mw build --install`（重建 bundle）+ 窗口重启。
- CLI 写入是 YAML 重新序列化：手写注释不保留（README 已注明）。

## R-01 独立复核处置（2026-10-15）

已派 `review-fallback-cli`（type: review，报告 `.agenticdoc/mw-model-fallback-cli/evidence/review-fallback-cli-20261015.md`）。首轮判定 ❌ 未通过（3✅/1⚠️/2❌），处置如下（PM 直执，均在本 key 写入面内）：

| 项 | 性质 | 处置 |
| --- | --- | --- |
| **F1**（P1） | `mw.py` 在校验前 `strip()`+过滤空项，使 `a,,b` 与项内 CR/LF 绕过 validator 的空项/单行规则 | **已修**：改为 `args.value.split(",")` 原样交给 `validate_fallback_models`（仅保留「整个参数全空白」的用户友好报错）；空格容忍不变（`parse_model_value` 自身 strip）。回归：mixed-empty / 项内换行拒绝 + 「带空格仍接受」反例 |
| **F2**（P2） | mini-spec「Implemented as specified; no deviation」不成立（空值处理/show 形态/参数名） | **已修**：本文件写「规格修订」节 + Outcome 改写（见上） |
| **F3**（P2） | README 称「列表内重复」为 issue，实际 validator 去重接受；前缀表缺 `zai/` | **已修**：README fallback 段改为「重复接受并去重（保首次、大小写归一）」+ 前缀表补 `zai/` 行 |
| D1-D3（Q5 欠债） | 缺 CLI 拒绝路径与逐字节 oracle | **已补**：新增 `TestModelFallbackCliRefusals`（15 例：mixed-empty / 项内换行 / 空白容忍 / 4 条边界 / 8 项拒绝矩阵逐字节不变 / 无文件不创建 / 整图保留 `yaml.safe_load` / show 坏块非零） |
| D4（Q5 欠债） | TS 守卫/透传覆盖不足 | **已补**：守卫矩阵（缺 task type、clear 多参、空引号）+ 双引号含空白链原样透传 + runner 失败 + 通用 usage 含新子命令 |
| Q4/Q6 文案 | 注册处注释 / `/mw` 通用 usage / `mw-runner.ts` 注释仅列 show/set/clear | **已修**：三处同步新子命令 |
| show 可观测性 | 坏 fallback 块时 show 仍返回 0 | **已改**：与坏 `models` 块同契约，返回 1（新增用例） |

复核后证据：Python `test_dispatch_models.py` 78 passed（原 63 + 15）；TS `agent-team-loop.test.ts -t fallback` 7 passed（原 5 + 2）；biome/tsgo 待本轮复跑。

### 遗留（更新）

- 上表全部修复项已完成。
- 继承风险（非本 key 阻断，两次复核均已列）：`_model_write` 无锁多读 + 非原子 `write_text` 的并发/IO 失败窗口；show 以外的写面同理。

## R-02 复评与收口（2026-10-15）

已派 `review-fallback-cli-r2`（卡：`tasks/R-02-reverify-fixes.md`；报告已由 PM 归档：`evidence/review-fallback-cli-r2-20261015.md`，15KB）。

- **判定：⚠️ 有条件通过（5✅/1⚠️/0❌）**，明确回答：**F1/F2/F3 三项静态复评全部闭合**，D4 已解除。
- 剩余 ⚠️（Q3）= 断言欠债 4 条，**已全部补齐**：
  1. `clear-fallback` 未知任务类型拒绝用例（`main` 是 role 不是任务类型）——新增（现在 79 passed）。
  2. 旧参数拒绝用例（`*_cli` 前缀 / 未知前缀 / 未知 task type / 空值）从「只断言 rc」改为**逐字节不变** oracle（模块级 `_write_dispatch_bytes` + `_CONFIG_WITH_FOREIGN_KEYS` 夹具，含注释/外来键/其它链）。
  3. noop 现在同时断言**不创建 `.mw` 目录**（不只是文件不存在）。
  4. 本节记录 TS 全文计数：full `agent-team-loop.test.ts` = **201 passed / 1 failed**（唯一失败为已登记基线 `T-17/B-1 anchor integrity`：`.agenticdoc/mw-guard-form-hardening/design.md → worker/worker-mode.ts:747` 行漂移，与本 key 无关）；`-t fallback` = 7 passed。
- 报告归档说明：worker 写面只允许其 `report.md`，故 PM 将 `workers/review-fallback-cli-r2/report.md` 复制到 `evidence/review-fallback-cli-r2-20261015.md`（内容一致，PM 归档动作本身即证据）。

### 最终证据快照

| 面 | 结果 |
| --- | --- |
| `test_dispatch_models.py` | **79 passed**（原 63） |
| `test_mep_fallback_config.py` | 41 passed（与 `test_dispatch_models.py` 同跑：119 passed） |
| `agent-team-loop.test.ts` full | 201 passed / 1 已登记基线失败 |
| `-t fallback` | 7 passed |
| biome（本 key 触动的 3 个 TS 文件） | No fixes applied |
| `tsgo --noEmit` | 无输出（通过） |
| 实机 | `mw model show --project .` → `fallback review: timi/deepseek-v4.1-flash`；`mw doctor` → `dispatch_fallback: review=timi/deepseek-v4.1-flash` |

### 收口声明

本 key 为 mini 快速路径（同 `mw-review-schema-lookaround` 先例：无 plan/tasks 阶段机，记录即本 mini-spec + spec.md + 两份独立复核报告）。两轮独立复核（R-01 ❌ → 修复 → R-02 ✅ 修复项全闭合）已完成，无未闭合 ❌，无阻塞性欠债。

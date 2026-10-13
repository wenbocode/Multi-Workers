# Design 阶段选型证据（mw-dispatch-card-gate）

- 日期：2026-10-12｜支撑 `design.md` 的架构选型；每条给出候选、裁定、依据出处。
- 上游证据：`evidence/research/spec-{dispatch-path,card-format-corpus,dispatch-input-format,gate-layer}-20261012.md`

## DQ-1 门禁落层：工具层 / 服务层 / 校验器

- 候选：① 仅工具层；② 仅服务层；③ 仅独立校验器；④ 工具层主 + 服务层兜底。
- **裁定：④**。
- 依据：入队生产者有 **4 个** —— `dispatch_worker`（`pm/ui-bridge.ts:1814/2026`）、`/worker`（`:2355/2502`）、conductor 直写（`packages/multi-workers/autopilot/dispatch.py::dispatch`）、手写队列行；**工具层只得前 2 个**，只有服务层（`packages/multi-workers/launcher.py:872 _poll_once`）全覆盖；校验器**不拦任何一次派发**（不满足 G1）。出处：`spec-gate-layer-20261012.md` §1–§2。

## DQ-2 判据宽严：严格标题档 vs 宽档语义档

- 候选：① 严格三段标题；② 标题命中或段落语义命中。
- **裁定：②（宽档）**。
- 依据：严格档会误拒 **87.2%** 卡片（`spec-card-format-corpus-20261012.md`）与 **99.4%** 派发卡（`spec-dispatch-input-format-20261012.md`）；"过拦同样违约"（`spec.md` §8 P-03）。宽档 + **新派发强制 + 历史豁免**。

## DQ-3 合规保证位置：事后校验 vs 生成端构造

- 候选：① 仅事后校验；② 生成端构造 + 事后兜底。
- **裁定：②**。
- 依据：派发正文 = PM `description` **原文**（`pm/ui-bridge.ts:1780 writeDispatchTaskMd` → `:1806`），正文完全由单写点机器拼装；`:1745 applyWriteSurfaceContract` 已有**幂等段注入**机制可复用 ⇒ 生成端可保证 100% 齐备（零误拒）；手写/手改旁路由服务层兜底。出处：`spec-dispatch-input-format-20261012.md` §③④。

## DQ-4 上下文投递形态：全文注入 vs 种子 + 自由探索

- 候选：① 注入全部相关文档；② 种子 + 允许 worker 启发式探索。
- **裁定：②**。
- 依据：用户裁定（`pm-state.md` D-002：投递优先、不设探索限制）；现有语义支持"跨 key 读允许、写拒绝"（`worker-crosskey-readonly`）；隔离约束要求不主动注入其他 key 私有内容，但**不禁止** worker 自行只读检索。可审计性由「上下文来源清单」保证。

## DQ-5 回收契约形态：沿用现状 vs 段落 + 状态双判据

- 候选：① 沿用 `output.md` 现状（无成文契约）；② 五段必备 + `_workers.parallel` 状态判据。
- **裁定：②**。
- 依据：实测 4 个 worker 中 **3 个**内容齐全却因 `output.md` 占位段被判 `needs-clarification`（本会话工人回读记录）；`worker/output-sections.ts` 分段器可复用；迁移期须避免历史派发一次性判红（P-09）。

## DQ-6 追溯与一致性机件：自造 vs 复用

- **裁定：复用**。
- 依据：卡 hash 用 `mw_common.sha256_eol_normalized`（EOL 归一，避免跨语言 CRLF 误报，上一 key 已用于语料对拍）；卡片集合 ⊇ 派发集合的差集抄 `packages/multi-workers/autopilot/conductor.py:2417/2433`；跨语言成对实现沿用 `shared/index-store.ts:67 keyNameRefusal` ↔ `packages/multi-workers/update_index.py:118 key_name_refusal` 的 golden+parity 范式。

## DQ-7 逃生舱：只写不读 vs 真读 + 审计

- **裁定：真读 + 审计**。
- 依据：现状 `allow_foreign_write: true` **只写不读**（TS/Python 均无消费者，`spec-dispatch-path-20261012.md` 假设点清单）⇒ 例外机制形同虚设；本 key AC-007 要求可检索到读取点 + 审计行。

## DQ-8 类型工具集：沿用现状 vs 修正

- **裁定：修正 `review` 加 bash**。
- 依据：上一 key 实测 —— `type=review` 角色**无 bash**，导致质量门只能静态推演、无法执行验证，事后返工重派；`review` 的职责是启发式发现问题，必须能跑验证命令。`spec.md` AC-005 与 §8 P-08（`type:` 词汇表工具 5 值 vs 运行时 10 值不一致）同步收口。

# 回归记录：ai-baseline-repair T-01~T-04 验证链（2026-09-10）

> Key: ai-baseline-repair
> 范围：T-01（src+单点类型修）/ T-02（model ID 重定向，含根修转向）/ T-03（cross-api 8 处）/ T-04（验证链+预防文档）

## 1. 验证链结果（全绿）

| 验证 | 命令 | 结果 |
|---|---|---|
| VC-001 tsgo | `npx tsgo --noEmit` | exit 0，0 错误（基线 26） |
| VC-002 check 全链 | `npm run check` | exit 0（biome/pinned-deps/ts-imports/shrinkwrap/install-lock/tsgo/browser-smoke 全过） |
| VC-003 ai 套件 | 包根 `vitest --run` | 838 passed / 825 skipped / 0 failed（基线 7~8 failed） |
| 扩展域回归 | coding-agent `vitest --run test/extensions/` | 123/123（含另一在飞会话的 +2 测试，非本 key 改动） |
| Python 域回归 | multi-workers `pytest -q` | 367 passed / 8 deselected / 0 failed（含 goal-autopilot 未跟踪测试） |
| VC-009 biome | check 链内 | 触碰文件零告警（曾 5 个未用 import，已清） |

## 2. 执行中的方案转向（比 design 更优的根修）

1. **T-02 初版**（gateway+kimi 块删除 + empty-tools fixture 覆写）在 ai 套件暴露 3 个新失败：compat 层 `getBuiltinProviderForModel` 以**静态目录**判定 provider+api 组合，gateway 目录无 openai-completions 模型时走裸 API → env 占位符不解析。
2. **根修**（镜像 upstream generator）：`generate-models.ts` 在 gateway 目录循环后**把 cloudflare-workers-ai 目录镜像进 gateway**（`workers-ai/*` 前缀 id + `/compat` baseUrl + session affinity compat，带去重集合）——models.dev 增删 workers-ai 条目不再影响 gateway。再生成后 gateway json 恢复 18 个 workers-ai 条目（含 kimi-k2.6）。
3. **测试面回滚**：T-02 初版的 6 处删块 + empty-tools fixture 全部还原（原始 `getModel("cloudflare-ai-gateway", "workers-ai/...")` 调用重新合法且运行正确），仅保留 M1/M2 换 ID（5 处）。
4. 镜像过程中 stream.test.ts 曾因闭括号深度误判多删 118 行，已即时发现并 `git checkout --` 单文件还原后手工精修（最终 diff 29 行符合预期）。

## 3. 运行时失败处置（基线 7 failed → 0）

| 失败 | 处置 | 依据 |
|---|---|---|
| baseten GLM-5.2 全量元数据断言 | 镜像上游替换版（仅断言两端点 input），并按**我们目录现状**适配为 `["text","image"]`（上游 09-03 时 models.dev 为 text-only，今日已变 multimodal） | upstream 3316c4e35 + 本地 json 实况 |
| fireworks Fire Pass turbo router | 镜像上游**删除**该测试（模型已离开目录；上游 09-10 同样删除） | upstream bbb61e34a |
| github-copilot-oauth filters gpt-4.1 | mock id 与期望从 `gpt-4.1`（已不在目录）换 `gpt-5-mini`（在目录）；上游整文件重写为动态取 catalog id，镜像面过大不做，此为最小等价 | 上游重写方向一致（不硬编码易逝 id） |
| tool-choice opencode maxTokensField | 第二 case `grok-build-0.1`（compat 无 maxTokensField）→ 镜像上游换 `kimi-k2.6`（有） | upstream 现版 |
| timi-models 15≠14 | 目录新增 `glm-5.3`，测试期望表补该条目（元数据同 glm-5.2 形状） | 本地 timi.json 实况 |
| empty-tools ×2（T-02 初版引入） | 随根修自愈（目录门禁恢复） | §2 |

## 4. 最终变更面（17 文件，含 2 文档）

- `scripts/generate-models.ts`（+37：镜像块 + 去重集合）
- `src/providers/cloudflare-ai-gateway.ts`（D-001：显式 `createProvider<CloudflareAIGatewayApi>` + 上游注释）
- `src/image-models.generated.ts`（再生成附带漂移，AGENTS.md 允许）
- test 11 文件（M1/M2 换 ID 5 处、cross-api 8 处、TS1294、compat 窄化、运行时断言对齐）
- `README.md`（Model Catalog and Test Hygiene 节，AC-008）+ `CHANGELOG.md`（Unreleased Fixed 3 条）

## 5. 上游镜像跳过清单（留档）

- qwen-token-plan-individual 新增块 ×6（abort/tokens/empty/total-tokens/unicode/context-overflow）：provider 不在本 tree generator 输出，属 54 文件 src 分歧，超 GC-A4
- github-copilot-oauth 整文件重写（动态 id 基建）：以 gpt-5-mini 最小对齐替代
- empty-tools 注释 URL 修正（issues/3649）：纯注释，未取

## 6. 其他会话在飞工作（不碰）

pm-orchestrator.ts（+32）/ agent-team-loop.test.ts（+41）/ mw.py（+43，`_rebuild_pi_dist`）/ test_mw_build.py（新）= goal-autopilot 会话资产；本 key 的回归数字已含其改动，未提交不动。

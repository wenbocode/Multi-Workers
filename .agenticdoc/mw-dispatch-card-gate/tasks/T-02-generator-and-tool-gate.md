# T-02 生成端注入 + 工具层校验

- Key: mw-dispatch-card-gate｜Wave: 2｜依赖: T-01（接口见 `plan.md` 冻结接口）｜type: coding

## 上下文
`dispatch_worker` 参数面没有卡片路径，投递物正文 = description 原文（`pm/ui-bridge.ts:1780 writeDispatchTaskMd` → `:1806`）；生成端可保证齐备，因为正文完全由该写点机器拼装，且 `:1745 applyWriteSurfaceContract` 已有幂等段注入（`evidence/research/spec-dispatch-input-format-20261012.md` ④）。依据 `design.md` §1/§4。

## 要求
1. 在 `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`：
   - `dispatch_worker` 增加**必填**参数 `card_path`（相对仓库根或绝对路径）；`/worker` 同（调用点 `:1959`、`:2445`）。
   - 二者调用 `shared/dispatch-card.ts` 的 `readEnvelope`；`ok=false` ⇒ **拒绝派发**，返回文本须**指名缺失项与卡路径**（`missing=[...]`）。
   - `writeDispatchTaskMd`（`:1780`）注入固定段：`## 上下文` / `## 要求` / `## 交付格式`（内容取自卡），并追加一行声明："以上为种子，不是探索上界；可自行检索补充上下文"；注入须**幂等**（重复派发不重复追加）。
2. 保持既有行为不变的部分：frontmatter 字段（`type:`/`phase:`/`model:`/`write_scope:` 等）与幂等 marker 逻辑不动。
3. 追溯落盘（对接 T-06 已落地的 `packages/multi-workers/autopilot/card_audit.py`）：在与 `type:` 相同的**头部区**写入**裸行** `card_path:` 与 `card_sha256:`（头部区 = 首个 H2 之前的卡前区；**不得用 `---` 围栏** —— 实测真实卡 0/345 有 fenced `type:`，PM 活写法是 `｜type: coding` / `| type: coding`；此规则与 T-01 `inspectEnvelope` 的头部区判定、T-06 `card_audit` 的读取规则三者一致）；`card_path` 用归一形式 `tasks/<name>.md`（正文提及不算引用）；`card_sha256` 用**新增叶子模块** `packages/coding-agent/src/extensions/agent-team-loop/shared/card-digest.ts`（仅 import `node:crypto`/`node:fs`）实现 **EOL 归一 sha256**，必须与 `packages/multi-workers/mw_common.py` 的 `sha256_eol_normalized` 语义一致。
4. 新增测试 `packages/coding-agent/test/suite/dispatch-card-injection.test.ts`：合法卡 ⇒ 派发成功且 `task.md` 三段齐备（**字节级断言**）；无 `card_path`/卡不存在/缺段 ⇒ 拒绝且不进队列（断言存储零新增）；另加**跨语言摘要 parity** 用例：对同一卡，TS `card-digest` 与 Python `sha256_eol_normalized` 结果逐字节相等（golden + 双实现），并覆盖 CRLF/LF 等价与等长篡改摘要变化。

## 交付格式
- 写入允许面：`pm/ui-bridge.ts`、`shared/card-digest.ts`（新）、`test/suite/dispatch-card-injection.test.ts`。
- 写入禁止面：`shared/dispatch-card.ts`（T-01 归属）、`worker/**`、`packages/multi-workers/**`、其他 key 目录。
- 回收判据：验收命令 `node ../../node_modules/vitest/dist/cli.js --run test/suite/dispatch-card-injection.test.ts`（在 `packages/coding-agent` 下）全绿；另跑 `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts` 不得回归；报告含改动清单（含 `dispatch_worker` 调用点 55 处引用的适配说明）。

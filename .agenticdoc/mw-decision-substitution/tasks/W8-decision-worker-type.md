- type: coding
- key: mw-decision-substitution
- 目标锚点: `.agenticdoc/goal.md`（jev 替换中低风险决策，PM 并行管理 worker）；本卡把「写决策本」固化成一个可派发的 worker 类型，让决策不再靠 PM 临场推理
- 上游: `spec.md` §14 AC-018/AC-019/AC-021/AC-022、`design.md` §8 D-055..D-060、`packages/multi-workers/decision_book.py`（`scaffold_book`/`check_book`）、`packages/multi-workers/decide_registry.json`

## 上下文

决策本三件套已落地：`mw decide book new <dp>` 从 `decide_registry.json` 生成骨架（键与顺序 == `required_state_fields`，值为类型占位符，
`notes.evidence` 同名待填，`context` 只留该 dp 的槽位），`mw decide book check <file>` 用七类失败码判缺/类型错/多余键/占位符/证据不可达/
超预算/凭据，`decide run/ask --book` 先验后发。真实 dp3 骨架形态见 `workers/ds-w7-decision-book/report.md` 与 `decide_book_template.json`。
现在缺的是**角色**：这类任务（读配置 → 收集证据 → 填本 → 过检 → 交回判定）由谁来干、允许写什么、验收什么。

决策本实现锚点：`packages/multi-workers/decision_book.py:105`（CONTEXT_SLOT_LIMITS）、`packages/multi-workers/decision_book.py:248`（scaffold_book 槽位选择）、`packages/multi-workers/mw_common.py:341`（FALLBACK_TASK_TYPES 派生处）、`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:4993`（dp3 state 构造所在段）。

worker 类型词表在 `packages/multi-workers/mw_common.py`（`TASK_TYPE_TO_ROLE`，`FALLBACK_TASK_TYPES` 由它派生）；
派发角色校验在 `packages/multi-workers/autopilot/dispatch.py`；worker 侧类型→提示词/工具映射在
`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（`type:` 分支与工具白名单）。

## 要求

1) 词表加 `decision` 类型：`mw_common.TASK_TYPE_TO_ROLE["decision"] = "decision"`（`FALLBACK_TASK_TYPES` 自动跟随），
   `dispatch.py` 的角色校验放行；`.mw/dispatch.yml` 里 `roles.decision` 缺省沿用 `coding` 的角色配置（写进 README 说明怎么改）。
2) worker 侧：`worker-mode.ts` 为 `decision` 类型提供固定提示词（"你写决策本，不改代码：先 `mw decide book new <dp> --out <key>/evidence/books/<dp>-<slug>.json`，
   按每个字段的 description 从证据里填值，`notes.evidence` 每条给 `path:line` 或命令原文，最后 `mw decide book check`，失败就继续填，不要改阈值/不要填预期答案"）
   与工具白名单：read/find/grep/ls/bash（bash 只允许 `mw decide book check`、`git diff --stat`、`rg`、`cat` 类只读命令）；
   `ask_decision` 工具保持可用。
3) 写入面守卫：`decision` 类型的 worker **只能写** `<key>/evidence/books/**`（卡片仍用 `## 写入允许面` 声明，但类型默认值必须收窄到该目录；
   卡片声明更宽的面时以卡片为准，并在 task.md 记一条 `narrowed_by` 说明）。
4) 卡片必需项（缺任一 → 派发拒绝，与现有 envelope 校验同一处实现）：`- dp:`、`- 证据来源:`、`- 分支后果:`、`- allow-send:`（yes|no，缺省 no）。
   `allow-send: no` 时 worker 不得调用 `decide run/ask --book`（只有 `book check`），发送由 PM 做。
5) 只有定义了 `required_state_fields` 的 dp（今天 dp1/dp2/dp3）可派 `decision` 类型；其余 dp 派发时 exit 2 并说明"先给该 dp 定义必填字段"。
6) 文档：`packages/multi-workers/README.md` 新增「派 decision worker 写决策本」一节（何时派、卡片怎么写、验收看什么）；
   `docs/decision-points.md` §9 末尾加一段指向该类型。CHANGELOG 加一条。
7) 测试：`test_dispatch_decision_type.py`（新建，≥14 例：词表包含且派生正确、角色校验放行/拒绝、卡片缺 `- dp:`/`- 证据来源:`/`- 分支后果:`/`- allow-send:`
   各 exit 2、`allow-send: no` 时 `--book` 被拒、未定义必填字段的 dp 被拒、写入面收窄到 books 目录、`narrowed_by` 记录）；
   TS 侧在 `test/suite/worker-decision-type.test.ts`（新建，≥6 例）验证提示词与工具白名单、以及 bash 只读命令过滤。

## 写入允许面

- packages/multi-workers/mw_common.py
- packages/multi-workers/autopilot/dispatch.py
- packages/multi-workers/test_dispatch_decision_type.py
- packages/multi-workers/README.md
- packages/multi-workers/CHANGELOG.md
- packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts
- packages/coding-agent/test/suite/worker-decision-type.test.ts
- docs/decision-points.md

## 写入禁止面

- `packages/multi-workers/decision_book.py`、`decision_context.py`、`decision_points.py`、`decision.py`（本卡只调用，不修改校验规则）
- `.mw/decide-points.json`、`.mw/decide.json`（运行时配置；`dispatch.yml` 也不改，只在 README 说明怎么配）
- `.agenticdoc/**`（除 `workers/<task_key>/`）、`packages/ai/**`
- git 写、`npm run check`、`npm run build`、`mw build --install`、全量 pytest、真实网络（`--live`/`decide run`/`decide ask`）

## 运行约束（OOM 教训，必须遵守）

- 禁止整文件读 `mw.py`（1 万行）/`worker-mode.ts`（5 千行）：每次 read 只用 `offset`/`limit`，单次 ≤ 120 行且只围绕锚点。
- 单个命令 stdout ≤ 30 行；长输出先落盘到 `workers/<task_key>/` 再读尾部。
- write-first：先落实现再跑验收；`rg` 必须带目录限定（`-g`）。
- 动手前先在 `report.md` 写一段 ≤10 行的计划。

## 验收命令

cd packages/multi-workers
python -m pytest -q test_dispatch_decision_type.py test_decision_book.py test_decide_cli.py
python mw.py dispatch check --help
cd ../coding-agent
npx tsgo --noEmit
npx vitest --run test/suite/worker-decision-type.test.ts test/suite/dp3-answer.test.ts

## 交付格式

`report.md` 五节：结论（每条验收命令 stdout 原文 ≤30 行）/ 证据（文件:行）/ 残留与未验证 / 上下文来源（goal.md mtime + 读过的 `path:line`）/ 改动清单。禁止只写"已验证"。

## 改动历史

- 2026-10-21 创建（PM，用户提议把「写决策本」这一类任务固化成 worker 类型；基于 W7 真实 `book new` 输出写卡）

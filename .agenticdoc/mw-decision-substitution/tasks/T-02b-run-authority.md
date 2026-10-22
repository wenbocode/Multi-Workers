# T-02b `mw decide run` 走 decide_for（answer 意图）

- key: mw-decision-substitution · type: coding
- 依据：T-05 残留 2 —— `mw decide run`（`mw.py:835-855`）直调 `DecisionClient`，**不做授权判定、无 `mode/acted/decision_id`、不落档案**；TS 侧只能自己镜像配置表推导 `mode/acted`，形成第二套权威。

## 上下文

`decision_points.decide_for` 是 design §2.3 定义的唯一入口（授权 → 输入闸 → 传输 → 答案校验 → 档案）。但 CLI 的 `decide run` 绕过了它，于是：

- AC-001（配置关闭时零 spawn 且零档案写）在 **CLI 路径上不成立**；
- AC-011（每次决策落一行档案）在 CLI 路径上不成立；
- TS（`decision-tool.ts`）不得不重复实现"读配置判 enabled/mode"，两处一旦漂移就是静默错配。

## 要求

1. `decision_points.decide_for` 增加 `intent: str = "act"` 参数，取值 `"act" | "answer"`：
   - `"answer"`：跳过步 10/11（不执行 executor），但仍按步 9 落 `acted=false` 的档案行，并在 `DecisionOutcome` 上带 `answers`/`confidence_source`/`latency_ms`/`state_digest`/`decision_id`/`mode`/`escalated_reason`；
   - `"act"`：现有行为逐字节不变（已有 62 条测试必须全绿）。
2. `mw.py:_decide_run` 改为走 `decide_for(..., intent="answer")`：
   - 输出 JSON = **旧键全部保留**（`available`/`answers`/`reason`/`confidence*`/`latency_ms` 等，供 `triage-client.ts` 解析）+ 新增键 `decision_id`/`mode`/`acted`/`escalated_reason`/`state_digest`；
   - `escalated` 时 `available=false` 且 `reason` 取映射后的旧词表值（`disabled` → `reason="disabled"`），保证 TS 侧 `unavailable` 分支仍能解析；
   - 未知 dp → exit 2（沿用 `DecisionInputError`）。
3. 关闭态硬约束：`enabled=false` 时**零 spawn、零档案写、零 encode**，且 `decisions.jsonl` 不存在（新增用例断言）。
4. 新增 `test_decide_run_authority.py`：
   - 关闭态：`dp3` off → `available=false, escalated_reason=disabled`，档案文件不存在，`FakeBackend.calls == 0`；
   - 开启态：`dp3` on + `mode=auto` → `mode=="auto"`, `acted is False`, 档案恰好 1 行且 `decision_id` 形如 `dp3-...:<trigger>`；
   - legacy 兼容：带 `questions` 的旧请求仍返回旧键集合（逐键断言，新增键不删旧键）；
   - `mode=suggest` → `acted=false` 且档案行 `mode=suggest`。
5. 不改 `decision.py`；不改 TS。

## 写入允许面

- `packages/multi-workers/decision_points.py`
- `packages/multi-workers/mw.py`（仅 `_decide_run` 及紧邻辅助函数）
- `packages/multi-workers/test_decide_run_authority.py`（新建）
- `packages/multi-workers/test_decision_points.py`（仅补 `intent="answer"` 断言）

## 写入禁止面

- `decision.py` / `decide_archive.py` / TS 侧 / 其它 key 目录
- 禁止 `git add/commit/checkout/stash/clean`、禁止 `npm run build`
- `mw.py` 只做定点 edit（其它会话可能在同文件其它区段改动）

## 验收命令

```bash
cd packages/multi-workers && python -m pytest test_decide_run_authority.py test_decision_points.py test_decide_dp_cli.py test_decide_archive.py -q
```

期望：全绿且不少于 118 + 新增用例数。

## 种子

- goal 锚点：`.agenticdoc/goal.md`（唯配置论 / 单一权威）
- `packages/multi-workers/mw.py:835`（`_decide_run` 现状，绕过 decide_for）
- `packages/multi-workers/decision_points.py:1372`（`decide_for` 11 步）
- `packages/multi-workers/decision_points.py:1402`（步 9/10 分界）

## 交付格式

- 四段：结论 / 证据（pytest 尾行 + 关闭态档案不存在的证据）/ 残留与未验证 / 改动清单（`path:line`）。
- "零 spawn"必须用 `FakeBackend.calls == 0` 或 spy 断言，不接受叙述。
- 契约冲突停手写残留，禁止自行改契约。

## 改动历史

- 2026-10-20 创建（T-05 残留 2 的 PM 裁定 D-035/D-036）

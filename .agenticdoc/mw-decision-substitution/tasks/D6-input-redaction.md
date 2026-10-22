# D6 设计调研：结构化输入（≤2KB）+ 脱敏出口 + digest 跨语言一致性

- type: research
- 唯一证据文件: `.agenticdoc/mw-decision-substitution/evidence/research/design-input-redaction-20261019.md`
- goal 锚点: `.agenticdoc/goal.md`（"凭证隔离：每个 Worker 只拿到它需要的 API key"）
- 超时: 30m

## 上下文（已冻结）

spec §5.4：canonical JSON ≤2000 B；三级敏感度（L0 枚举计数 / L1 摘要脱敏 / L2 凭据、用户原话、绝对路径、代码永不外发）；唯一出口 `pm/triage-client.ts:273`；`decision.py:378-387` 的 `_redact` **当前不覆盖 state**；`state_digest = sha256(_encode_state(state))[:16]`。

关键锚点：`packages/multi-workers/decision.py:402-417`（`_encode_state`/`_serialize_state`，`sort_keys`）、`:244`（`max_state_bytes=16384`）、`:378-387`（`_redact`）、`:780-781`（answers 校验）、`mw.py:716-719`；`pm/triage-client.ts:44`（`MAX_TRIAGE_STATE_BYTES`）、`:216`、`:273`（唯一出口）、`:327`/`:340`（回执格式）；证据文件 `.agenticdoc/mw-decision-substitution/evidence/research/spec-structured-input-contract-20261016.md`（RQ-4 已给出的 schema 草案与 8 条脱敏规则，直接引用不要重做）。

## 要求（逐条回答，每条带 path:line）

- **RQ-1 ≤2KB schema 落地**：把 RQ-4 草案变成可实现的字段表（字段名 / 类型 / 必填 / 敏感级 / 体积预算）；给出一个填充到 2000B 上限的示例 JSON 与字节数；超限时的截断策略（按字段优先级丢 L1，绝不丢必需字段）与超限留痕。
- **RQ-2 digest 跨语言一致**：TS 与 Python 两侧算同一个 `state_digest` 的可行方案（谁 canonical 化？能否只在 Python 侧算并把 digest 回传？）。若只能各算一次，给出两侧等价的序列化参数（`sort_keys`、`separators`、`ensure_ascii`、数字格式）与一个可复现的测试向量（输入 JSON → 期望 hex），必须能在两侧都验证。
- **RQ-3 唯一出口改造**：`triage-client.ts:273` 前后的具体改动（在哪一步做 L2 剥离、脱敏后重新序列化、体积检查、失败上抛）；`mode=suggest` 与 `auto` 是否用同一份输入（应相同，说明理由）。
- **RQ-4 L2 字段负向测试**：列出必须用测试证明"不外发"的字段类别（API key/token、绝对路径 `H:\...`、用户原话引号段、源码片段、git remote/凭据），每类给一个构造输入与断言方式；说明测试放在 TS 侧还是 Python 侧（哪侧能观测到真正的出站字节）。
- **RQ-5 输入不足路径**：必需字段缺失时 TS 侧拒发的实现（`input-incomplete`），与 Python 侧 `DecisionInputError` exit 2 的分工；拒发是否留痕（留什么、写哪）；如何避免"字段缺失 → 静默变成空字符串"。逐项列出 dp3/dp2/dp1 各自的必需字段集合。
- **RQ-6 兼容与零扰动**：旧调用（`state` 为字符串）如何保持路径不变（`isinstance(state, str)`）；`max_state_bytes=16384` 与新 2000B 的关系（哪个生效、旧路径是否仍允许 16KB）；未配置 jev 的项目 doctor 输出逐字节不变的验证方法。

## 写入允许面

- `.agenticdoc/mw-decision-substitution/evidence/research/design-input-redaction-20261019.md`

## 写入禁止面

- 任何源码（`packages/**`）、配置（`.mw/**`）、其它 key 目录、其它 evidence 文件
- 禁止 `git add` / `git commit` / `git checkout` / `git stash`

## 交付格式

- 只写唯一证据文件；`## Q1..Q6` + `Q-answered: 6/6`；结论带 `path:line`；未确认写"未验证"。
- 不修改源码/配置；不做 git 操作。

## 验收命令

```
grep -c '^## Q' .agenticdoc/mw-decision-substitution/evidence/research/design-input-redaction-20261019.md
```
期望 6。

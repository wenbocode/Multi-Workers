# T-04 `triage-client.ts` 改造：dpId 入参 / ≤2KB / input-incomplete / digest 回传

- key: mw-decision-substitution · type: coding · phase TASKS
- timeout: 40
- 依据: spec.md rev3（AC-005/013）+ design.md D-004、D-019、D-021 + plan.md §1

## 上下文

- 现有实现：`pm/triage-client.ts`（`MAX_TRIAGE_STATE_BYTES:44`、`DP1_ID:47`、`DP1_QUESTIONS:55-58`、`readDecidePolicy:132`、spawn args `:169`、唯一出口 `:273`、`formatTriageReceipt:327`）。
- 改造要求见 design §2.6；输入字段与字节预算见 `evidence/research/design-input-redaction-20261019.md` Q1（dp1 实测 706B）。
- digest 由 Python 计算并随响应回传，TS **不做哈希**。

## 要求

1. 入参改为 `(dpId: string, state: object)`；删除 `DP1_QUESTIONS` 字面量，改为只持 `dp` id 常量（问题集权威在 Python）。
2. 保留 20s 硬超时与"异常→`available=false`"归一化；新增 `input-incomplete` 路径：必需字段缺失时**零 spawn** 返回并标记需要上抛人。
3. 体积检查：canonical 序列化 > 2000B 时按两段式截断（丢可选 L1 → 必需 L1 减半 → 拒发）。
4. 唯一出口 `:273` 保持**纯序列化**，不做脱敏（L2 靠构造签名无入口，见 design D-019）；digest 从 Python 响应读取。
5. 新建 `test/suite/triage-client-state.test.ts`：dpId 透传、必需字段缺失拒发（断言未 spawn）、超限截断、digest 透传、旧字符串 state 兼容。

## 交付格式

- 实现按上列写入允许面落地；报告四段：结论 / 证据（命令 + 输出摘要）/ 残留与未验证 / 改动文件清单。
- 每处关键实现附 `path:line`；关闭态未证明前不得声称完成。
- 遇到契约不足：停手并在报告"残留"里写明，禁止自行改契约。

## 种子

- goal 锚点: `.agenticdoc/goal.md`（文件驱动的去中心化协调 / 项目级目标对齐）
- 代码锚点: `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts:44`
- 代码锚点: `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts:273`

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`
- `packages/coding-agent/test/suite/triage-client-state.test.ts`（新建）

## 写入禁止面

- 除上列文件外的一切文件（含其它包的源码、其它 key 目录、`_pitfalls.md`、`_project_log.md`）
- 禁止 `git add` / `git commit` / `git checkout` / `git stash` / `git clean`
- 禁止修改 `packages/ai/src/models.generated.ts`、禁止跑 `npm run build`、禁止跑完整 vitest 套件（用 `./test.sh` 或指定测试文件）

## 验收命令

```bash
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/triage-client-state.test.ts test/suite/triage-dispatch.test.ts
```

## 改动历史

- 2026-10-20 创建

## 后续闭环（T-02 完成后，由 PM 复核）

- `DP1_QUESTIONS` 现为 legacy-only 常量；待 `mw decide run` 能从注册表补 `questions` 后，删除该常量并同步修改 `test/suite/triage-dispatch.test.ts` 的逐字断言（该文件不在本卡写面内）。
- `escalate_to_human` 的强制留痕（D-021）接在 T-08 的 settle/回执段。

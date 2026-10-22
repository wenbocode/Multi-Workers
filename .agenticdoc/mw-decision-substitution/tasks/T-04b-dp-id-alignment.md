# T-04b dp id 词表对齐 + 漂移锁

- key: mw-decision-substitution · type: coding
- 依据：T-06 残留「契约漂移」+ PM 复核（`triage-client.ts:319-333`）

## 上下文

`pm/triage-client.ts` 的 `REQUIRED_FIELDS_BY_DP` 用**短 id** 作键：

```
dp1 / dp2-checkpoint / dp3-clarify / dp4-failure / dp5-flaky / dp6-qg / dp13-release
```

而 `packages/multi-workers/decision_points.py` 的注册表 id 是：

```
dp1-dispatch-type / dp2-checkpoint-split / dp3-worker-clarify / dp4-failure-handling /
dp5-test-triage / dp6-qg-verdict / dp13-commit-release
```

**后果**：`REQUIRED_FIELDS_BY_DP[dpId] ?? []` 对真实 dpId 恒为空 → **dp 专属必填校验整体失效**（只剩 `UNIVERSAL_REQUIRED_FIELDS`）。这正是 AC-005 要防的"输入不全就放行"。T-06 因此不得不自建一套校验，形成第三份实现。

同时：注册表 builder 产出的 state 是 `{"v": 1, "dp": <id>}`，TS 侧若按 `v === 2` 假设工作也是错的。

## 要求

1. 把 `REQUIRED_FIELDS_BY_DP` 的键全部改为**注册表 id**（7 个），值不变。
2. 确认并统一 state schema 版本为注册表的 `v: 1`（若 TS 有 `v === 2` 判断，改为 `v === 1`；若只是白名单键则补注释说明）。
3. **漂移锁测试**（关键）：在 `test/suite/triage-client-state.test.ts` 增加一例，运行时从 Python 取权威 id 列表并断言：
   ```bash
   python -c "import sys,json;sys.path.insert(0,r'packages/multi-workers');import decision_points as d;print(json.dumps([p.id for p in d.DP_REGISTRY]))"
   ```
   - `REQUIRED_FIELDS_BY_DP` 的每个键都 ∈ 该列表（防止拼错/过期）；
   - `DP1_ID` 常量 === `dp1-dispatch-type`；
   - 该测试在 Python 不可用时 fail（不要 skip），因为它是跨层契约锁。
4. 同步更新既有用例里的短 id 引用（`dp3-clarify` 等）。
5. 不新增字段、不改校验规则本身，只对齐标识与版本。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`
- `packages/coding-agent/test/suite/triage-client-state.test.ts`

## 写入禁止面

- 其它任何文件（含 `worker-mode.ts`、`pm-orchestrator.ts`、`mw.py`、Python 侧）
- 禁止 `git add/commit/checkout/stash/clean`、禁止 `npm run build`

## 验收命令

```bash
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run \
  test/suite/triage-client-state.test.ts test/suite/triage-dispatch.test.ts
```

期望：全绿，且新增用例证明 7 个键全部命中注册表。

## 种子

- goal 锚点：`.agenticdoc/goal.md`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts:319`（短 id 键表）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts:490`（`?? []` 静默兜底）
- `packages/multi-workers/decision_points.py:330`（`DP_REGISTRY`，权威 id 来源）

## 交付格式

- 四段：结论 / 证据（vitest 尾行 + 漂移锁用例名）/ 残留与未验证 / 改动清单。
- 必须给出"修复前该键查不到、修复后命中"的对照证据（可临时脚本，跑完删除）。

## 改动历史

- 2026-10-20 创建（T-06 残留 + PM 复核）

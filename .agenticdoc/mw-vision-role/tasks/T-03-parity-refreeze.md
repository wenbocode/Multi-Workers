# T-03 parity 语料重冻与两侧镜像断言

- key: mw-vision-role · 波 1 · 独占写面：`packages/multi-workers/test_autopilot_l0.py`、`test_mwpp_collection_parity.py`、`test_autopilot_dispatch.py`、`packages/coding-agent/test/extensions/agent-team-loop.test.ts`
- ac_refs: AC-004, AC-005, AC-019 · vc_refs: VC-004, VC-005, VC-019
- 依赖: T-01, T-02 · 预估: 60-90min

## 目标

把 T-01/T-02 新增的键/类型/白名单同步进测试语料，并**补齐 TS 半边的映射断言**（现状：role-map 只有 Python 侧被断言，TS 半边无 parity 锁）。

## 契约与已知触点

| 测试 | 现状 | 本卡动作 |
|---|---|---|
| `test_autopilot_l0.py:233/246` | 白名单逐元素同序断言 | 新增 `vision` 用例（同序 `["read","write","edit","bash","find","grep","ls"]`） |
| `test_mwpp_collection_parity.py:34-62` | 冻结键集/计数 | 按新增键**重冻**（只增不删；逐例 diff 后写新期望） |
| `test_autopilot_dispatch.py:32` | REGISTRY 键集 | 加 `vision` 键；补 `dispatch(task_type="vision")` 非 `not-conductor-dispatchable` 断言 |
| `agent-team-loop.test.ts:5143-5145` | `DISPATCHABLE_TYPES` 子串断言 | 末尾追加 `vision` 后应仍绿（**若红则说明插入位置错了**，回 T-02 修） |
| `agent-team-loop.test.ts` 新增 | — | 断言 `roleForTaskType("vision") === "vision"`（TS 半边 parity，必须新增，禁止空断言） |

## 步骤

1. 先跑一遍现状命令，记录红项（预期：`test_autopilot_l0` / `test_mwpp_collection_parity` / `test_autopilot_dispatch` 键集红）。
2. 逐文件更新期望：**新增**条目、不放宽既有断言、不改语义。
3. 新增 TS 半边断言 + AC-005 的跨语言 parity（可从 `test_autopilot_l0.py` 读出 TS 侧期望值比对，或 TS 侧断言白名单字面量）。
4. `[VERIFY]` 行用 `process.stdout.write`（TS）/ `print(..., flush=True)` + `-s`（Python）——`console.log` 会被 `silent:"passed-only"` 吞掉（P-006）。

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_autopilot_l0.py test_mwpp_collection_parity.py test_autopilot_dispatch.py -q -s
cd ../../packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts
```

## 证据格式

`[VERIFY] VC-005: allowlist_vision=read,write,edit,bash,find,grep,ls parity=true` ·
`[VERIFY] VC-019: conductor_dispatchable=true unknown_type_refused=true` ·
`[VERIFY] VC-004: role_for_vision=vision mirror_ok=true`

## 非空洞对照

删掉 TS 半边新增断言 ⇒ 把 `roleForTaskType("vision")` 改成返回 `"coding"` 无人发现（这正是要补的洞）；重冻时若把某个既有键删掉，计数锁定会红。

## 交付

4 个测试文件改动 + 三个 `[VERIFY]` 原始输出。重冻 diff 需在 output 中给出（证明只增不删）。

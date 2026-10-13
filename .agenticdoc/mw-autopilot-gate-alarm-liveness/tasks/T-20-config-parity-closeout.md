# T-20 — 跨语言 config 注册表 parity 收尾（`envelope_fallback`；含 PM 未收尾改动）

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-011（跨语言一致性）/ 过程发现（上一 key 的收口遗漏）
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/workers/mwgal-t14b-monitor-blocker-class/report.md`（发现该红）；
      `packages/multi-workers/autopilot/config.py:61-65/:111-113/:151/:230-241`；`packages/coding-agent/test/suite/autopilot-config-sync.test.ts:22-28`

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（跨语言单一真相：Python 与 TS 必须读到同一份配置语义，否则自动裁决与面板会各按一套规则判断）。
- **破口来源（PM 已定位）**：`envelope_fallback` 由提交 **`b65380d1b`**（上一个 key `mw-dispatch-card-gate`）加入 Python 侧注册表 —— `config.py:112 ENVELOPE_FALLBACK_KEY = "envelope_fallback"`、`:113 _BOOL_FIELDS = ("enabled","paused","xkey_repair", ENVELOPE_FALLBACK_KEY)`，且**刻意不在 `DEFAULT_CONFIG` 内**（`:61-65` 文档串明写 "One optional key sits outside DEFAULT_CONFIG"；校验在 `:151` 用 `- {ENVELOPE_FALLBACK_KEY}` 放行；读取语义见 `:230-241 envelope_fallback_enabled`）。TS 侧镜像表未同步 ⇒ **P5 锁（`autopilot-config-sync.test.ts`，"matches the Python registries byte-for-byte: order, defaults"）自该提交起一直红**；`npm run check` 不跑测试，故收口时未被发现。
- **PM 已施加的未收尾改动（必须复核，可保留也可回退，但必须给出理由）**：
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:162` 由
    `export const BOOL_FIELDS = ["enabled", "paused", "xkey_repair"] as const;`
    改为
    `export const BOOL_FIELDS = ["enabled", "paused", "xkey_repair", "envelope_fallback"] as const;`（另加 3 行注释）。
  - 施加后**实测 2 红**：
    1. `autopilot-config-sync.test.ts > P5 > matches the Python registries byte-for-byte` ⇒ `AssertionError: expected 21 to be 20`（某处**计数**断言，实际 21 / 期望 20）；
    2. `autopilot-console.test.ts > config integer literals, mirror exports, and write lock (T-04) > AC-006/AC-012: the 20-key mirr…` ⇒ `expected ['enabled','paused',…2)] to deeply equal ['enabled','paused','xkey_repair']`（该锁字面量仍是旧的 3 项）。
  - 施加前基线：P5 红（`BOOL_FIELDS` 3 项 vs Python 4 项）、console T-04 绿。⇒ **当前净效果是 2 红，本卡必须收敛回 0 红。**
  - `npx tsgo --noEmit` 在施加后**无输出（干净）**。

## 要求

1. **以 Python 为唯一真相**：TS 侧注册表必须与 `config.py` 的 `_BOOL_FIELDS`/`DEFAULT_CONFIG`/枚举/范围表**逐项一致（顺序、默认值、键集合）**。特别地：`envelope_fallback` 必须是"**注册在 `_BOOL_FIELDS` 等价物中、但不在 `DEFAULT_CONFIG` 中**"的形态（与 Python `:61-65/:113/:151` 一致）；不得为了过测试把它塞进 `DEFAULT_CONFIG`。
2. **收敛两处红**：
   - P5 的计数断言（21 vs 20）：查明该计数在两侧各代表什么（`20-key mirror` 的定义），按 Python 真相修正 **TS 侧**（或正确修正该锁的期望），并在报告中说明"20 与 21 分别数的是什么、为何";
   - `autopilot-console.test.ts` 的 T-04 锁：若其字面量编码的是**过时的** 3 项注册表，则更新为与 Python 一致；**不得**改成"只断言前 3 项"之类的弱化形式；必须保留"镜像导出"语义。
3. **复核 PM 的 `status-model.ts:162` 改动**：确认它是否是正确形态（是否需要同时更新 `boolOf` 联合类型 `~:306`、DEFAULT_CONFIG `~:142`、读取映射 `~:339/:371`）；若需要更多改动，一并完成；若 PM 的改法是错的，**回退它并说明理由**（回退也要报告）。
4. **不得引入新 config 键**；不得改动 Python 侧语义（Python 是真相）；不得触碰 `config.py` 的既有键顺序与默认值。
5. **回归测试**：P5 与 T-04 全绿；并补一条**防再犯**断言（若可行）：TS 侧注册表与 Python 的差异检测必须覆盖"**可选键**"这一类（即：可选键必须在 `_BOOL_FIELDS` 等价物里、且必须**不在** `DEFAULT_CONFIG` 里）——若现有 P5 已覆盖，请指出覆盖点（`path:line`）并说明为何这次没拦住。
6. 报告须回答：**这类破口为何能在上一个 key 收口中存活**，以及本卡加了什么机制防止再犯。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`
- `packages/coding-agent/test/suite/autopilot-config-sync.test.ts`
- `packages/coding-agent/test/suite/autopilot-console.test.ts`
- 新增：`packages/coding-agent/test/suite/mwgal-t20-config-parity.test.ts`（若需要防再犯断言）

## 写入禁止面

- `packages/multi-workers/autopilot/config.py`（Python 是真相，零改动）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`、`shared/index-store.ts`（T-16b 正在改）
- `shared/change-ledger.ts`、`worker/output-writer.ts`（T-17c 正在改）
- `autopilot/monitor.ts`
- 其他 key 目录、其他项目仓库只读

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-config-sync.test.ts test/suite/autopilot-config-parity.test.ts test/suite/autopilot-console.test.ts test/suite/mwgal-t20-config-parity.test.ts`
另加：`npx tsgo --noEmit`（须无输出）

## 改动历史

（填写：`envelope_fallback` 的正确镜像形态、21/20 计数的真相、T-04 锁更新理由、PM 改动是保留还是回退及理由、防再犯机制。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。

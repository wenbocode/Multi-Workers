# T-25 C-31 版本恒为 0.0.0（身份行不可比）+ dotless 漏红

- Key: mw-dispatch-card-gate｜Wave: 17（本 key 最后一张实现卡）｜type: coding｜依赖: T-14/T-18/T-21（终态）+ cutover（bundle `975D4066…978D`，服务 PID 158412）

## 上下文（两项均为 cutover 后运行期实测出的硬缺陷）

**C-31 身份行版本恒为 `0.0.0`**：T-23 自己的 `task.md` 头部实测为
`envelope_producer: agent-team-loop-pm@0.0.0`（T-18 已生效：`card_path:`/`card_sha256:` 均在）。
根因已定位：`packages/coding-agent/src/config.ts:492` = `export const VERSION: string = pkg.version || "0.0.0";`，而**打包后的 bundle 拿不到 `package.json`** —— 实测在 `packages/multi-workers/dist/extensions/agent-team-loop.js` 中 **`0.83.0` 命中 0 次、`0.0.0` 命中 1 次**。
后果：T-14 的"版本偏移 vs 真缺段"判别对 **TS 派发路径实质失效**（身份行在，但版本不可比）；若服务层把 `0.0.0` 当作"比基线老"，还可能把正常 TS 派发误判为 producer-skew。

**dotless 漏红**：T-23 直接调用实测 —— 声明写入 `scripts/deploy`（无扩展名、带分隔符）被 `isPathCandidate` 判为 `malformed` ⇒ `declared=[]` ⇒ **trace 无对应事件时 `extra` 仍为 `[]`**（真实越界漏网）。T-21 的形态白名单（"带分隔符的候选 basename 必须含 `.`"）是引入该漏红的直接原因。

## 要求（逐条可验收）

1. **构建期注入版本（首选）**：让扩展 bundle **自带**版本，不依赖运行时 `pkg`。
   - 在打包路径（`mw.py build` 所用构建代码 / esbuild define 等）注入 `packages/coding-agent/package.json` 的 `version`；
   - 扩展侧取值不得再依赖运行时 `pkg.version`（否则必落 `0.0.0`）；
   - **不得**在本卡运行 `build --install`（那会动 `dist` 与全局安装面、影响正在运行的会话，属 PM cutover 步骤）。
   **验证方式**：若构建函数可输出到临时目录/可在单测内调用，则断言"产物中 `0.83.0` 命中 ≥1、且身份行不再依赖 `pkg`"；若确无干净路径，**只做单测 + 在报告中说明未构建验证**，不得 install。
2. **服务层对 `0.0.0` 的语义**：把 `0.0.0`（或等价的"无版本")按 **未知版本** 处理：
   - **不得**判为"比基线老"的 producer-skew；
   - 保留可解释性（如 notice/log 标注 `producer-version-unknown`），且**不得**借此放行真缺段（T-09/T-14 的 fail-closed 语义不变）。
3. **dotless 漏红修复**：形态门失败后加**存在性仲裁** —— 若该 token 在仓库内**真实存在**（文件/目录，`fs.existsSync` 等只读判定），则按**声明**处理（仍计入 `malformed_candidates` 计数，但不得因形态而丢声明）；不存在则维持现状。
4. **正反例必测**（TS 侧）：
   - ① `scripts/deploy` 无扩展名：**有** trace 事件 ⇒ `extra` 不含它；**无**事件 ⇒ `extra` **必须包含**它（红）；
   - ② 既有形态判据不得放松：`host/pid` 这类英文词对仍不得算声明；
   - ③ 上一轮真实语料（T-18/T-19 报告片段、本卡 `task.md` 的禁止面段）仍为 `extra=[]`；`mwds-t02` 的 AC-010 语料回放 `false_positives` 必须仍为 **0**。
5. **Python 侧用例**：`0.0.0` 生产者 ⇒ (a) 不判 producer-skew；(b) 真缺段仍拒；(c) 有新版本号的生产者仍按 semver 正常比较（回归 T-14 三分支）。
6. **回归**：TS —— `mwds-t21-write-intent-soundness`（13）、`mwds-t02-write-intent`（39，`false_positives=0`）、`change-ledger`、`dispatch-recovery-terminal`、`output-recovery-contract`、`mwds-t23-cutover-recheck`（10）；Python —— `test_mwds_t14_producer_skew.py`、`test_mwds_t13_producer_paralysis.py`、`test_launcher.py`、`test_mwds_t27_card_audit.py`；仓库根 `python -X utf8 -m pytest packages/multi-workers -q` 失败数 == **2**（既有基线）。

## 种子（seed）
- **目标锚点**：`.agenticdoc/goal.md`（「Key Constraints」段：*不修改 pi 核心，所有功能通过 Extension API 实现*、*文件锁并发控制* —— 本卡只改构建注入与服务层语义，不碰 pi 核心）。
- **锚点**（符号名定位；行号为 cutover 后基线，漂移以符号名为准）：
  - `packages/coding-agent/src/config.ts:492`（`VERSION = pkg.version || "0.0.0"` —— C-31 根因）
  - `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:1965`（`DISPATCH_PRODUCER_ID`）、`:1990`（身份行写点）
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts:198`（`isPathCandidate` —— dotless 修点）、`:431`（`collectMalformedCandidates`）
  - `packages/multi-workers/launcher.py`（符号 `_ENVELOPE_PRODUCER_LINE_RE`、producer-skew 判定与基线 semver 读取点）
  - `packages/multi-workers/autopilot/dispatch.py:276`（`PRODUCER_IDENTITY_KEY` —— 身份行契约来源）

## 改动历史（依赖的上游改动）
- **T-14**：服务层三分支（合规/`producer-skew`/`envelope missing`）+ `envelope_fallback`（默认关）。本卡为其补"`0.0.0` = 未知版本"语义。
- **T-18**：`pm/ui-bridge.ts::mergeCardHeader` 写 `envelope_producer: <id>@<version>`；版本取自 `config.ts::VERSION`（**在 bundle 中恒为 `0.0.0`**）。
- **T-21**：`shared/change-ledger.ts` 否定感知 + 词元卫生（`isPathCandidate` 的白名单引入 dotless 漏红）。
- **cutover**：`build --install`（repo/global bundle 均 `975D4066…978D`），服务 PID 79536 → 158412。

## 交付格式
- 写入允许面：`packages/multi-workers/mw.py` 与其构建实现（版本注入）、`packages/multi-workers/launcher.py`（`0.0.0` 语义）、`packages/coding-agent/src/config.ts`（仅在必要时调整 `VERSION` 取值来源）、`packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts`（dotless 仲裁）、新建 `packages/coding-agent/test/suite/mwds-t25-version-and-dotless.test.ts`、新建 `packages/multi-workers/test_mwds_t25_version_semantics.py`。
- 写入禁止面：`packages/multi-workers/autopilot/dispatch.py`、`autopilot/card_audit.py`、`pm/pm-orchestrator.ts`、`pm/ui-bridge.ts`、`test/extensions/**`、`.agenticdoc/**`（除本 worker 目录 taskDir）、其它 key 目录；**禁止** `build --install`。
- 验收命令：
  - （`packages/coding-agent`）`node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t25-version-and-dotless.test.ts test/suite/mwds-t21-write-intent-soundness.test.ts test/suite/mwds-t02-write-intent.test.ts test/suite/mwds-t23-cutover-recheck.test.ts` 全绿；
  - （`packages/coding-agent`）`node ../../node_modules/vitest/dist/cli.js --run test/suite/change-ledger.test.ts test/suite/dispatch-recovery-terminal.test.ts test/suite/output-recovery-contract.test.ts` 全绿；
  - （`packages/multi-workers`）`python -X utf8 -m pytest test_mwds_t25_version_semantics.py test_mwds_t14_producer_skew.py test_mwds_t13_producer_paralysis.py test_launcher.py test_mwds_t27_card_audit.py -q` 全绿；
  - （仓库根）`python -X utf8 -m pytest packages/multi-workers -q` 失败数 == 2（既有基线）；
  - `npm run check` 退出码 0；若 biome 会改写你写面之外的文件，**先停下在报告中说明**。
- 报告须含：结论、证据（原始命令与输出；C-31 的 `0.83.0`/`0.0.0` 命中数前后对照；`0.0.0` 三态 Python 用例输出；dotless 正反例输出；未构建验证的说明）、改动清单、残留与未验证、上下文来源清单。
- 不做 cutover、不重启服务；不改 task 卡；不得弱化或删除既有断言；如认为卡有误，在报告中提出供 PM 裁定。

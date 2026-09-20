# Quality Gate Report (Independent Worker Rerun): mw-partition-parent-extended

**时间**: 2026-09-20T16:05:00+08:00
**执行者**: mwppe-quality-gate（独立质检 worker，不信任 PM 自查报告，全量独立重推导）
**对照**: evidence/quality-gate-report-2026-09-20.md（PM 自查，判 PASS）
**范围**: AC-001~006 / VC-001~009 / A~E 复验清单全项

## (1) 前置门禁

| 检查项 | 结果 | 实测依据 |
|--------|------|---------|
| spec.md 存在 AC 编号 | ✅ | 通读全文，提取集 = {AC-001..AC-006}，无多无漏 |
| design.md 存在 VC 编号 | ✅ | 通读全文，VC-001~009（§7）齐 |
| AC→VC 映射覆盖 100% | ✅ | design §8：AC-001→VC-001；AC-002→VC-002/003/004；AC-003→VC-005；AC-004→VC-006；AC-005→VC-007/008；AC-006→VC-009——6/6 AC、9/9 VC 全绑 |
| evidence-requirement.md 存在 | ✅ | 通读，每 AC/VC 行均含充分性判定 |
| ac_fingerprint 复算一致 | ✅ | git-bash 字面管道 `grep -oE 'AC-[0-9]{3}' spec.md \| sort -u \| sha1sum \| cut -c1-12` 实跑 = `6a9e7040d5d2`，与 evidence-requirement.md 记录值一致 |
| tasks 绑定非空 | ✅ | T-01[AC-001/VC-001]、T-02[AC-002~004/VC-002~006]、T-03[AC-005/VC-007,008]、T-04[AC-006/VC-009] 全非空 |
| evidence/baseline/ | ⚠️ 缺（同 PM 判定） | design §6 全 VC 为 L1，无 L2 基线要求；wiring 用例经真实 workerModeActivate 路径——非欠债 |

## (2) A~E 逐项复验

### A. 复跑 — PASS

| 命令 | 结果（命令尾行实录） |
|------|---------------------|
| `python -m pytest -q`（packages/multi-workers） | `678 passed, 8 deselected in 56.63s`（0 failed） |
| `python -m pytest test_partition_dispatch.py test_mw_partition.py -q` | `78 passed in 8.29s` |
| vitest 2 文件（coding-agent） | `Test Files 2 passed (2)` / `Tests 44 passed (44)` |
| — 其中 autopilot-read-scope.test.ts | `Tests 28 passed (28)`；[VERIFY] VC-002/VC-003/VC-004+VC-006/VC-005 四行齐（--silent=false 实录） |
| — 其中 agent-team-loop-profile-injection.test.ts | `Tests 16 passed (16)`；[GOLDEN] MATCH + [VERIFY] FIX-13: partition_profile_parity=byte-identical |
| 附加（超清单要求）：目标单测 [VERIFY] 捕获 | `TestExpandReadScopePartition + test_set_missing_parent_rejected` → `[VERIFY] VC-001: expanded=[entries, control, parent], legacy=unchanged`、`[VERIFY] VC-001: dedup=pass`、`[VERIFY] VC-008: read_only_residual=0, wording=extended-writable-workspace`（5 passed）；golden parity 单跑 `[VERIFY] FIX-13: partition_profile_parity=byte-identical`（1 passed） |
| 附加（超清单要求）：其余 workerModeActivate 消费文件回归 | dual-root-worker / autopilot-protocol / cross-drive-worker / atl-output / atl-worker-tree-kill / agent-team-loop 六文件 → `Tests 188 passed \| 1 skipped (189)`，0 failed |

### B. AC↔实现逐条核对 — 全 PASS

- **AC-001 PASS**：dispatch.py `_expand_read_scope`（全函数通读）——partition 分支在 control 追加后追加 parent：顺序恰为 [原条目（partition root 锚定，原序）…, control（缺失才加）, parent（缺失才加）]，判重均为 normcase 全列表比较；parent 取 `config["parent_root"]`（`load_target_config` 经 `_tc_normalize_root` normpath+resolve 归一，`resolve()` 幂等兜底）。dual 分支（game root 锚定 + 仅 control 追加）与 single 直通分支代码行零变化（diff 仅 docstring + 新增 parent 块）。测试侧：`test_partition_anchors_at_partition_root` 断言整列表 `==`（含顺序）；新 `test_partition_parent_dedup` 覆盖 (a) parent 显式列入 (b) parent==control 两种判重；既有未改 `test_dual_single_unchanged` 锁定 dual=[game/src, control]、single 原样直通。
- **AC-002 PASS**：`parentRootFromTaskContent` 模式行门控 `^\[mw\] mode: partition[ \t]*$`（MULTILINE）+ `^Parent root[^:\n]*:` 前缀匹配——新旧两种标签均解析（VC-002 用例双形态断言）；无模式行 / mode: dual / 无 Parent root 行 → null。`applyParentRootUnion` 三不作用域逐项核对：config=undefined → undefined；scope=null（deny-only）→ **原引用返回**（`toBe` 引用同一性断言）；scope=[]（全拒）→ 原引用返回；parentRoot=null → 原引用返回。wiring 真经 `workerModeActivate` 生效：worker-mode.ts:455-458 `applyParentRootUnion(readScopeConfigFromMeta(meta), parentRootFromTaskContent(fs.readFileSync(taskPath, "utf8")))`，VC-004/005/006 用例写真实 task.md + 真实激活路径（非纯函数测试）。附加 scratch 复验（%TEMP 临时脚本，已删）：union 后 read/ls/find/grep 四工具对 parent 路径全部 allowed、scope 外 block（rule=scope）、空 scope + parent root 存在仍 block——AC-002 的"read/ls/find/grep 调用 verdict.allowed=true"四工具面独立证实（四工具共用同一 checkReadScopeCall 门）。
- **AC-003 PASS**：`git diff --numstat read-scope.ts` = `33 0`（纯新增，checkReadScopeCall 及既有函数零修改）；代码通读确认判定次序 deny-glob → scope → cap-file → cap-byte 未变；VC-005 wiring 用例（parent root 已入 scope + `**/DerivedDataCache/**`）断言 block 且 reason 含 rule=deny-glob。
- **AC-004 PASS**：`git diff --numstat worker-mode.ts` = `10 1`（imports + union wiring，tool_call 拦截块零触碰）；通读拦截器：门控集合恰为 {read, ls, find, grep}（worker-mode.ts:529-532 的四连 `!==` 早退），write/edit/bash 直接 fall-through；VC-006 wiring 用例对 parent 路径 write/edit/bash 三工具断言返回 undefined 且 output.md 无对应 rejection（`not.toContain("new.cpp")`/`not.toContain("existing.cpp")`）。
- **AC-005 PASS**：(a) mw.py 两处措辞改"extended writable workspace"（:1302 报错、:2817 argparse help，diff 核对）；grep "read-only" 全文件恰 2 处且均为无关语义（:1293 env 覆盖说明、:1824 rmtree 注释）；test_mw_partition.py capsys 断言 stderr 不含 "read-only"、含 "extended writable workspace"。(b) 标签字面量 `Parent root (extended workspace, writable):` 在 mw_common.py:2239 与 task-dispatcher.ts:135 双侧渲染一致；golden parity 用例双跑：TS 侧 `[GOLDEN] MATCH`、Py 侧 `[VERIFY] FIX-13: parity=byte-identical`——同一共享 golden 文件、双方逐字节比较。(c) golden fixture + TS 注入断言（profile-injection.test.ts:345）同步该标签。
- **AC-006 PASS**：git diff 逐 hunk 审计（11 文件全部通读 diff）——源码 6 文件：dispatch.py（docstring+parent 块）/mw.py（2 行措辞）/mw_common.py（1 行标签）/read-scope.ts（+33/-0 纯新增）/worker-mode.ts（imports+wiring）/task-dispatcher.ts（1 行标签）；测试 5 文件：test_partition_dispatch.py +29/-6 三 hunk 全部 partition 用例（:92 模板标签、:473 注入断言、:613 展开翻转+判重 case）、test_mw_partition.py +7/-1（missing-parent 用例 stderr 断言，partition CLI 用例）、autopilot-read-scope.test.ts +149/-0（纯新增 describe）、profile-injection.test.ts 1 行标签断言、golden 1 行。dual/single 既有用例零修改（触面文件内 dual/single 用例行未动；其余 dual 文件不在 git status 修改集）且全绿（Py 678 + TS 44+189）。check 见 D（本 key 面 0/0/0）。

### C. 抽查防呆（spec 断言 ↔ 测试断言逐字对照） — PASS

1. **AC-001 顺序锁定**：spec"返回值逐项等于 [相对条目…, control root, parent root]" ↔ 测试 `assert expanded == [str((partition/"src").resolve()), str((partition/"docs"/"readme.md").resolve()), str(outside), str(control.resolve()), str(parent.resolve())]`——整列表严格相等（序敏感、逐项相等），且旧红线断言 `str(parent.resolve()) not in expanded` 在 diff 中真实删除（翻转非恒真）。
2. **AC-002 空 scope 原引用返回**：spec"存在但空（全拒形态）时允许集与现行完全一致" ↔ 测试 `expect(applyParentRootUnion(emptyScope, "P:/parent")).toBe(emptyScope)`（toBe = 引用同一性，"完全一致"最强形态）+ scratch 运行时复核（空 scope + parent root 仍 block，rule=scope）。
3. **AC-005 标签字面量**：spec"标签为 `Parent root (extended workspace, writable):`" ↔ 7 处字面断言/渲染（mw_common.py:2239、task-dispatcher.ts:135、golden:6、test_partition_dispatch.py:92/:473、profile-injection.test.ts:345、autopilot-read-scope.test.ts:690）+ 双侧对同一 golden 整块逐字节比较（MATCH / byte-identical）。
4. **AC-003 deny 次序**：spec"仍被拒且 rule='deny-glob'——deny 先于 scope" ↔ 测试断言 `block=true` 且 reason 含 `rule=deny-glob`（parent root 同时在 scope 内的并 存场景）+ 代码 deny 检查位于 scope 检查之前（通读）。

### D. 环境（归属判定） — PASS（归属清晰，未触碰）

`npm run check` 实跑（命令尾行 `Command exited with code 1`）：
- biome：`Checked 1054 files in 580ms. No fixes applied.`（0 error/0 warning——含本 key 全部触面文件）
- check:pinned-deps / check:ts-imports / check:shrinkwrap / check:install-lock:coding-agent：全部通过
- `tsgo --noEmit`：**15 个错误，100% 位于 packages/ai**（1× `src/providers/kimi-coding.ts(5,36)` 缺失模块 + 14× `test/*.test.ts` 的 "kimi-coding" provider id 不在联合类型）——与任务预判的并发 session WIP（`git status -- packages/ai`：`D packages/ai/src/providers/kimi-coding.models.ts` + `M packages/ai/src/models.generated.ts`）一致
- **本 key 触达面（packages/coding-agent + packages/multi-workers）：0 error / 0 warning / 0 info**
- 未修不追：packages/ai 零触碰（硬约束遵守）

### E. bundle — PASS

`packages/multi-workers/dist/extensions/agent-team-loop.js` grep 实证：
- `parentRootFromTaskContent`（:19358）、`applyParentRootUnion`（:19365）
- wiring 编译产物（:19619-19621）：`applyParentRootUnion(readScopeConfigFromMeta(meta), parentRootFromTaskContent(fs.readFileSync(taskPath, "utf8")))`
- 新标签 `Parent root (extended workspace, writable): ${config.parentRoot}`（:13860）

bundle diff = +23/-3。其中含一个非本 key hunk：`process.on("exit")` 内 `killTrackedDetachedChildren()` 的 try/catch 包裹——经 git 考古，该源码变更**已随 commit 44f30c338 入库**，但 HEAD 中的 dist 产物未随之重建（陈旧 bundle）；本次重建使 dist 与 src 对齐，属修正而非回归（PM verify-run 环境备注亦有记载）。

## (3) 与 PM 自查报告的差异点

| # | 差异 | 判定 |
|---|------|------|
| 1 | `npm run check` tsgo 错误数：PM 记 14，本次实测 **15**（仍 100% packages/ai） | 环境漂移（并发 session WIP 演进），归属判定不变，非本 key 回归 |
| 2 | 本次新增独立证据：四工具 union 门 scratch 复验、6 个额外 workerModeActivate 消费测试文件复跑（188 passed）、git-bash 字面指纹管道实跑 | 补强，无分歧 |
| 3 | bundle 额外 hunk 归因：achieved.md 称"mw-worker-tree-kill 未提交 4 行"，实测该源码已在 commit 44f30c338 提交、是 dist 产物陈旧 | 措辞不精确，实质判断一致（非本 key 引入、重建对齐无害） |

无实质性分歧——PM 报告的全部 PASS 判定均被独立复现。

## (4) 终判

**QUALITY GATE: PASS**

残留清单：无（0 FAIL / 0 有条件通过）。唯一开口项为环境面（packages/ai 并发 WIP，归属该 session 自行收敛，非本 key 面）与 `mw serve` 待重启后 Py 侧生效（PM achieved.md 已记录为用户择机操作，非欠债）。

---
约束遵守：本 worker 除本报告外零仓内文件写入（scratch 校验脚本写于 %TEMP 且已删除）；未 commit；未重启 mw serve；未触碰 packages/ai 与 dist 之外的构建产物。

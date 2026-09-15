# Task T-17: L0 静态门禁 + 双侧注册表奇偶

## 基本信息
- Stage: 4
- 代码状态: 代码完成（test_autopilot_l0.py 5 测试；双源活解析奇偶 + AST 静态扫描 + vitest 活跑）
- 验证状态: 验证通过（5/5，含 autopilot-protocol.test.ts 10/10 活跑；证据 evidence/runs/l0-parity-2026-09-10.log；默认套件 363 passed 零警告）
- 负责 Agent: PM 窗口（直执）
- ac_refs: [AC-005, AC-021]
- vc_refs: [VC-007, VC-023]
- pattern_refs: []

## 描述
新文件 `packages/multi-workers/test_autopilot_l0.py`——L0 静态与奇偶门禁（无进程编排，纯静态 + 单元级动态）。

**① VC-007 静态扫描**：
- 扫描 conductor 源码（autopilot/*.py）：对 pm-state.md Phase 字段直写调用 = 0（正则/AST 检查写路径与 Phase 字段组合）；对 goal.md 的写调用 = 0
- 运行期部分：timeline advance 事件全带脚本 exit code（fixture timeline 验证事件 schema；全量运行期验证由 T-16/T-18 的真实时间线复核）

**② VC-023 奇偶与 fail-closed**：
- **双侧注册表奇偶**：解析 Python `dispatch.py` 注册表与 TS `worker-mode.ts` TOOL_ALLOWLISTS → 每类型工具集**精确相等**（含 verifier 显式条目；集合比较，非子集）
- **未知 type conductor 拒绝**（动态单元级）：dispatch 对未注册 type → 0 行 + type-rejected 事件
- **worker fail-closed**（动态单元级）：`origin: conductor` 且未注册 type → exit 1（复用 T-14 测试或以等价进程级断言补齐）

**③ 手动 fallback 保留断言**：非 origin 任务未知 type → fallback 全集（GC-8；确认未被误改）

## 输入
- 依赖文件: `autopilot/dispatch.py`（注册表）、`worker/worker-mode.ts`（TOOL_ALLOWLISTS）、conductor 源码族
- 依赖 Task: T-06, T-09~T-12（conductor 源）、T-14（TS 注册表）
- AC 约束:
  > AC-005: 在任何 phase 推进路径上，conductor 对 pm-state.md Phase 字段的直接写入次数为 0 且对 goal.md 的写调用次数为 0，全部推进经 advance_phase.py 完成（静态检查 conductor 代码无 Phase 直写、无 goal.md 写调用 + 调用日志留痕）
  > AC-021: 在 autopilot 派发路径上，roadmap-writer（含 write，需写 `_roadmap.md` 提案）/ L2 verifier（review 级：read/find/grep/ls）/ L3 review（review 级）/ repair（coding 级）各类型均有显式工具白名单条目；对未注册 type 的派发请求，conductor 拒绝派发（行数 0）并记录时间线，不回退全量工具集
- 设计约束:
  > D-107: 双侧表 + per-type 精确奇偶 + worker fail-closed（stale bundle 场景封闭）
  > GC-8: 手动 fallback 明文保留

## 预期产出
- `packages/multi-workers/test_autopilot_l0.py`
- 验证方式: `python packages/multi-workers/test_autopilot_l0.py` → `[VERIFY] VC-007: phase_direct_writes=0 goal_writes=0 advance_via_script=all` + `[VERIFY] VC-023: unknown_rows=0 registry_parity=per-type-exact verifier_entry=explicit worker_fail_closed=1`
- 验证等级: Level 0

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 21:20-21:40 | 写 test_autopilot_l0.py：①VC-007 AST 扫描（docstring 剔除后零 `- Phase:` 字串常量；写族调用段（write_text/write_bytes/replace/rename/touch/open(w|a)/shutil move|copy）零 goal.md/goal_path 令牌）+ 运行期半（双 key 同 tick，mock advance 返回 0/1，全部 advance 事件带 exit=\d+ 且两码均现）；②VC-023 奇偶（Python REGISTRY import 活取 vs worker-mode.ts TOOL_ALLOWLISTS 正则活解析，逐类型序精确相等 + TS 键集恰为并集{coding,review,research,fallback} + fallback==coding 全集）+ 未知 type 动态拒绝（0 行 + type-rejected 事件）+ worker fail-closed（worker-mode.ts 形状断言：门仅限 origin=conductor / D-107 exit(1) / GC-8 fallback 链；node 在位时活跑 T-14 套件 10/10）；③GC-8 手动 fallback 保留（fallback 桶=全 coding 集 + T-14 测试在场断言） | 5/5；vitest 复核 10/10 (721ms) |
| 2 | 2026-09-10 21:40 | 修复 pytest 警告：subprocess text=True 默认 GBK 解码 vitest UTF-8 输出 → 两个测试文件全部 subprocess.run 补 encoding="utf-8", errors="replace"；默认套件复跑 | 363 passed 零警告 |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|
| E1 | 编码 | test_autopilot_l0.py vitest 子进程 | `UnicodeDecodeError: 'gbk' codec can't decode byte 0x94`（PytestUnhandledThreadExceptionWarning）——subprocess text=True 用默认 locale 解码 UTF-8 | 已修：全即 subprocess.run 补 encoding="utf-8"（e2e 文件同步加固 roadmap_check/mw status 三处） |

### 设计取舍备注
- **TS 侧 PY_REGISTRY 是硬编码常量**（autopilot-protocol.test.ts:75）可漂移——L0 门从两侧源码活解析，双向锁死；TS 键集恰为并集断言捕获意外增删
- **docstring 剔除**：`- Phase:` 在 audit_evidence.py 的读正则（`-\s*Phase:`，非字面 `- Phase:`）与 docstring 中合法出现，扫描仅计非 docstring 字串常量
- **扫描限度（docstring 明文）**：写族段扫描捕获字面目标写与 goal_path() 令牌；变量间接无法静态完全覆盖——与 Phase 字面量禁令组合后在源码层锁定 AC-005
- **fail-closed 证据分级**：node/vitest 在位→活跑 T-14 套件（ts_run=passed）；不在位→静态形状+套件在场断言（ts_run=skipped-no-toolchain），不伪报
- **运行期半的双码覆盖**：mock advance 迭代器 (0,1)——成功与失败路径的 advance 事件 schema 均验证

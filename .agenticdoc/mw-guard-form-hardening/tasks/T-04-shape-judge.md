# T-04 — 目标集轴 `judgeWriteTarget`（形状判定取代扩展名白名单）

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**（不得改写、不得凭记忆猜测）：`design.md` §§4.3.1/§4.3.2/§4.3.3（判定顺序 + 形状要点 + 预期回归）（含 L1–L18 落点总表与 VC 定义）+ `spec.md` AC-003, AC-004 + 下列证据文件
- 证据: `evidence/research/design-target-axis-20261011.md`（判定顺序伪代码 + 形状判定表 + Windows 9 项 + deny 表 + 误报控制）
- **唯一允许改的路径**: `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`；`packages/coding-agent/test/suite/mwds-t02-write-intent.test.ts`；外加自身目录 `report.md`
- 禁止: 运行 `npm run check`/全量 vitest/`mw build`/`mw.py build`（PM 负责）；修改 `design.md`/`spec.md`/`plan.md`；改本卡未列出的文件；删既有测试用例（只能新增或按下卡明示修订）

## 卡元信息
- AC: AC-003/AC-004｜VC: VC-011…VC-019｜波 1｜链 S2（`ui-bridge.ts`）
- 验收命令（PM 执行）: `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t02-write-intent.test.ts`

## 必须实现
1. 删 `WRITE_INTENT_PATH_RE` 扩展名枚举，并删除 `collectWriteIntentHits` 里 `if (!pm || pm.index !== 0) continue;` 整条放弃分支。
2. token 发现 = verb → gap ≤32 → **行首锚定字符类**；**不得**做前向扫描（design §4.3.1 的否决理由：无界 +11 FP、保守版 +1 FP）。
3. 新增 `judgeWriteTarget`：形状识别 → deny 前缀（镜像 `worker-mode.ts` 的 6 规则）→ 允许面 realpath + 段边界（复用 `../worker/read-scope.ts` 的 `isSameOrUnder`/`normalizeForCompare`，先例 `ui-bridge.ts:44-45`）→ **无目录成分**的 basename 白名单 → 形状拒判（fail-closed）→ 非候选放行；`isWhitelistedWriteTarget` 退化为布尔包装。
4. A4 前置用 **`!hasDirComponent`**（不得用「形状 == bare」，否则 `report.md`/`output.md` 被踢出框架通道）。
5. `Makefile` 类无扩展名目标走形状层 deny-name 表（11 名）+ `existsSync`；**禁止裸 token fail-closed**（35% 假阳性）。
6. 预期回归：QG-B 5 样例 `leak_caught=5/5`（前值 0/5）、语料 `hits 2→13`、`violations=1`、`false_positives=0`。

## 交付
- 唯一写入（除源码/测试外）= `worker_file file="report.md"`、`mode="append"` 追加、`mode="write"` 覆盖；禁止其它路径。
- `report.md` 必须含：改动文件清单、前后行为对照表（输入/期望/实测）、红→绿证据、未完成项与原因（若有）。

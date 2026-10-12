# T-01 — 写面形态补全（A–F 组 + 8 条 FP 消除）

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**（不得改写、不得凭记忆猜测）：`design.md` §§4.2.2（A–F 六组表）+ §4.2.3（逐字节冻结清单）（含 L1–L18 落点总表与 VC 定义）+ `spec.md` AC-002 + 下列证据文件
- 证据: `evidence/research/design-write-guard-landing-20261011.md` §3（33 条缺失逐条：算法 + 1 正例 + 1 不得误拦反例）；`evidence/research/spec-form-inventory-20261011.md`（79 条实测表）
- **唯一允许改的路径**: `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`；`packages/coding-agent/test/suite/mwds-t03-bash-write-scope.test.ts`；外加自身目录 `report.md`
- 禁止: 运行 `npm run check`/全量 vitest/`mw build`/`mw.py build`（PM 负责）；修改 `design.md`/`spec.md`/`plan.md`；改本卡未列出的文件；删既有测试用例（只能新增或按下卡明示修订）

## 卡元信息
- AC: AC-002｜VC: VC-006…VC-010｜波 1｜链 S1（`worker-mode.ts`）
- 验收命令（PM 执行）: `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t03-bash-write-scope.test.ts`

## 必须实现
1. 按 design §4.2.2 的 A–F 六组补提取：19 包装器（含 `bash|sh|zsh|dash|ksh -c`、`cmd /c`、`powershell|pwsh -Command`、`perl|ruby -e`、`env VAR=x`、`sudo -u`/`doas`、`xargs … sh -c`、`timeout`/`setsid`、`stdbuf`/`nice`/`time`）、2 重定向（`>|`、`>&` 三态）、7 操作数（`install`/`dd of=`/`ln`/`rsync`/`tar -x`/`perl -i`/`--` 后操作数）、2 find（`-exec` 重进、`-delete`）、3 其他（`os.system`/`execSync`、`truncate -s` arity、`--` 终止符）。
2. wrapper 递解开箱：命令位跳过（flag arity 表）+ 载荷重 token 化 + `MAX_UNWRAP_DEPTH=3`；超深/不可解 ⇒ 归未知档（不得崩溃、不得当写目标）。
3. 消除 8 条 FP（`truncate -s 0 F` 的 `0`、`write_text('x')` 的 `x`、`> $(...)`/`> $VAR`、`rm *.txt`/`> *.txt`、`~/f`、`{a,b}.txt`、`> $null`）。
4. 5 类「完全隐形」形态必须有非 0 candidate。
5. **逐字节不变**：deny 6 规则、允许面判定、`matchesWriteScopeEntry`、`GLOB_MAGIC_RE`、`:960` 实参表达式、handler「首个违规即 block」。
6. 测试：每个新增形态 1 正例 + 1 不得误拦反例；FP 用例断言「不再被判为写目标」。

## 交付
- 唯一写入（除源码/测试外）= `worker_file file="report.md"`、`mode="append"` 追加、`mode="write"` 覆盖；禁止其它路径。
- `report.md` 必须含：改动文件清单、前后行为对照表（输入/期望/实测）、红→绿证据、未完成项与原因（若有）。

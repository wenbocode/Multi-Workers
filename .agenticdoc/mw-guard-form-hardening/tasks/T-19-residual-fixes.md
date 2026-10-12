# T-19 — QG-A2 四条残余修复（跨语言归一 × 2 + heredoc × 1 + tar × 1）

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**：本卡 + `design.md` §9.2（C-15…C-18）+ `workers/mwgf-qga2-code-adversarial/report.md`（含每条原始输出与攻击形态）
- **唯一允许改的路径**：
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/task-frontmatter.ts`（C-15/C-16）
  - `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（C-17/C-18）
  - `packages/multi-workers/mw_common.py`（C-15/C-16 的 Python 同语义镜像）
  - `packages/coding-agent/test/suite/task-frontmatter.test.ts`、`test/suite/mwds-t03-bash-write-scope.test.ts`、`packages/multi-workers/test_task_type_parity.py`（新增用例）
  - 自身 `report.md`
- **禁止**：改 `.agenticdoc/**` 的任何相位文档（`spec.md`/`design.md`/`plan.md`/`pm-state.md`/其他卡片——由 PM 负责）；运行全量 vitest / 全量 pytest / `npm run check` / `npm run build`；改 `pm/ui-bridge.ts`、`shared/index-store.ts`、`pm/pm-orchestrator.ts`、`pm/task-dispatcher.ts`、`autopilot/status-model.ts`、`autopilot/state.py`；git 操作

## A. C-15 / C-16：跨语言头区解析归一（AC-005 主轴）

QG-A2 实测分歧（原始输出见其报告）：
- **F-A4-1**：单独/内嵌 **CR**（`\r`）—— Python `read_text` 走通用换行而 Node 按原样 ⇒ 头区边界/首行内容分歧。
- **F-A4-2**：**U+2028** —— Python `splitlines()` 的分行集合与 `\n` 不同 ⇒ 索引空间不一致。

**要求**：在**共享头区提取器**（`shared/task-frontmatter.ts`）内把边界判定归一为**统一的 `\n` 索引空间**（`\r\n`/`\r`/U+2028/U+2029 的处理必须两侧一致），并在 `mw_common.py` 做**同语义镜像**。补 3 类 fixture（单 CR、CRLF 混用、U+2028）到两侧一致性表，**每类都要 1 正例 + 1 条「不得误判」对照**（例如含 CR 的正文行不得被当成头区键、含 U+2028 的正文不得截断头区）。断言等值（`toEqual`/逐字段相等），不得 `>0`。

## B. C-17：heredoc 体内的 `>` 不得当重定向（误拦）

实测：`cat <<EOF > f.txt ...` 之外的**heredoc 体**内出现的 `>` 被当重定向目标 ⇒ 误拦（实际不建文件）。
**要求**：识别 heredoc（`<<`/`<<-`/`<<<` 及带引号定界符）并把**体**内的 `>` 排除出重定向判定；补 1 正例（真正在 heredoc 外的 `>` 仍须拦）+ 1 反例（体内的 `>` 不得拦）。断言等值。

## C. C-18：`tar -c … -C <dir>` 的源/目标判定

实测：`tar -c … -C <dir>` 把 chdir 源当写目标（误拦）**且漏掉归档目标**（漏放）。
**要求**：`-C <dir>` 是 **chdir**（不是写入目标）；`-f <archive>` 才是写入目标；补 1 正例（`tar -czf $OUT.tar -C $D src` ⇒ 归档目标按契约判档，`-C` 目录不得成为 deny 依据）+ 1 反例（`tar -czf /etc/x.tar` 这类**字面**越面目标仍须拦）。断言等值。

## D. 纪律

- 每条给「红（改前实测失败原始输出）→ 绿（改后输出）」；不得用「应该是」代替。
- 不得回退基线：`npm run check` exit 0；TS 9 文件 **402 passed**（`mwds-t03` 42 / `worker-dispatch-guard` 20 / `agent-team-loop` 198 等）；Python **143 passed**（`test_update_index_key_refusal` 23 / `test_launcher` 100 / `test_task_type_parity` 7 / `test_update_index` 13）。改完复跑相关套件给前后计数。
- 两项机器可读门禁必须仍打印且为绿：`[FORMS] total=79 covered=79 missing=0`、`[ANCHORS] … unanchored_refs=0`。
- 新增断言必须等值；不得依赖 `task.md` 语料条目总数（语料仍在增长）。
- 若发现必须改卡外文件才能完成，**停下报告**，不要扩面。

## E. 验收命令（PM 执行）

- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run --silent=false test/suite/task-frontmatter.test.ts test/suite/mwds-t03-bash-write-scope.test.ts test/suite/worker-dispatch-guard.test.ts test/extensions/agent-team-loop.test.ts`
- `cd packages/multi-workers && python -X utf8 -m pytest test_task_type_parity.py test_launcher.py -q`

## F. 交付

`report.md`：A/B/C 三段逐条的实测命令 + 原始输出 + 红→绿 + 改动（符号/行区间）；两侧一致性 fixture 新增行数与对照结果；改前/改后套件计数；未完成项与原因。

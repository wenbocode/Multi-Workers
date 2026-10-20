# T-03: `mw stats` CLI（argparse + cmd_stats + dispatch）

type: coding
phase: execute
key: mw-usage-monitor
覆盖 AC: AC-003, AC-012
依据: `.agenticdoc/mw-usage-monitor/design.md` §3.3/§5/§6/§7；`evidence/research/spec-rq4-surface-storage-20261019.md`（§2/§4/§5/§6）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（mw 后台服务 = LLM 代理 + 任务调度器；CLI 是它的操作面）。
- 已核实起点（自行复核）：
  - `packages/multi-workers/mw.py:7009-7493` `_parse_args`：`sub = parser.add_subparsers(dest="subcommand", required=True)`（:7012）；
    `for name in ("stop","status")` 只带 `--project`（:7016-7018）；`doctor`（:7020-7035）。
  - dispatch 表 `mw.py:7503-7524`（21 项）；`sys.exit(dispatch[args.subcommand](args))`（:7526）。
  - 双输出先例：doctor `:655-661`（`--json` → `json.dumps(report, indent=2, default=str)`，否则 `format_doctor_text`）；
    update-env `:6967-6971`。定宽列先例 `:6933`。
  - 测试风格：`test_rag_cli.py:207-247`（`argparse.Namespace` 直调 `mw._cmd_rag_list`，`contextlib.redirect_stdout`）、
    `test_decide_cli.py:128-196`（直调 `mw.cmd_decide` 断言 rc）。
- 依赖：T-01 的 `packages/multi-workers/usage.py`（`build_report`/`format_report_text`/`parse_since`/`ledger_path`）。
  先读其签名；**不要改 usage.py**。
- 硬约束：TS 侧 `runMwCliRaw` 恒在 argv 尾部追加 `--project=<dir>`（`packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts:515-517`），
  故 `stats` **必须声明可选 `--project`**，否则 argparse exit 2（RQ4 §2）。

## 要求

1. 在 `("stop","status")` 循环之后（`mw.py:7018` 后、`doctor_p` 之前）新增 `stats` 子解析器，参数：
   `--since`（默认 `7d`）、`--key`、`--type`、`--model`、`--project`（可选，None=全机）、
   `--source`（choices `worker|pm`）、`--json`（store_true）。`help=` 文案随参数给出。
2. 新增 `cmd_stats(args) -> int`（与既有 `cmd_*` 同风格）：调用 `usage.build_report(...)`；
   `--json` → 打印契约 JSON（`ensure_ascii=False`, `indent=2`）；否则 `print(usage.format_report_text(report))`。
3. 错误与边界（对应 design §7）：非法 `--since` → 打印可用格式到 stderr，返回 2；台账不存在 → 仍扫描会话
   并打印 `no ledger yet`（rc 0）；窗口内无数据 → `no usage in window`（rc 0）。
4. dispatch 表加 `"stats": cmd_stats,`：**锚定插入在 `"status": cmd_status,` 之后**（当前 `mw.py:7503-7525` 的 `dispatch = {` 字典，`"decide"` 行下面是 `"target"`；不要放在 `"decide"` 附近——该行属其它会话未提交改动）。
5. 不实现 rollup、不改 usage.py/launcher/TS、不新增依赖、不改既有子命令行为。

## 写入允许面

- `packages/multi-workers/mw.py`（仅 `_parse_args` 的 stats 块、`cmd_stats` 函数、dispatch 行）
- `packages/multi-workers/test_stats_cli.py`（新建）

## 并发警告（必读）

`mw.py` 当前带有**其它会话的未提交改动**（`git diff --stat`：+360 行，含 `cmd_decide`、argparse `decide` 块
`~7442-7473`、dispatch `"decide"` 行）。因此：
- 只用**锚定插入**（`edit` 工具的小块替换 / 追加），**禁止**重写整文件、禁止格式化整文件；
- 禁止 `git checkout|restore|stash|reset`、禁止 `git add` 任何文件；
- 插入点避开 `~7442-7473` 区域（decide 的 argparse 块）：stats 的 argparse 块放在
  `for name in ("stop","status")` 循环之后（约 7018 行附近），dispatch 行放在 `"status": cmd_status,` 之后。

## 写入禁止面

- `packages/multi-workers/usage.py`、`launcher.py`、`mw_common.py`、任何 TS、CHANGELOG
- 其它 key 目录、`.mw/**`

## 验收命令

```powershell
cd H:\git\Multi-Workers\packages\multi-workers
python -m py_compile mw.py
python -m pytest test_stats_cli.py -q
python -m pytest test_rag_cli.py test_doctor_activation.py -q   # 相邻 CLI 用例零回归
```

`test_stats_cli.py` 必须覆盖：
1. `mw._parse_args(["stats"])` 与 `["stats","--project","X","--json","--since","24h","--source","pm"]` 均解析成功；
2. `cmd_stats` 文本路径（固定 fixture 台账 + fixture 会话目录，`MW_USAGE_DIR` 注入）输出与 `format_report_text` 一致；
3. `--json` 路径：`json.loads` 成功且键集 == design §5 契约（**断言无 cost/usd/amount 键**）；
4. 非法 `--since` → rc 2；不存在的台账路径 → rc 0 且 stderr/stdout 含 `no ledger yet`；
5. `dispatch["stats"] is mw.cmd_stats`。

## 改动历史

（首次改动，填写：插在哪个语句之后、为什么、被否决的替代方案。）

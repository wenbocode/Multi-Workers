# T-02 `mw review-split` 命令（coding）

- Key: claim-driven-review-orchestration
- 里程碑：M1（只读规划器）
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（文件驱动协调、服务常驻）。
- 设计依据 `design.md` §2.2：开关由 `mw` 命令持久化到 `.mw/review-split.json`，优先级
  `MW_REVIEW_SPLIT`（env）> 配置文件 > 默认 `off`。
- 既有形态参照 `.mw/decide.json` 的持有方式（`mw.py` 是唯一写者）。
- **已知坑（必须避开）**：`mw.py:10381` 的 `stats --detail --json` 在 `--json` 下仍会写 HTML 报表。
  `review-split status` 必须是**纯只读**，不得产生任何文件写入。

## 要求

在 `packages/multi-workers/mw.py` 增加子命令 `review-split`（与既有子命令同一 argparse 注册处）：

```
mw review-split status [--project .] [--json]
mw review-split set off|plan|on [--project .]
```

1. `status`：
   - 解析顺序 env `MW_REVIEW_SPLIT` → `.mw/review-split.json` → 默认 `off`，**大小写不敏感**；
   - 非法 env 值忽略并继续降级，同时在输出里标 `invalid_env`；
   - 文本输出一行：`review-split: mode=<m> source=<env|config|default> config=<path>`
     （有 `invalid_env` 时追加 ` invalid_env=<原文>`）；
   - `--json` 输出 `{"mode":...,"source":...,"config_path":...,"invalid_env":...}`；
   - **纯只读**：不建目录、不写任何文件（包括报表）。
2. `set <mode>`：
   - 写 `<project>/.mw/review-split.json`，内容 `{"v":1,"mode":"<m>","updated":"<iso8601 UTC>"}`；
   - **原子写**：写 `.mw/review-split.json.tmp` 后 `os.replace`；
   - 非法取值 → stderr 一行 + `exit 2`，**不写文件**（零副作用）；
   - 成功后打印 `review-split: mode=<m> wrote <path>`，`exit 0`。
3. `.mw/` 目录不存在时 `set` 可创建；`status` 不得创建。
4. 不复用也不改动既有 `stats`/`decide` 的任何行为。

## 交付格式

- 改 `packages/multi-workers/mw.py`（只加子命令与实现，不动其他命令）
- 新增 `packages/multi-workers/test_review_split_cli.py`，覆盖 7 条：
  默认 status、config=plan、env 覆盖 config、env 非法降级、set 后文件内容与 `v`/`mode`、
  set 非法值 exit 2 且目录内无新文件、**status 前后整个项目目录文件哈希集合不变**。
- 报告 `report.md` 四段：`## 结论` `## 证据` `## 未覆盖面声明` `## 上下文来源`。

## 写入允许面

- `packages/multi-workers/mw.py`
- `packages/multi-workers/test_review_split_cli.py`

## 写入禁止面

- 其他 `packages/**`、`.agenticdoc/**`、仓库根的 `.mw/**`（测试只许在 `tmp_path` 里造 `.mw`）

## 验收命令

从 `packages/multi-workers`：
`python -X utf8 -m pytest test_review_split_cli.py -q`（7 passed）

## 改动历史

| 日期 | 改动 | 依据 |
|---|---|---|
| 2026-10-22 | 初始卡（M1 拆分） | design.md §2.2、spec AC-S1b |

# RQ-D2 — mw Python 侧的 CLI / 配置 / doctor / 证据 / 测试 既有模式

- key: mw-jev-provider-integration · type: research · DESIGN 相位调研
- timeout: 40

## 上下文

本 key 要新增一个决策客户端与 CLI（`mw decide`）+ 一个新配置文件 + 一行 doctor 展示 + 机器可读证据行，并配 Python 测试。为让设计与实现"照既有模式写、不发明新风格"，需要把 mw Python 侧的既有骨架盘点清楚。

goal.md Key Constraints（文件锁/原子写/凭据隔离）。已知锚点：`packages/multi-workers/mw.py:3495`（`cmd_model`）、`packages/multi-workers/mw.py:3464-3492`（`_model_write` 读改写）、`packages/multi-workers/mw_common.py:217-261`（配置路径与加载，fail-soft）、`packages/multi-workers/mw_common.py:4460-4496`（doctor 行）。

## 审计目标（调研问题）

- Q1 CLI 骨架：`mw.py` 的子命令如何注册/派发（函数命名、参数解析、`argparse` 还是手写、help 文本、退出码约定、`mw` 入口脚本在哪）；给 path:line 与最小可复用骨架。
- Q2 配置读写：`.mw/` 下既有哪些配置文件、用什么格式、由哪个函数读写；是否有通用 YAML/JSON 读工具；**P-003 原子写**的实现位置与调用方式；新配置文件应遵循的命名与容错约定（含"文件缺失/损坏"时的 fail-soft 行为参照）。
- Q3 doctor 行：`mw_common.py:4460-4496` 的行格式与字段渲染细节；新增一行需要动哪些函数/常量；既有行的错误/警告标记（如 `ERROR`）怎么表达。
- Q4 证据行与 PM 可见面：Python 侧写机器可读行（worker `trace.log` 的 `[TOOL]`/`[FLOW]`/`[END]`、launcher 的 `[MODEL_RETRY]` 等、autopilot ledger/alarm）分别由谁写、用什么 API（path:line）、格式约定（前缀、时间、字段分隔）；**列出全部既有 `[XXX]` 前缀**以便新前缀不撞名。
- Q5 测试骨架：`packages/multi-workers/test_*.py` 的组织与命名、跑法（`./test.sh` 与直跑 vitest/pytest 的关系）、断言风格、临时目录与环境变量隔离约定、中文/编码注意点；给一个最小可复制的测试骨架。
- Q6 编码与输出卫生硬规则在代码里的体现：显式 `encoding="utf-8"`、避免 PowerShell 管线、stdout 行数约束（若有）、以及 mw 侧对 Windows 路径的处理惯例（pathlib？字符串拼接？）。

## 唯一证据文件

- `.agenticdoc/mw-jev-provider-integration/evidence/research/design-mw-python-patterns-20261016.md`（新建，全文中文，每条结论附 文件:行号）

## 写入允许面

- `.agenticdoc/mw-jev-provider-integration/evidence/research/design-mw-python-patterns-20261016.md`

## 写入禁止面

- 一切源码/配置；禁止 git add/commit；禁止写入其它 key 目录

## 验收命令

```bash
python -c "import pathlib; t=pathlib.Path(r'H:\git\Multi-Workers\.agenticdoc\mw-jev-provider-integration\evidence\research\design-mw-python-patterns-20261016.md').read_text(encoding='utf-8'); print('bytes:',len(t)); print('Q-answered:', sum(1 for q in ['Q1','Q2','Q3','Q4','Q5','Q6'] if q in t))"
```

## 交付格式

- 证据文件：六问逐条结论（含 path:line）+ 「既有 `[XXX]` 前缀清单」（供新前缀避让）+ 「最小可复用骨架」（CLI 子命令 / 原子写 / doctor 行 / 测试各一段，注明来源行号）。
- 输出卫生（硬性）：每条命令 stdout ≤30 行。

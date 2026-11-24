# PLAN → TASKS 启动检测修复

## 系统行为变化

MW 启动时的能力检查原先只识别独立的 `from plan_closure import problems ...`，而 AgenticTask 84bbc27 同时导入 `_AC`、`_defined_ids` 与 `problems`，导致八个项目 reload 后全部误报缺少 PLAN → TASKS 门禁。本轮只修正静态导入绑定识别，支持多个名称、别名及括号换行；忽略注释，不执行项目 Python 代码。

真实 `plan_closure.py`、调用及 TASKS 注册仍须存在，原生计划闭环、scope review 和阶段推进代码保持。原安装只核对了框架文件，遗漏了 MW 启动检测的兼容性；本轮补上旧安装与热修版对八项目的对照验证。

- 源码提交：`18a2f5b9c5ba7ec5be9a0f5d1c70aba71866e871`，仅修改能力检测与新增回归两个文件。
- 用户级全局 MW、pi 和扩展已安装冻结版 `mw-plan-gate-capability-20261124`，pi 0.83.0；旧入口与扩展保存在该目录的 `deployment-backup`。
- 八项目的 AgenticTask 脚本、项目阶段与认领未更改。Python 后台代码未变，无需为本修复重启后台。

## 验收

- AC-001/002：新增检测回归 16/16、现有脚本调用 5/5、原生计划闭环及 scope review 19/19，共 40 项通过。正式证据：`evidence/codex-pm/self/1795525352953280000-mnk_x1kd/result.json`。初次回归为 5 失败 / 8 通过，保留于 `evidence/regression-before.log`。
- AC-003：根 `npm run check`、冻结扩展自检、pi 编译和加载通过。旧已安装检测在实际八项目为 0/8，热修源码和已安装构建均为 8/8。安装文件与产物哈希逐项复核通过，见 `evidence/installed.json`、`eight-projects-before.json`、`eight-projects-postinstall.json`，正式证据为 `evidence/codex-pm/self/1795525499652553700-l6ihg4rj/result.json`。
- 两次正式验收的源码与合同散列相同，均为 passed。本轮为 Codex 自验，无新增独立执行者复核，无真实模型请求。

## 遗留

无未实施修复。已打开的 pi 窗口需再执行一次 `/reload`，才能使用本轮刚安装的扩展。缺失或损坏的真实框架仍会告警，不屏蔽合法错误。

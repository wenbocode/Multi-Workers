# mw-plan-gate-capability-fix · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: mw-plan-gate-capability-fix
- Phase: DONE
- Claim-Id: —
- Status: idle

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

修复项目 reload 后错误报告 AgenticTask PLAN → TASKS gate unavailable 的问题，让已正确安装的框架可正常识别并推进任务，保留真实计划闭环和 scope review 门禁。

## 范围

控制和源码工作区为 E:/gitlite/Multi-Workers。只修改 shared/agentic-scripts.ts、独立回归测试及必要交付文档；核对八项目已安装 84bbc27 的实际脚本。构建新的冻结 MW 版本并全局安装，保留旧版本回滚入口；不改项目阶段、任务、认领、AgenticTask 脚本或其它项目后台。

## 验收标准

- AC-001: 静态能力检测识别真实已安装的多名称 problems 导入、别名及括号换行形式，不执行项目 Python 代码；八项目检查通过。
- AC-002: 缺脚本、缺 problems 绑定、缺调用或缺 PLAN → TASKS 注册时仍报告不可用；真实原生计划闭环与 scope review 的拒绝和通过路径维持。
- AC-003: 定向回归与 npm run check 通过；新冻结版构建、安装并在实际项目路径复验，不再对当前框架产生启动误报。

## 关键决策

根因为启动检查只接受 `from plan_closure import problems ...` 单独一项的严格正则，而已安装脚本从同一模块同时导入 `_AC`、`_defined_ids` 和 `problems`。只修复导入识别，不删除告警或放宽真实阶段门禁。

## 执行与验收

Codex 直接执行；初次回归 5F/8P，修复后新增 16/16、现有脚本调用 5/5、原生门禁 19/19，根检查通过。旧已安装检测在八项目为 0/8，热修源与安装构建为 8/8。源提交 18a2f5b9c，全局冻结版 mw-plan-gate-capability-20261124 已安装。无派发 Worker，本轮记录为自验。正式证据见 evidence/codex-pm/self/1795525352953280000-mnk_x1kd/result.json 和 evidence/codex-pm/self/1795525499652553700-l6ihg4rj/result.json。

## 接续须知

通过 python -B packages/multi-workers/codex_pm.py status --project . --key mw-plan-gate-capability-fix 恢复。全部验收通过，无在途 Worker；交付与重载说明见 achieved.md。原始红测及新旧八项目对照证据保留。

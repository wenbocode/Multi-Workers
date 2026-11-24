# mw-remaining-closeout · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: mw-remaining-closeout
- Phase: DONE
- Claim-Id: —
- Status: idle

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

收尾上一轮按 key 列出的开发遗留，使已审查的 MW/AgenticTask 改动经过当前源码验证后可提交、安装和复核。保留 DP/PM 推进循环，不新增过程门禁。

## 范围

控制工作区为 E:/gitlite/Multi-Workers。核对并接续 mw-signoff-freeze-metadata、ue-frame-install-generate、mw-repo-check-baseline、mw-duty-followup、mw-runtime-version、mw-pi-version、mw-zai-glm54 及此前列出的遗留回归；AgenticTask 开发克隆的正式签收改动单独处理。保留其他窗口在途产物和历史失败，不将运行日志、历史快照删除或无关文件清理混入提交。逐文件归属写入 docs/mw-remaining-review-list-20261124.md。

## 验收标准

- AC-001: 剩余源码和测试按原 key 归属列明；当前 npm run check 与对应定向回归通过，失败有真实归因和处理结果。
- AC-002: duty-followup 遗留的 busy 发送与 reservation 恢复问题通过永久回归验证；签收、UE 安装与版本入口使用当前实现复验，不弱化既有权限或裁决能力。
- AC-003: 形成可审查的提交清单和冻结构建，全局安装后核对 MW/pi/扩展及 AgenticTask 的实际文件；安装前后保留工作区其他改动，未获规则所需确认的动作明确保留。

## 关键决策

按用户“把剩下的内容都处理掉”接续原待办，并按明确文件清单接手提交此前其他会话留下的已验收源码；先验收后提交/安装，不重复交付已完成的 additional-write-roots。新 key 只负责本轮收尾与必要纠错，不把旧完整 SDD key 自动转换为轻量流程，也不释放仍在运行的其他 PM 认领。2026-11-24 用户已另行明确确认：发布 AgenticTask dd0e6f3 到 origin/master 并更新八个项目。使用独立审查克隆，原开发克隆的 HEAD、未提交字节和索引均保留。

## 执行与验收

Codex 直接执行。当前源码 Python 983 项、TS 436 项、值守 30 项、UE 模板 10 项、AgenticTask 54 项通过；根 npm run check 通过。冻结候选 MW 自检、pi 编译与加载通过。逐文件归属见 docs/mw-remaining-review-list-20261124.md，精确输入见 evidence/scoped-files.json，原始红测保留。本轮无新派出的 Worker；验证明确记为自验。

源码已提交 61e40b198，MW 全局安装和本仓库后台已切换，AgenticTask 八项目安装完成。远端 84bbc27 与审查提交 dd0e6f3 的源码树完全相同；直接采用已发布版本。正式验收覆盖全部 AC，证据为 evidence/codex-pm/self/1795524474968860000-2t6sy2yc/result.json。交付、保留范围和接续见 achieved.md。

## 接续须知

恢复命令：python -B packages/multi-workers/codex_pm.py status --project . --key mw-remaining-closeout。无本轮在途 Worker；全部验收通过，准备按正式接口结案并提交本轮文档与证据。旧 PM 认领与原 SDD 历史不改写；已打开窗口按各自生命周期重载。

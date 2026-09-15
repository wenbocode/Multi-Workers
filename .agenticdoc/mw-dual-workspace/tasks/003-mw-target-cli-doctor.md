# Task 003: mw target CLI + doctor 扩展

- Stage: S1
- 代码状态: 代码完成
- 验证状态: 验证通过（2026-09-11，12/12 + 全量 391 零回归 + CLI e2e 冒烟，证据 evidence/runs/003-mw-target-cli-doctor.md）
- ac_refs: [AC-005]
- vc_refs: [VC-010]
- pattern_refs: []
- deps: [002]
- 预估: ~1.5h

## 交付物

- `packages/multi-workers/mw.py`: `target set --game <p> [--engine <p>] [--vcs git|p4|none] [--uproject <p>]` / `target clear` / `target show` 子命令
- doctor 扩展: PyYAML 导入检查 + target.yml 结构校验 + toolchain 探测（Build.bat 存在性、engine 路径有效性等）→ 结果持久化 `.mw/toolchain.json`
- `packages/multi-workers/test_mw_target.py`（新增）+ `test_serve_doctor.py` 扩展

## 实现要点（design.md D-011/D-013）

- **D-011 为 [AI 推荐] 形态**：若用户在执行期调整指令形态，以用户意见为准更新本 task
- `target set` 只写引导字段（mode/game/engine/vcs/uproject），不碰三节内容：
  - 文件不存在 → 写含注释的完整模板（引导字段 + 空三节骨架）
  - 文件已存在 → **行级更新顶层引导键**（regex 定位 `^game:` 等顶层标量行替换；避免 safe_dump 丢注释/格式）
- `target show`: 调 `load_target_config` 显示解析后 roots + 占位符渲染示例
- `target clear`: 删 target.yml（single 回落）
- toolchain 探测缓存: `{probed_at, checks: {name: {ok, detail}}}`；存在且 `probed_at` 新于 target.yml mtime 则跳过重探（D-013：项目确定后一般不变）
- P-001 编码铁律: 一切读写显式 `encoding="utf-8"`；禁止 PowerShell 文件往返

## 验证方式（VC 断言）

- VC-010: set 后解析根=game、clear 后=控制根；写面断言（monkeypatch fs 只触 target.yml）；dist 产物 mtime 前后快照不变 → `[VERIFY] VC-010: dual-root=game single-root=control write-scope=target-yml-only dist-mtime-unchanged=true`
- 证据落盘: `evidence/runs/003-mw-target-cli-doctor.md`

## 依赖与阻塞

- 依赖 002（Py 解析层）。doctor 的 toolchain 探测项列表执行期可按实际命令模板扩展。

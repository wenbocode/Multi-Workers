# Task 002: Py 侧 target-config 解析 + TS/Py parity

- Stage: S1
- 代码状态: 代码完成
- 验证状态: 验证通过（2026-09-11，Py 5/5 + TS 36/36 同一 14 fixture 集，multi-workers 379 全绿，check exit=0，证据 evidence/runs/002-py-target-config-parity.md）
- ac_refs: [AC-001, AC-004, AC-005]
- vc_refs: [VC-001, VC-006, VC-007, VC-008]
- pattern_refs: []
- deps: [001]
- 预估: ~1.5h

## 交付物

- `packages/multi-workers/mw_common.py` 扩展: `load_target_config(control_root)` + `render_toolchain_command()` + `discover_uproject()`
- `packages/multi-workers/test_common_target_config.py`（新增）
- parity fixture 集: `packages/multi-workers/test/fixtures/target-config-cases/`（target.yml 样本 + 期望结果，TS/Py 共用同一份）

## 实现要点（design.md D-002/D-010）

- PyYAML `yaml.safe_load`（6.0.3 环境实测可用，见 design note 补充核查）；损坏 → 显式异常 fail-closed
- 与 TS（Task 001）语义逐条对齐: env>target.yml>single 优先级、占位符 fail-closed、uproject 唯一性发现；错误消息格式尽量一致（parity 断言按「错误类别 + 关键字段」而非逐字节文案）
- parity 锁定（T-17 模式复用）: 同一 fixture 集两侧各跑全量断言，期望结果 JSON 化（mode/roots/渲染串/错误类别）
- 所有文件读写显式 `encoding="utf-8"`（P-001 编码铁律）

## 验证方式（VC 断言）

- VC-001/006/007/008 的 Py 侧用例全部通过（断言内容与 Task 001 对齐）
- parity 断言: TS 与 Py 对同一 fixture 产出相同 mode/gameRoot/engineRoot/uprojectPath/渲染结果/错误类别
- 证据落盘: `evidence/runs/002-py-target-config-parity.md`（两侧测试命令 + parity 对照表）

## 依赖与阻塞

- 依赖 001（TS 侧为参照实现 + fixture 期望值来源）。

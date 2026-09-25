# T-02-closure-module（worker A：dcr-t02-closure-module）

状态: done（2026-09-25，worker A 交付 + PM 亲验） · 覆盖: AC-002(VC-003)/AC-003(VC-004/005)/AC-011(VC-013-L1) · 依赖: design §2 契约（无代码依赖）

产出：autopilot/closure.py（183 行）+ test_autopilot_closure.py（378 行），32 passed；PM 复读契约逐项核对无偏差。

## 目标

新建纯逻辑模块 `packages/multi-workers/autopilot/closure.py` + 单测 `packages/multi-workers/test_autopilot_closure.py`（两个全新文件，不触碰任何既有文件）。closure.py 不 import conductor（保持纯函数 + 数据类），由 conductor 单向消费。

## 接口契约（design §2 钉死，命名偏差 ≤ 别名级）

- `REPROMPT_INSTRUCTION: str` —— 固定通用文案常量：告知驳回原文含义、指示在 `## Achieved` 节内按所列规则组织子节、禁止改动任何 PASS/FAIL 判定。**不得含任何工程词表字面量**（「系统行为变化」「行为影响」「未了事项」——受 VC-003 rg 扫描约束），不得提及 achieved.md 以外的具体文件名。
- `failure_lines(err: str) -> list[str]` —— 按稳定前缀 `"   - "`（3 空格+连字符）提取 stderr 中全部失败行，保持行内字节逐字。
- `has_achieved_failure(lines: list[str]) -> bool` —— 任一行含字面量 `achieved.md`。
- `compose_reprompt_prompt(base_prompt: str, lines: list[str]) -> str` —— 全文 = base_prompt + REPROMPT_INSTRUCTION + 失败行逐字列表，无其他内容（两分式，逐字节可断言）。
- marker 契约：路径 `<key_dir>/.mw-achieved-baddraft.json`；字段 `{"file": "achieved.md", "sha256": <hex>, "declared_at": <iso8601>, "failures": [lines]}`；sha 用字节精确 `hashlib.sha256(read_bytes())`（禁 EOL 归一）。
- `read_bad_draft_marker(key_dir) -> dict | None`
- `write_bad_draft_marker(key_dir, failures: list[str]) -> None` —— 原子写：tmp 文件 + `os.replace`（tmp 名固定 `.mw-achieved-baddraft.json.tmp`，失败残留不可见——全部扫描面按 `^gate-(\d+)\.md$`/`task.md` glob 过滤，已核验）。
- `delete_bad_draft_marker(key_dir) -> None` —— 幂等（缺失不抛）。
- `overwrite_authorized(marker: dict | None, current_bytes: bytes, failure_lines: list[str]) -> bool` —— 三条件全真才 True：marker 非空 ∧ `marker["sha256"] == sha256(current_bytes)` ∧ `has_achieved_failure(marker["failures"])`（注意第三条件锚定 **marker 记录的失败行**，非调用方当次行）。

## 步骤

1. TDD：先写 test_autopilot_closure.py（下述用例），再实现至绿。
2. L0/VC-003：用例扫 `autopilot/` 源码目录（rg 或等价 Python 实现）对三词表字面量 0 命中（closure.py 自身也在扫描面内）。
3. L1/VC-004 真值表 4 否定例：marker 缺失 / sha 失配 / failures 无 achieved.md 行 / marker 为 None——各返回 False 且**不做任何写操作**（临时目录字节不变断言）。
4. L1/VC-005 全真例：tmp 目录造 200B 草稿 + 合规 marker → overwrite 授权 True；write→read 往返字段完整；write 原子性（无 .tmp 残留）；delete 后 read 返回 None；重复 write 同一文件不增殖（单文件）。
5. L1 辅助：failure_lines 对 `"GATE BLOCKED:"` 头 + 多行 `"   - "` 载荷的解析（逐字、顺序、无多余空白）；compose_reprompt_prompt 逐字节等式断言。

## 验证

- `python -m pytest test_autopilot_closure.py -q` 全绿；不触碰 closure.py/test 文件之外的任何文件。

# T-02 L1 真值表测试（W2 单写者，TDD 红测）

key: `xkey-repair-mechanism` · 依赖: 仅冻结契约 · 覆盖: VC-001…006,011,012

## 目标

新建 `packages/multi-workers/test_autopilot_xkey_registration.py`——**对 HEAD 必红**（实现由 T-01/T-03 提供），落地后转绿。语料驱动，禁止凭空构造无出处的"字形"。

## 语料来源（必须逐字引用 + 标出处）

`.agenticdoc/xkey-repair-mechanism/evidence/research/design-registration-carrier-20260926.md`（10 字形 S-A…S-J，含 S-A/S-B 键值对与 S-C/S-E/S-F 散文）+ `.agenticdoc/xkey-repair-mechanism/evidence/research/design-boundary-apply-20260926.md`（冻结块定位实验）+ spec §1.1 的 FM 实物锚点（`repair-r1-out-20260925-r3.txt:220`、`cli-run-state-and-events/l3-report.md:17/:58`、`ap-cli-hitl-channel-l3-a1/report.md:68`）。

## 用例清单

1. **解析真值表（VC-011）**：10 字形逐条用例——KV 字形断言 `parse_registration` 字段**逐字段等于人工判读值**；散文字形断言返回 `None`（=升级，不提案）。每条用例上方注明语料出处（file:line 或证据文件节号）。
2. **owner 角色值拒绝（VC-002）**：`兄弟 key` / `PM` / `conductor` 三种值 ⇒ `None`（不得当成 owner_key）。
3. **账本幂等（VC-001）**：同 `(file,test_id,block_sha)` 扫描 N=3 次 ⇒ `rows` 长度 1、`history` 不因重复扫描增长；`dedup_key` 稳定性（同输入同值）。
4. **工单未授权零写（VC-003）**：写工单前后目标文件 sha256 相等。
5. **边界正反例（VC-005）**：正例（改冻结常量值）⇒ `"ok"`；反例三类（改断言主体行 / 触 untouchable / 涉及第二个文件）⇒ `"violation"`，且断言 `apply_block_replace` 未被调用（用 monkeypatch 计数）。
6. **sha 漂移作废（D-012）**：工单记录 sha 与磁盘不符 ⇒ `apply_block_replace` raise 且文件字节不变。
7. **证据包五项（VC-006）**：齐备 ⇒ `closed=True`；逐项缺一（5 个负例）⇒ `closed=False`。
8. **gate flood（VC-012）**：同一 pending 工单经 N=5 tick ⇒ `xkey-authorize` gate 文件数 = 1（此例可断言 conductor 层，若依赖 T-03 未落地则标 `@pytest.mark.skip` 并在报告说明；落地后由 PM 复跑）。
9. **开关关闭零扰动（VC-008）**：`xkey_repair=False` 时 `xkey/` 目录零新增（同上，允许标 skip 待 T-03）。

## 硬约束

- **禁止修改**任何既有测试文件；特别**不得触碰**两处 sha 锁：`test_autopilot_verdict_source_fallback.py:66-67/:529`、`test_autopilot_verdict_freshness.py:68`。
- 新文件自包含（fixture 用 `tmp_path`，不污染仓目录）。
- 用 `pytest.mark` 标注依赖 T-03 的用例，禁止用 `xfail` 掩盖真实失败。

## 验收

- `node ../../node_modules/vitest/dist/cli.js` **不适用**（Python 侧）：在 `packages/multi-workers` 下 `python -m pytest -q test_autopilot_xkey_registration.py`（**加 `-s` 以免吞输出**）——此时对 HEAD 应红（导入 `autopilot.xkey` 失败或断言失败），报告须给出**红的真实输出**以证明非空洞。
- 报告含：用例数、每条用例的语料出处、对 HEAD 的红输出摘要。

## 纪律

- 只写这一个新文件（+ 报告）。不改实现、不改 conductor、不改 TS。

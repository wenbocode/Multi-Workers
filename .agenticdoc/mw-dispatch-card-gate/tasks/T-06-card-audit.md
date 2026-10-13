# T-06 卡追溯（sha256）与集合一致性

- Key: mw-dispatch-card-gate｜Wave: 1｜依赖: 无｜type: coding

## 上下文
卡片与派发之间没有引用关系，事故时无法回溯"这次派发依据哪张卡"（`spec-dispatch-path-20261012.md` ②）；一致性差集的现成实现见 `packages/multi-workers/autopilot/conductor.py:2417/2433`。依据 `design.md` §2.3。

## 要求
1. 新建 `packages/multi-workers/autopilot/card_audit.py`（叶子模块，仅标准库 + 现有 `mw_common`）：
   - `card_digest(path) -> str`：复用 `mw_common.sha256_eol_normalized`（EOL 归一，跨平台稳定）；
   - `audit(agenticdoc_root, key) -> { cards[], dispatched[], missing_cards[], unlisted_dispatches[], digests{} }`：`cards` 取 `tasks/*.md`（排除模板/非卡文件须有明确规则），`dispatched` 取 `workers/*/task.md` 的 `card_path:` 头（若无则记 `unlisted`）；
   - 缺 `card_path` 头的历史派发计入 `unlisted_dispatches`，**不判红**（迁移兼容），仅在 `--strict` 下视为失败。
2. CLI 入口 `python -X utf8 packages/multi-workers/autopilot/card_audit.py --root .agenticdoc --key <key> [--strict]`，输出人可读表 + 退出码（strict 且有差异 ⇒ 非 0）。
3. 新增测试 `packages/multi-workers/test_mwds_t27_card_audit.py`：正常/缺卡/未登记派发/等长篡改（digest 变化 ⇒ 检出）四类用例；篡改用例必须**等长替换**。

## 交付格式
- 写入允许面：`packages/multi-workers/autopilot/card_audit.py`（新）、`packages/multi-workers/test_mwds_t27_card_audit.py`（新）。
- 写入禁止面：`packages/multi-workers/mw.py`、`autopilot/conductor.py`（只读参考）、`packages/coding-agent/**`、其他 key 目录。
- 回收判据：`python -X utf8 -m pytest packages/multi-workers/test_mwds_t27_card_audit.py -q` 全绿；在真实 `.agenticdoc` 上跑一次并把输出写入 `report.md`（须显示既存 `unlisted_dispatches` 规模）；报告含改动清单。

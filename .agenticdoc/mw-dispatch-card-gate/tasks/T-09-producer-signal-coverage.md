# T-09 生产者信号全覆盖（conductor 注入 + 豁免改按时间边界）

- Key: mw-dispatch-card-gate｜Wave: 4｜依赖: T-02（注入形态）、T-03（已终态）｜type: coding

## 上下文
T-03 把服务层兜底实现为「按**触发信号**（canonical 段标题或 `card_path:` 头）决定是否校验」，因此在 `packages/multi-workers/launcher.py` 里**无信号的行被放行**。被放行的恰好是**绕过工具的两个生产者**：conductor 直写（`packages/multi-workers/autopilot/dispatch.py:290 render_task_md` → `:625 write_text`）与手写队列行 —— 这使 G-3 的"覆盖 4 个生产者"名不副实（`evidence/…/workers/mwd-t03-service-fallback/report.md` §5.3 残留①，PM 已裁定收口于本卡）。

## 要求
1. **conductor 注入**：让 `render_task_md` 的输出与 T-02 同形态 —— canonical 段标题 `## 上下文` / `## 要求` / `## 交付格式`，以及头部区**裸行** `card_path:`（归一形式 `tasks/<name>.md`）与 `card_sha256:`（EOL 归一 sha256，须与 `packages/multi-workers/mw_common.py` 的 `sha256_eol_normalized` 和 TS `shared/card-digest.ts` 三方一致）。
2. **豁免改为时间边界，而非"有无信号"**：`launcher.py` 用**队列行的创建时间**（行内既有时间戳字段；若行内没有，则在 T-03 的失败记录处一并落 `created`）与常量 `ENVELOPE_ENFORCE_SINCE`（默认 `2026-10-12`，cutover 日期）比较：
   - 早于边界 ⇒ 豁免（历史兼容，P-07/P-09）；
   - 晚于边界 ⇒ **无论有无信号、无论卡形态，一律 fail-closed**（不 spawn、行 `failed` + 原因指名缺失项）。
3. **不得放宽判据来迁就旧 fixture**：既有 `test_launcher.py` 的旧式 fixture 若需豁免，改的是**fixture 数据**（给它们早于边界的时间戳），不是判据本身。
4. 新增测试 `packages/multi-workers/test_mwds_t29_producer_signal.py`：conductor 生成的 `task.md` 通过校验且与 TS judge 的判定 parity；早于边界的旧行豁免；**晚于边界且无信号/缺段 ⇒ 拒绝**（这三类的原始输出都要进报告证据）。

## 交付格式
- 写入允许面：`packages/multi-workers/autopilot/dispatch.py`、`packages/multi-workers/launcher.py`、`packages/multi-workers/test_mwds_t29_producer_signal.py`（新）+ 仅限测试文件内的 fixture 数据调整。
- 写入禁止面：`packages/multi-workers/mw.py`、`packages/multi-workers/mw_common.py`（只读）、`packages/multi-workers/autopilot/conductor.py`（只读）、`packages/coding-agent/**`、其他 key 目录、`.agenticdoc/**`（除本 worker 目录）。
- 交付物：上述改动 + 测试；`report.md` 含结论/证据（原始命令与输出）/改动清单/残留与未验证/上下文来源清单。
- 回收判据：
  - `python -X utf8 -m pytest packages/multi-workers/test_mwds_t29_producer_signal.py packages/multi-workers/test_launcher.py packages/multi-workers/test_mwds_t27_service_envelope.py -q` 全绿；
  - 报告须含「晚于边界 + 无信号 ⇒ 拒绝」与「早于边界 + 旧式卡 ⇒ 豁免」两条**原始输出**；
  - 改动清单 ⊆ `trace.log` 的 `[WRITE_FILE]` 事件（cutover 后生效）。

# T-03 服务层兜底（覆盖全部生产者）

- Key: mw-dispatch-card-gate｜Wave: 1｜依赖: 无｜type: coding

## 上下文
入队生产者有 4 个，工具层只得 2 个；唯一全覆盖的是服务层 `packages/multi-workers/launcher.py:872 _poll_once`（`evidence/research/spec-gate-layer-20261012.md` §1）。现状缺项或文件缺失会**静默归档**到 `_workers.stale.parallel` 且无消费方（`evidence/research/spec-dispatch-path-20261012.md` ⑤）。依据 `design.md` §4 的 G-3。

## 要求
1. 在 `launcher.py` 的 `_poll_once` 路径上、`:1055 _spawn` **之前**，对每个待 spawn 的 `workers/<task_key>/task.md` 做**独立**校验（不得 import TS）：
   - `type:` 存在且在词汇表内；
   - 三段（上下文/要求/交付格式）宽档非空 —— 判据必须与 TS 侧同源：**同词表、同宽档**，词表与门槛常量集中定义并在两侧测试中固定。
   - 类型附加项（同 T-01 规则）。
2. 不合规 ⇒ **不 spawn**；`_workers.parallel` 行置 `failed`，原因写入该行与 `worker.log`（格式 `[launcher] envelope missing: <items> (<path>)`）。**不得**再走静默 stale 归档。
3. 兼容：缺失 `task.md`（非信封问题）保留既有 stale 归档语义，但日志须写明（不得静默）。
4. 新增测试 `packages/multi-workers/test_mwds_t27_service_envelope.py`：三种负例（缺段/缺 `type:`/缺类型附加项）+ 一种正例（合规卡 spawn）；断言负例零 spawn、行 `failed` 且原因含缺失项名。
5. **跨语言 parity（必做）**：词表与门槛常量须与 `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts` 导出的 `ENVELOPE_HEADING_FAMILIES` / `ENVELOPE_BODY_HINTS` / `ENVELOPE_BULLET_KEYS` / `TYPE_EXTRA_SECTIONS` 逐项对齐；新增 parity 用例：对同一批语料（>=20 份：本 key `tasks/*.md` + 若干历史 `workers/*/task.md`），Python 与 TS 判定结果**逐份相等**。头部区规则同 TS：**首个 H2 之前的卡前区**，`type:` 裸行或 `|`/`｜` 分隔皆可（实测真实卡 0/345 有 fenced `type:`；严格窄头区会拒全部真实卡）。`worker .tmp/` 不可写 ⇒ 脚本放本 worker 目录并在报告中内联可重建。

## 交付格式
- 写入允许面：`packages/multi-workers/launcher.py`、`packages/multi-workers/test_mwds_t27_service_envelope.py`（新）。
- 写入禁止面：`packages/coding-agent/**`、其他 key 目录、`.agenticdoc/**`（除本 worker 目录）。
- 回收判据：`python -X utf8 -m pytest packages/multi-workers/test_mwds_t27_service_envelope.py -q`（或仓库既有 pytest 调用方式）全绿，且 `test_launcher.py` 不回归；报告含改动清单。

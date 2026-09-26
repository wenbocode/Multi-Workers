# T-07 跨语言一致性判据（P1-P6 + 共享语料 + fail-closed）

- AC: AC-006 · VC: VC-006, VC-015 · 波次: 2（依赖 T-01/T-04）
- 写面：**新建** TS 测试（`packages/coding-agent/test/suite/` 下，如 `autopilot-config-parity.test.ts`、`autopilot-config-sync.test.ts`）、**新建** Python 半表测试（`packages/multi-workers/test_autopilot_config_parity.py`）、**新建**共享语料 JSON（一处分发两份读取，或两侧读同一文件）

## 契约（design D-013，6 条判据）

- **P1 差分结论一致**：TS vitest `spawnSync(resolveRagPython())` 跑 Python 侧校验（先例 `rag-parity.test.ts:147-169`），逐 payload 断言两侧 ok/err 结论一致；语料含 `4.0` / `4.5` / `1e2` / `-0.0` / 范围边界 / partial / 未知键 / bool 当 int / 空与空白 list。
- **P2 跨侧字节一致**：同一配置分别由 Python `save_config` 与 TS `saveConfig` 写，断言 sha256 相同（语料含中文、emoji、反斜杠、`</script>`、tab）。
- **P3 互读幂等**：A 侧写 → B 侧读改写 → 字节不变。
- **P4 语料完整性**：断言语料 sha256 与用例数（冻结），覆盖 D1–D6 历史差异类别。
- **P5 新键镜像**：TS 起 python 子进程 dump `DEFAULT_CONFIG/_BOOL_FIELDS/_LIST_FIELDS/_INT_RANGES`，与 TS 镜像表逐字比较（键集/顺序/默认值/类型/范围）。
- **P6 partial 读取语义**：Python 与 TS 对 partial 文件都产出 13 键全量。
- **全 fail-closed**：对端解释器缺失 ⇒ **硬失败**（禁止 `skipIf`/静默 skip；P-016）。Python 侧半表可用 `node` 反向差分。

## 验证

- `packages/coding-agent`: `node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-config-parity.test.ts test/suite/autopilot-config-sync.test.ts` 全绿（真实调用 python）。
- `packages/multi-workers`: `python -m pytest -q test_autopilot_config_parity.py` 全绿。
- 非空洞对照：去掉 TS reviver ⇒ P1 的 `4.0` 用例必须红。
- `[VERIFY]` 行：P1-P6 各一条（含语料 sha256 与用例数）。

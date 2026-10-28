# T04b ledger supplement（只补追溯，不改 pm-state.md）

原 T04 的 Evidence Ledger / run ledger 未记录 `decide_registry.json` 的写入（该文件在原 T04 卡的允许面内），
T04b 报告据此补记实际生成路径、字节数与 sha256，供 PM 合并进 pm-state / 台账。本卡未改任务或相位文档。

## 1. T04 已写入但 ledger 漏记（本卡未再写）

| 路径 | 字节 | sha256 | mtime | 生成方式 |
|---|---|---|---|---|
| `packages/multi-workers/decide_registry.json` | 62396 | `c836bc7e776a7f31342c35d6f9bc761824cf916db086d1e1a33ec30b0bd64757` | 2026-10-22 12:01:25 | `mw decide dp export --write` → `decision_points.registry_snapshot_text` |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts` | 33283 | `36a84c1edb3cfb8f6be7cf302338f0d9557a5aff24265af11989dbabe3ac5fc9` | 2026-10-22 12:05:49 | `python scripts/gen_decide_registry_ts.py` |

两者在 T04 时已验证为可从 registry/JSON 重新渲染的产物；本卡验收套件继续锁定：

- `test_decide_registry_export.py::test_export_is_byte_identical_to_a_regeneration`
- `test_decide_registry_ts_lock.py::test_generated_registry_matches_a_fresh_render`
- `test_decide_registry_ts_lock.py::test_generator_check_mode_is_clean`

## 2. T04b 本卡写入

| 路径 | 字节 | sha256 | 说明 |
|---|---|---|---|
| `packages/multi-workers/mw.py` | 481642 | `5214794799ae680d816a6d7acf4ffc8c114899f073653207e25bdfaf3091fff2` | 仅 `_DP_VERIFY_STATE_VALUES` 纯数据（+103/-0，单 hunk） |
| `packages/multi-workers/decide_book_template.json` | 3178 | `ba84d388455dbc906bbaed647ca63daa4d56aedaf3bd8e475a3b2e0f58ea277d` | `scaffold_book` 重生成（+18/-2，仅 dp6） |

## 3. 命令（cwd 见各行）

```
# cwd packages/multi-workers
python ../../.agenticdoc/mw-decision-dashboard/evidence/runs/T04b-contract-artifacts/regen-book-template.py --write
python -m pytest test_decision_dashboard_contracts.py test_decide_registry_contract.py \
  test_decide_registry_export.py test_decide_registry_ts_lock.py test_decision_points.py \
  test_decision_book.py -q          # exit 0, 395 passed

# cwd repo root
npm.cmd run check                   # exit 1, biome 3 warnings + 2 infos in untouched mwoc-*.test.ts
```

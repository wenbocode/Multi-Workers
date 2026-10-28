# 决策签收 / Decision sign-off: claim-driven-review

> 由 `mw decide sign` 生成的人类签收记录；`conclusion:` 等机器行为列 0 单行。
> done 门禁（`advance_phase.py` 的 `decision_signoff` 检查）只在 key 目录存在
> `decision-scope.md` 时生效，并按 `rows_sha256` 重算比对档案。

conclusion: narrow
counted_rows: 1
rows_sha256: 1d990e463cfda8e59c753370cf64ab6993cd199901bb896b5d8e358cee28baf5
engine: timi-decisions/jev-latest/api
allow_empty: false
key: claim-driven-review
claim: WENBOZHOU-PC4:69520
ts: 2026-10-22T12:18:49+00:00
reason: -
promote: -
demote: -
p0-open: -
signed_via: auto-decide

## 计数表（按 dp）

| dp | rows | available | acted | escalated |
| --- | ---: | ---: | ---: | ---: |
| dp7-gate-failure | 1 | 1 | 0 | 1 |

## 引擎（transport/model/confidence_source）

| engine | rows |
| --- | ---: |
| timi-decisions/jev-latest/api | 1 |

## 上抛原因分布

| escalated_reason | rows |
| --- | ---: |
| low-confidence | 1 |

## 已开 P0

-

## 依据

- archive: `H:\git\Multi-Workers\.agenticdoc\_autopilot\decisions.jsonl`
- chain_ok: true
- p0 source: config
- n_available: 1 / counted_rows: 1

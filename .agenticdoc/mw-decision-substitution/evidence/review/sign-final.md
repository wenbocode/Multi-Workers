# 决策签收 / Decision sign-off: mw-decision-substitution

> 由 `mw decide sign` 生成的人类签收记录；`conclusion:` 等机器行为列 0 单行。
> done 门禁（`advance_phase.py` 的 `decision_signoff` 检查）只在 key 目录存在
> `decision-scope.md` 时生效，并按 `rows_sha256` 重算比对档案。

conclusion: narrow
counted_rows: 2
rows_sha256: eb447f1d44f6856008fe1767bf4bd37499b2262a266388b7b1ea8bff2dc71819
engine: timi-decisions/jev-latest/api
allow_empty: false
key: mw-decision-substitution
claim: WENBOZHOU-PC4:53592
ts: 2026-10-21T15:40:33+00:00
reason: -
promote: -
demote: -
p0-open: -
signed_via: auto-decide

## 计数表（按 dp）

| dp | rows | available | acted | escalated |
| --- | ---: | ---: | ---: | ---: |
| dp1-dispatch-type | 1 | 1 | 0 | 1 |
| dp3-worker-clarify | 1 | 1 | 0 | 1 |

## 引擎（transport/model/confidence_source）

| engine | rows |
| --- | ---: |
| timi-decisions/jev-latest/api | 2 |

## 上抛原因分布

| escalated_reason | rows |
| --- | ---: |
| low-confidence | 2 |

## 已开 P0

-

## 依据

- archive: `H:\git\Multi-Workers\.agenticdoc\_autopilot\decisions.jsonl`
- chain_ok: true
- p0 source: config
- n_available: 2 / counted_rows: 2

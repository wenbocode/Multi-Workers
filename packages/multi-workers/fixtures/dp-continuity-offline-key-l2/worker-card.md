# T15-B offline worker card (fake-worker.cjs)

role: worker — isolated fake provider/transport/CLI stand-in
run: t15-b-20261117T054654Z  (single isolated key/run)
type: coding
images: no

## Goal
Compute one deterministic, independently recomputable result and persist a
worker deliverable. The worker does NOT decide pass/fail and does NOT emit any
QG / review / sign / phase / Done state.

## Declared computation (verbatim, recomputable by an independent reviewer)
N = 64
sum_sq = sum over i in 1..N of (i * i)
seq = ASCII string "1,2,3,...,N" (decimal integers, comma-joined, no spaces,
      no trailing comma)
seq_sha256 = sha256 of the UTF-8 bytes of seq

## Deliverable
argv[2] is the deliverable output path. Write exactly one JSON object:
{
  "producer": "fake-worker.cjs",
  "card": "worker-card.md",
  "inputs": { "N": 64 },
  "result": { "sum_sq": <int>, "seq_sha256": "<64 hex>" }
}
Print a one-line JSON summary to stdout. No hardcoded verdict; no signing.

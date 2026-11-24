# T15-B offline reviewer card (fake-reviewer.cjs)

role: independent reviewer — isolated fake provider/transport/CLI stand-in
run: t15-b-20261117T054654Z  (same run as the worker; distinct reviewer)
type: review
images: no

## Goal
Consume the worker deliverable and INDEPENDENTLY recompute the declared
computation from the deliverable's declared inputs. Emit a content-based
verdict. The review must be a function of the consumed bytes, not a hardcoded
pass, and must not emit QG / sign / phase / Done state.

## Required checks (each recomputed, never hardcoded)
- producer == "fake-worker.cjs"
- result.sum_sq == sum_{i=1..N} (i*i)          recomputed from inputs.N
- result.seq_sha256 == sha256("1,2,...,N")     recomputed from inputs.N
verdict = "pass" iff ALL checks are true, else "fail".

## Producer -> consumer binding
Emit producer_sha256 = sha256 of the EXACT deliverable bytes consumed, plus
producer_bytes. This binds the review to the concrete producer artifact.

argv: fake-reviewer.cjs <deliverable> <review-out>
A tampered deliverable (changed result, changed N, or flipped byte) MUST yield
verdict "fail". Hardcoding "pass" is a defect, not a fixture.

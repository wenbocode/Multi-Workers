## Quality Gate Report

| ID | Status | Evidence |
| --- | --- | --- |
| AC-001 | PASS | checks.py@a1f0c41ba713df39587282fcf856af617f4b5c816a3d5c185701542ee7d98fb9 |
| AC-002 | PASS | anchors.json@42013cc0d3b1901e96aea656c093c879fb193554323f08af45f8ba4b7f8be150 |
| VC-001 | PASS | checks.py@a1f0c41ba713df39587282fcf856af617f4b5c816a3d5c185701542ee7d98fb9 |
| VC-002 | PASS | anchors.json@42013cc0d3b1901e96aea656c093c879fb193554323f08af45f8ba4b7f8be150 |
| FLOW-001 | PASS | ordered_rows.py@703d8389adaed01134580180d459e7212d3a83e2fc5a516c6ff1cbcd4072d2cc |

## Achieved

The isolated repair now checks input row order with unsorted input. The original implementation passed that check, and the deliberately sorted implementation failed at the exact ordering assertion. The evidence index resolves to that assertion in the same observed revision. Both review probes ran without modifying the reviewed project.

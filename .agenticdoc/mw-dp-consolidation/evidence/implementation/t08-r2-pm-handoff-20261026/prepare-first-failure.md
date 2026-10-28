# Preparation failure

`python -B prepare-verification.py` exited 1 before creating bootstrap or running product imports/tests. The evidence preparer incorrectly treated `RETIRED_25` as a literal AST value; the inspected assigned test line704 derives it from `dpts.RETIRED_DP_REGISTRY`. Original script is preserved. A new preparer will use that copy-bound authoritative registry directly. No product regression or authorization change is inferred.

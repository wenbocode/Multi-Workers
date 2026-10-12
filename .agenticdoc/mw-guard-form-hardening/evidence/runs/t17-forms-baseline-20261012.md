# T-17 B-6 forms baseline (2026-10-12)

Machine-readable re-run of the RQ-1 79-form inventory
(`evidence/research/spec-form-inventory-20261011.md` §2, R01–R79) against the
extractor on the final working tree of `mw-guard-form-hardening`.

## Command

From the repo root:

```
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t03-bash-write-scope.test.ts
```

The metric lives in `test/suite/mwds-t03-bash-write-scope.test.ts`, describe
`T-17/B-6 forms coverage metric (AC-002)`; it writes the `[FORMS]` line to
stdout and fails if any row violates its AC-002 expectation.

## Raw output (2026-10-12)

```
[FORMS] total=79 covered=79 missing=0
```

## Semantics

- `covered` = the extractor's candidate set satisfies the row's AC-002
  expectation: the correct literal target(s) appear, or the row lands in the
  `allow-unknown` tier (all candidates non-verbatim), or the row correctly
  produces no target (`2>&1`, here-string, pure read, quoted `>`), or (for the
  directory/prefix forms `tar -x`, `find -exec`/`-delete`, `cd LITERAL && ...`)
  a candidate is produced.
- `missing` = rows whose candidate set does not satisfy the expectation.
- Baseline value (RQ-1, `ab546bb64`): `total=79 covered=35 missing=33`.

## Cross-check (AC-011 anchor metric)

The same run family produces the anchor metric from
`test/extensions/agent-team-loop.test.ts`, describe
`T-17/B-1 anchor integrity (AC-011)`:

```
[ANCHORS] refs_total=74 resolved=74 unresolved=0 out_of_range=0 content_mismatch=0 unanchored_refs=0
```

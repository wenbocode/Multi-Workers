# Prepared decision requests

All eight active entries share this protocol: `dp-w-type`, `dp-pm-steer`,
`dp-w-check-task`, `dp-QG`, `dp-gate-approve`, `dp-sign-key`, `dp-auto`, and
`dp-route`. Their roles, business choices, policy and execution gates are unchanged.

## One selection includes the conclusion and its basis

The caller prepares business material and a timestamped `basis_catalog` as before.
The framework generates one `decision_selection` choice question. Each candidate
binds one legal business choice to one prepared basis whose `applies_to` contains
that choice. Branch requirements also apply: for example, a QG `reopen` candidate
requires a substantive `basis_issue`, and an `investigate` candidate requires its
bounded investigation plan.

Two fix bases produce different wire candidates, such as `fixA` and `fixB`:

| Wire choice | Business choice | Prepared basis |
| --- | --- | --- |
| `fixA` | `fix` | Missing ordering assertion |
| `fixB` | `fix` | Missing ordering assertion and stale source anchors |

The endpoint returns one candidate ID. The framework resolves it against this
request's mapping, then returns the existing business answer and `basis_id` to
the PM or Worker. A basis may group several findings. Candidate IDs are local to
the prepared request; changing a catalog can change the mapping. Unknown IDs or
the former two-answer model reply are refused without a default or a second call.

Both normalized answer fields carry the same joint selection confidence. They
are not independent model estimates, and pair probabilities are not relabelled
as probabilities for business choices or bases. Raw transport evidence retains
the selected wire ID. Question versions distinguish the prepared protocol.

## File citations include readable content

New prepared requests can declare an `evidence_refs` array. Each item supplies
an existing `field` such as `material.worker_execution`, a literal `path`,
and optional inclusive `lines` with integer `start` and `end`. An empty
array uses inline material exclusively. When this field is present, prose,
backticks, Markdown links and planned output names do not trigger file reads.
Use the structured list for new requests and for corrected requests that
previously inferred a path from prose.

Decision books can use the same top-level list. Existing file citations in
`notes.evidence` must be moved to the explicit list. Non-file command provenance
may remain in `notes.evidence`. Requests and books without the explicit list
keep their existing citation rules.

The framework resolves precise local file citations in business material,
decision-book `notes.evidence`, and explicit citations in prepared basis text,
then adds `evidence_sources` to the sent state. Basis IDs and plain filename
prose in a basis do not trigger reads.
It reads relative paths from the control project and enforces canonical configured
control/target roots and read-scope deny globs. Callers cannot supply their own
trusted `evidence_sources` block.
Unsupported firewall pattern syntax refuses source preparation rather than
silently treating a restriction as a non-match.

Supported citations include a standalone filename/path with an extension, `path:line`, `path:start-end`,
backtick-delimited paths and Markdown links. Explicit line citations can also
occur in prose. Use delimiters for paths containing spaces. HTTP URLs are not
fetched, command strings are not executed, and citations inside loaded source
text are not recursively followed. Bare paths naming planned deliverables or
action outputs are not treated as proof that those files already exist.

Each source records the canonical path, original file SHA-256 and byte size,
selected line range, actual text, originating material fields, representation
(`full` or `excerpt`), and included/omitted line ranges. Exact duplicate citations
share one source. Missing, unreadable, empty, non-UTF-8 or out-of-scope files and
invalid line ranges refuse preparation before a model call. Reading is bounded
to 8 MiB per source file and 32 MiB of unique source files per request; larger
inputs need a smaller independently prepared artifact.

Worker requests also enforce the trusted task card's header `read_scope` and
`deny_globs` before reading source bytes. Empty scope denies every source;
partition parent-root union applies only to an already nonempty scope. Request
material cannot grant scope. Worker lifetime read counters live in the extension
and cannot currently be charged by this CLI path, so a card with an active read
guard refuses implicit file hydration with an actionable input gap. This includes
deny-only cards, because the existing guard also applies a cumulative byte cap.
Supply already-authorized inline text until a trusted host budget handoff exists.
Zero caps use the existing defaults, not unlimited reads. PM requests and Worker
cards without an active read guard continue to hydrate cited files normally.

## Explicit single-file read grants

When a required rule file lives above the configured workspace roots, use the
control project's `.mw/decision-evidence.yml` instead of widening `game`,
`engine`, or any named root:

```yaml
read_files:
  - 'D:/Dark/AGENTS.md'
```

This is a **decision-evidence-only** policy, separate from `target.yml`. It is
not a workspace read root, a Worker read grant, or a write permission. Only the
host project file supplies authorization; material and basis text cannot grant
it. Paths may be absolute or relative to the control project. There is no
parent-directory inheritance: `D:/Dark/other.md` remains outside scope.

Each entry is a literal file path, with both its lexical and canonical identity
required to match the grant. Do not list symlinks, junction aliases, directories,
or glob patterns; aliases pointing to a granted file are not additional grants.
Use the file's actual canonical path. Existing root-based reads are unchanged.
Workspace deny globs, Worker scope/lifetime caps, UTF-8/size limits and stable
snapshot checks still apply. The policy accepts only `read_files`, with at most
64 entries and 64 KiB of YAML; malformed, duplicate-key, unknown-field or
unreadable policies fail closed before source contents are read. Use
`read_files: []` or remove the file to revoke the extra grants.

The policy, including its absence, is recorded in local file dependencies, so
creating, editing or deleting it invalidates results prepared with this version.
After upgrading from a version that did not track this policy, reload the PM
extension before retrying a previously cached local preparation failure. The
original owning PM must retry the existing decision with its original rules;
this configuration does not supply a decision, receipt or sign-off.

## Explicit compression under the real request budget

Budget accounting includes business material, preparation, evidence text and
the generated pair question. If raw evidence fits, its text is sent unchanged.
When it does not fit, mechanical line-numbered excerpts retain detected failures,
negative facts, unknown/unverified outcomes, constraints, headings and adjacent
context. Omitted ranges are explicit. These excerpts are not semantic summaries
and do not certify that omitted lines were reviewed.

If the protected minimum still exceeds the effective byte/token ceiling, the
request returns `compression-required`. The preparation Agent must cite narrower
relevant ranges or create a sourced summary artifact that preserves failures and
unverified items. The framework does not silently cut core material or call
another model to summarize it. Referenced file contents also pass the same frozen
credential screening as the rest of the request.

Book checks, playground previews and real prepared sends use the same question
and source builder. Capture records the actual prepared state and pair vocabulary;
capture status and truncation metadata remain authoritative. A later file change
does not rewrite an earlier decision's evidence snapshot.

Window replay caching checks framework-provided file dependencies using content
hashes and canonical path identities, including the target read-scope config,
the exact-file decision evidence policy and the exact trusted Worker task card
when present.
Unchanged files reuse the same matter without a new request. Changed bytes,
retargeted aliases or a repaired missing file invalidate the cached source facts;
a trusted stop still prevents any new request. Signing rechecks cited source
dependencies before writing a sign-off, so a source changed during the model
request cannot be silently signed as the original evidence.

Generic operator-authored `decide ask` questions and diagnostic probes keep their
explicit question sets. Retired DP IDs remain uncallable; historical records keep
their original question versions. Human handoff selections remain explicit
business-choice/basis selections and continue to use the existing legality checks.
The former active-DP structured `state` CLI form and direct `decide_for` calls
without a prepared book are refused; use the prepared envelope/book or
`request_prepared` instead of bypassing basis and source preparation.

## Trace a blocked attempt

The control project stores one receipt per recorded block in
`.agenticdoc/_autopilot/dp-blocked/<event_id>.json`. Look up the exact receipt
using `blocked_event_id` from the CLI JSON or the `ask_decision` tool details.
Autopilot gate receipts can be filtered by `gate_id` or `key`.

The receipt includes the UTC time, DP, source, stage, short reason and any
available task, decision or matter identifiers. Repeated blocks have distinct
event IDs. If the tool receives a receipt ID from its MW child, it uses that ID
for the initial call. A later blocked replay gets its own receipt.

Evidence preparation refusals carry `input_diagnostics` in CLI JSON and
`ask_decision`. The tool displays the field and a repair hint, with safe path
and line information when available. If an `evidence_refs[].field` binding
fails, `allowed_fields` lists the paths you can use for this request, such as
`material.review_findings` and `material.review_evidence[0]`. An array item
requires its index. `basis_catalog[].material_refs` uses its own field syntax.
`transport: not-sent` records a local
refusal before transport. The local capabilities command is
`mw decide capabilities`. In a loaded PM window, `/mw runtime` shows the
loaded extension hash and the selected Python entry's capabilities.

From the control project root, list the latest blocks in PowerShell.

```powershell
Get-ChildItem .agenticdoc/_autopilot/dp-blocked -Filter '*.json' |
    ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json } |
    Sort-Object ts -Descending |
    Select-Object -First 20 ts, dp, key, stage, reason, detail, event_id
```

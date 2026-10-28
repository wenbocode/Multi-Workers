# T11a DOM coverage (no new dependency)

## Facility

- Node `v24.19.0` (already required by this repo), no npm install, no browser.
- `DOM_HARNESS_JS` lives inside `packages/multi-workers/test_decision_dashboard_assets.py`.
  It contains a ~600-line minimal DOM shim: element tree, `getElementById`,
  `createElement/createTextNode`, `setAttribute/getAttribute/removeAttribute`,
  `appendChild/replaceChildren`, `addEventListener/dispatchEvent`, and a
  single-compound selector matcher (`tag`, `#id`, `.class`, `[name="value"]`).
- The harness parses the **shipped** `decision_dashboard.html` (not a copy),
  then `vm.runInContext` loads the **shipped** `decision_dashboard.js`.
- `fetch` is mocked, but the payloads it serves are the **real**
  `/api/history`, `/api/history/<opaque>` and `/api/bootstrap` JSON captured
  from a real loopback `MonitorInstance` in the same test (tmp control root,
  real `decide_archive`/`decision_wire` writers).
- If `node` is absent the test skips with an explicit reason (would be reported
  as "DOM facility unavailable"); it is present here.

## Scenarios asserted on the rendered text

1. Boot: `#boot=one-time-boot-code` -> `POST /api/bootstrap` with
   `{"code":...}` and no token header; fragment cleared; page token only in
   closure memory (`localStorage`/`sessionStorage` traps empty); the first
   history GET carries `X-MW-Monitor-Token`; the token never appears in a URL.
2. List: 50 real rows, separate `data-claim=source/actor/answer_source` cells,
   summary/total, `未记录` for stages/calls/usage that the payload marks
   missing, no `tokens=0` for unrecorded usage, next page enabled.
3. Pagination: `#page-next` requests `offset=50&limit=50`, renders the real
   second page, `prev` enabled.
4. Filter: `key=mw-alpha` restarts at `offset=0`, rows change, and the notes
   render the emitted filter map + `filters_basis` policy. A second apply adds
   `dp=dp1-dispatch-type` and `source=model` to the same query (still offset 0),
   exercising the non-key filters end to end.
5. Detail (real payload of the newest alpha record, which has a book snapshot,
   one call/attempt and a partially captured request):
   - "决策本" with `book-v1` version and `input-memory` ref;
   - `逻辑调用` / `实际请求` / `实际返回` / call + attempt metadata;
   - `存储层` vs `本次输出层`: `output_omitted=true` note
     "本次输出省略正文", `wire_len`/`stored_len`/sha kept as stored facts;
   - record-level usage with `缺失（未补 0）`;
   - `吸收与应答` and `response-read` error;
   - unknown claims and `未记录` stages;
   - free text rendered literally (`<img ...>` XSS string present as text,
     `imgCount=0`, `PWNED` unset, no console messages).
6. Withheld filter: filtering by the known secret produces a real
   `filters_withheld=["key"]` + `filters.key=null` response; the DOM names the
   withheld slot, does **not** contain the secret value, and still renders the
   selected row.
7. Playground tab: clicking it keeps the same fetch count (no request), shows
   `待接入`, and the panel contains zero form/input/submit controls.
8. Bootstrap failure: `bad-boot-code` error banner, no history read, later
   filter/next clicks still make no history request.
9. No boot fragment: zero fetch calls, guidance mentions 引导码, no storage.
10. Contract-only labels: a hand-shaped detail payload with
    `stages.consumed.state="inferred"` and an `actor` claim whose basis says
    inferred renders `inferred（推断关联）`, `unknown`, `未记录`, and no
    `tokens=0` (this asserts the renderer contract, not a current writer).
11. Every recorded fetch URL is one of `/api/bootstrap` or `/api/history...`;
    `/api/test/*` is never requested in any snapshot.

## Not covered by this facility

- A real visible browser (Chrome/Edge window), real CSS layout/navigation,
  real `Origin`/`Sec-Fetch-Site` header emission by a browser, and DevTools
  behaviour. Real visible-browser acceptance is still not authorized (VC-006).
- Node is not a browser: `vm` execution proves the DOM/text logic, not browser
  security policy enforcement of the CSP header (the header itself is asserted
  over real HTTP, and the assets contain no inline script/handler/eval).

"""test_decision_dashboard_assets.py - T11a: the history tab assets, end to end.

Scope (card T11a):

* the monitor serves the *external* ``decision_dashboard.html/js/css`` files on
  its fixed routes (no second inline copy of the page in Python);
* ``/api/history`` forwards the read-side filter marks (``filters_withheld`` /
  ``filters_basis``) produced by the T07 fold;
* the shipped JavaScript, driven over real loopback HTTP JSON, performs the
  startup fragment exchange (boot code -> in-memory page token), clears the
  fragment, renders the project history (list/filter/pagination/detail), and
  keeps the honest labels (未记录 / unknown / inferred, no fabricated 0 usage,
  stored-capture vs this-read output layers);
* opening, refreshing and filtering never reaches the playground/model seam;
* no DOM string is injected as markup (textContent only), the CSP stays a
  closed set and there is no inline script/handler/eval;
* the DP-test tab is an honest placeholder (no submit button, no auto submit).

The DOM run uses a self-contained minimal DOM shim executed by Node (no new
dependency, no browser): the shim parses the *shipped* HTML, loads the shipped
JS in a vm context, serves the *real* monitor JSON captured over HTTP, and
records the rendered text. Real visible-browser acceptance remains separate.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import re

import pytest

import decision_monitor
import decide_archive
import decision_wire as wire

import test_decision_monitor as monitor_suite

SECRET = monitor_suite.SECRET
REDACTOR = monitor_suite.REDACTOR
HOST = decision_monitor.HOST

ASSET_NAMES = {
    "/": "decision_dashboard.html",
    "/app.css": "decision_dashboard.css",
    "/app.js": "decision_dashboard.js",
}


# ---------------------------------------------------------------------------
# Asset helpers
# ---------------------------------------------------------------------------


def _asset_text(name: str) -> str:
    return (decision_monitor.ASSET_DIR / name).read_text(encoding="utf-8")


def _asset_bytes(name: str) -> bytes:
    return (decision_monitor.ASSET_DIR / name).read_bytes()


def _html() -> str:
    return _asset_text(ASSET_NAMES["/"])


def _js() -> str:
    return _asset_text(ASSET_NAMES["/app.js"])


# ---------------------------------------------------------------------------
# Fixture: three production decisions with real archive + wire rows
# ---------------------------------------------------------------------------

XSS = '<img src=x onerror="globalThis.PWNED=1">'


def _scope(root: pathlib.Path, decision_id: str, key: str, *, secret_free: bool) -> wire.WireScope:
    return wire.WireScope(
        sink=wire.production_wire_sink(root),
        project_id=wire.project_id_for(root),
        scope_kind="production",
        origin="cli",
        decision_id=decision_id,
        dp="dp1-dispatch-type",
        key=key,
        # ``secret_free`` simulates a legacy writer that did not know this
        # secret: the text is stored verbatim, so the read-side output policy
        # must omit it (output_omitted) without touching the stored layer.
        redact=wire.SubstringRedactor(()) if secret_free else REDACTOR,
        warn=lambda message: None,
    )


def _seed_dashboard_history(root: pathlib.Path) -> dict[str, str]:
    archive = root / ".agenticdoc" / "_autopilot" / "decisions.jsonl"
    ids: dict[str, str] = {}

    def append(trigger: str, key: str, now: str, answer: dict | None) -> str:
        decision_id = f"dp1-dispatch-type:{trigger}"
        decide_archive.append_decide(
            archive,
            dp="dp1-dispatch-type",
            key=key,
            task_key=None,
            trigger_id=trigger,
            state={"a": 1},
            questions_version="q-1234abcd",
            available=True,
            authority="advisory",
            answer=answer or {"q-task": {"value": "keep"}},
            mode="auto",
            transport="timi-decisions",
            model="jev-latest",
            attempts=1,
            latency_ms=12,
            confidence=0.9,
            confidence_source="api",
            now=now,
        )
        ids[key] = decision_id
        return decision_id

    # 52 older filler decisions keep the five-row default page paginated.
    for index in range(52):
        append(f"t-fill-{index:02d}", f"mw-fill-{index:02d}", f"2026-10-22T09:{index:02d}:00+00:00", None)

    # mw-beta (the secret key) has an archive row only: no call/usage rows.
    beta = append("t-beta", SECRET, "2026-10-22T10:05:00+00:00", None)
    # mw-gamma: a clean call with a captured response and a partial usage row.
    gamma = append("t-gamma", "mw-gamma", "2026-10-22T10:10:00+00:00", None)
    # mw-alpha (newest): book snapshot, a legacy request whose stored text
    # matches the known secret at read time, and a never-captured response.
    alpha = append(
        "t-alpha",
        "mw-alpha",
        "2026-10-22T10:20:00+00:00",
        {"q-task": {"value": "fix " + XSS}},
    )

    alpha_scope = _scope(root, alpha, "mw-alpha", secret_free=True)
    call = wire.new_call()
    wire.append_event(
        alpha_scope,
        wire.book_snapshot_event(
            alpha_scope,
            book=b'{"schema_version":1,"decision_point":"dp1-dispatch-type"}',
            book_ref="input-memory",
            book_version="book-v1",
        ),
    )
    wire.record_attempt_start(
        alpha_scope,
        call,
        request=b'{"state":{"api_key":"' + SECRET.encode() + b'"}}',
        url_path="/v1/decisions",
        model="jev-latest",
    )
    wire.record_attempt_end(
        alpha_scope,
        call,
        response=wire.Capture.not_recorded(wire_len=12),
        latency_ms=5,
        http_status=200,
        usage={"input_tokens": 7},
        error_class="response-read",
    )
    wire.append_event(
        alpha_scope,
        wire.call_end_event(alpha_scope, call, attempts=1, latency_ms=9, available=True),
    )
    wire.append_event(
        alpha_scope,
        wire.decision_end_event(alpha_scope, status="ok", archive="created", call=call),
    )

    gamma_scope = _scope(root, gamma, "mw-gamma", secret_free=False)
    call2 = wire.new_call()
    wire.record_attempt_start(
        gamma_scope,
        call2,
        request=b'{"state":{"a":1}}',
        url_path="/v1/decisions",
        model="jev-latest",
    )
    wire.record_attempt_end(
        gamma_scope,
        call2,
        response=b'{"answers":{"q-task":"keep"}}',
        latency_ms=4,
        http_status=200,
        content_type="application/json",
        usage={"input_tokens": 7, "output_tokens": 3},
    )
    wire.append_event(
        gamma_scope, wire.call_end_event(gamma_scope, call2, attempts=1, latency_ms=8, available=True)
    )
    wire.append_event(
        gamma_scope, wire.decision_end_event(gamma_scope, status="ok", archive="created", call=call2)
    )
    # mw-beta has no wire rows; the two wire ids are otherwise unused here.
    ids["mw-beta"] = beta
    return ids


def _capture(instance: object, path: str, token: str) -> dict:
    status, _headers, payload, _raw = monitor_suite._http(
        instance.port, "GET", path, token=token
    )
    assert status == 200, (path, payload)
    assert payload is not None and payload["ok"] is True
    return payload


# ---------------------------------------------------------------------------
# Static asset routes (real loopback HTTP)
# ---------------------------------------------------------------------------


def test_monitor_serves_the_external_asset_files(tmp_path):
    root = monitor_suite._root(tmp_path)
    with monitor_suite._running(root, deps=decision_monitor.MonitorDeps(redactor=REDACTOR)) as instance:
        for path, name in ASSET_NAMES.items():
            status, headers, _payload, raw = monitor_suite._http(instance.port, "GET", path)
            assert status == 200, path
            assert raw == _asset_bytes(name), f"{path} must be the shipped file, not a copy"
            expected = {
                "/": "text/html",
                "/app.css": "text/css",
                "/app.js": "text/javascript",
            }[path]
            assert expected in headers.get("content-type", ""), path
            assert headers.get("x-content-type-options") == "nosniff"
            assert headers.get("cache-control") == "no-store"
            csp = headers.get("content-security-policy", "")
            assert "default-src 'none'" in csp
            assert "script-src 'self'" in csp
            assert "style-src 'self'" in csp
            assert "connect-src 'self'" in csp
            assert "unsafe-inline" not in csp
            assert "unsafe-eval" not in csp
        status, _headers, payload, _raw = monitor_suite._http(instance.port, "GET", "/app.css.map")
        assert status == 404
        assert monitor_suite._envelope_error(payload)["code"] == "not-found"


def test_monitor_has_no_second_inline_copy_of_the_page():
    assert decision_monitor.ASSET_DIR == pathlib.Path(decision_monitor.__file__).resolve().parent
    for path, name in ASSET_NAMES.items():
        assert decision_monitor.ASSET_FILES[path] == name
        content_type, text = decision_monitor.STATIC_ASSETS[path]
        assert text == _asset_text(name)
        assert content_type.startswith(
            {"/": "text/html", "/app.css": "text/css", "/app.js": "text/javascript"}[path]
        )
    # The old placeholder constants are gone: the assets are the single source.
    assert "_STATIC_HTML" not in vars(decision_monitor)
    assert "_STATIC_CSS" not in vars(decision_monitor)
    assert "_STATIC_JS" not in vars(decision_monitor)
    source = pathlib.Path(decision_monitor.__file__).read_text(encoding="utf-8")
    assert "<!doctype html>" not in source.lower()
    assert "data-tab=" not in source


def test_opening_static_assets_needs_no_token_and_reaches_no_model(tmp_path):
    root = monitor_suite._root(tmp_path)
    spy = monitor_suite._SpyPlayground()
    deps = decision_monitor.MonitorDeps(redactor=REDACTOR, playground=spy)
    with monitor_suite._running(root, deps=deps) as instance:
        for _ in range(3):
            for path in ASSET_NAMES:
                status, _headers, _payload, _raw = monitor_suite._http(instance.port, "GET", path)
                assert status == 200, path
        assert spy.calls == []


# ---------------------------------------------------------------------------
# Security-shape checks on the shipped assets
# ---------------------------------------------------------------------------


def test_assets_have_no_inline_markup_paths_or_unsafe_constructs():
    html = _html()
    js = _js()
    css = _asset_text(ASSET_NAMES["/app.css"])
    assert html.count("<script") == 1
    assert re.search(r'<script src="/app\.js"></script>', html)
    assert not re.search(r"<script(?![^>]*\bsrc=)", html)
    assert "javascript:" not in html.lower()
    assert " onclick" not in html.lower()
    assert " onerror" not in html.lower()
    style_blocks = re.findall(r"<style\b", html, flags=re.IGNORECASE)
    assert style_blocks == []
    for needle in (".innerHTML", "innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert needle not in js, needle
    assert "document.cookie" not in js
    assert "localStorage" not in js
    assert "sessionStorage" not in js
    assert "textContent" in js
    assert "X-MW-Monitor-Token" in js
    assert "@import" not in css


def test_history_envelope_forwards_the_filter_marks(tmp_path):
    root = monitor_suite._root(tmp_path)
    _seed_dashboard_history(root)
    with monitor_suite._running(root, deps=decision_monitor.MonitorDeps(redactor=REDACTOR)) as instance:
        token = monitor_suite._page_token(instance)

        plain = _capture(instance, "/api/history?limit=1", token)
        assert plain["data"]["filters_withheld"] == []
        assert isinstance(plain["data"]["filters_basis"], list)
        assert plain["data"]["filters_basis"], "the filter output policy must be stated"
        assert plain["data"]["redaction"]["enabled"] is True

        withheld = _capture(instance, "/api/history?key=" + SECRET, token)
        data = withheld["data"]
        assert data["filters_withheld"] == ["key"]
        assert data["filters"]["key"] is None
        assert SECRET not in json.dumps(withheld, ensure_ascii=False)
        assert data["total"] == 1
        assert data["records"][0]["key"] is None

        unredacted_root = monitor_suite._root(tmp_path, "unredacted")
        _seed_dashboard_history(unredacted_root)
    with monitor_suite._running(unredacted_root) as instance:
        token = monitor_suite._page_token(instance)
        plain = _capture(instance, "/api/history", token)
        assert plain["data"]["filters_withheld"] == []
        assert plain["data"]["filters_basis"], "fail-closed mode still states its basis"
        assert plain["data"]["redaction"]["enabled"] is False


# ---------------------------------------------------------------------------
# Node DOM harness (no new dependency)
# ---------------------------------------------------------------------------


DOM_HARNESS_JS = r'''"use strict";
const fs = require("node:fs");
const vm = require("node:vm");

function decodeEntities(text) {
  return text
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, "&");
}

class TextNode {
  constructor(text) { this.nodeType = 3; this._text = String(text); this.parentNode = null; }
  get textContent() { return this._text; }
  set textContent(value) { this._text = String(value); }
}

let uid = 0;
class Element {
  constructor(tagName) {
    this.nodeType = 1;
    this.tagName = String(tagName).toUpperCase();
    this.childNodes = [];
    this.parentNode = null;
    this._attrs = Object.create(null);
    this._listeners = Object.create(null);
    this._uid = ++uid;
    this.id = "";
    this.className = "";
    this.value = "";
  }
  get children() { return this.childNodes.filter((node) => node.nodeType === 1); }
  get textContent() { return this.childNodes.map((node) => node.textContent).join(""); }
  set textContent(value) {
    this.childNodes = [];
    this.childNodes.forEach((node) => { node.parentNode = null; });
    const text = value === null || value === undefined ? "" : String(value);
    if (text !== "") this.appendChild(new TextNode(text));
  }
  appendChild(node) {
    if (!node) throw new Error("appendChild(null)");
    if (node.parentNode) node.parentNode.removeChild(node);
    node.parentNode = this;
    this.childNodes.push(node);
    return node;
  }
  removeChild(node) {
    const index = this.childNodes.indexOf(node);
    if (index >= 0) {
      this.childNodes.splice(index, 1);
      node.parentNode = null;
    }
    return node;
  }
  replaceChildren(...nodes) {
    this.childNodes.forEach((node) => { node.parentNode = null; });
    this.childNodes = [];
    nodes.forEach((node) => { if (node !== null && node !== undefined) this.appendChild(node); });
  }
  remove() { if (this.parentNode) this.parentNode.removeChild(this); }
  setAttribute(name, value) {
    const key = String(name).toLowerCase();
    const text = String(value);
    this._attrs[key] = text;
    if (key === "id") this.id = text;
    if (key === "class") this.className = text;
    if (key === "value") this.value = text;
  }
  getAttribute(name) {
    const key = String(name).toLowerCase();
    return key in this._attrs ? this._attrs[key] : null;
  }
  hasAttribute(name) { return String(name).toLowerCase() in this._attrs; }
  removeAttribute(name) {
    const key = String(name).toLowerCase();
    delete this._attrs[key];
    if (key === "id") this.id = "";
    if (key === "class") this.className = "";
  }
  addEventListener(type, fn) {
    const key = String(type);
    (this._listeners[key] = this._listeners[key] || []).push(fn);
  }
  dispatchEvent(event) {
    const payload = Object.assign({
      type: "",
      target: this,
      currentTarget: this,
      defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; },
      stopPropagation() {},
    }, event || {});
    const handlers = (this._listeners[payload.type] || []).slice();
    handlers.forEach((fn) => fn(payload));
    return !payload.defaultPrevented;
  }
  click() { this.dispatchEvent({ type: "click" }); }
  submit() { this.dispatchEvent({ type: "submit" }); }
  querySelectorAll(selector) { return findAll(this, selector); }
  matches(selector) { return matchesSelector(this, selector); }
}

function matchesSelector(element, selector) {
  let rest = String(selector).trim();
  const tagMatch = /^([A-Za-z][A-Za-z0-9-]*|\*)/.exec(rest);
  if (tagMatch) {
    if (tagMatch[1] !== "*" && element.tagName.toLowerCase() !== tagMatch[1].toLowerCase()) return false;
    rest = rest.slice(tagMatch[0].length);
  }
  while (rest.length) {
    if (rest[0] === "#") {
      const match = /^#([A-Za-z0-9_-]+)/.exec(rest);
      if (!match || element.id !== match[1]) return false;
      rest = rest.slice(match[0].length);
    } else if (rest[0] === ".") {
      const match = /^\.([A-Za-z0-9_-]+)/.exec(rest);
      const classes = element.className.split(/\s+/);
      if (!match || classes.indexOf(match[1]) === -1) return false;
      rest = rest.slice(match[0].length);
    } else if (rest[0] === "[") {
      const match = /^\[([A-Za-z0-9_-]+)(?:="([^"]*)")?\]/.exec(rest);
      if (!match) return false;
      const value = element.getAttribute(match[1]);
      if (value === null) return false;
      if (match[2] !== undefined && value !== match[2]) return false;
      rest = rest.slice(match[0].length);
    } else {
      return false;
    }
  }
  return true;
}

function walk(node, visit) {
  node.childNodes.forEach((child) => {
    if (child.nodeType === 1) {
      visit(child);
      walk(child, visit);
    }
  });
}

function findAll(root, selector) {
  const found = [];
  walk(root, (element) => { if (matchesSelector(element, selector)) found.push(element); });
  return found;
}

function findFirst(root, selector) {
  let found = null;
  walk(root, (element) => {
    if (found === null && matchesSelector(element, selector)) found = element;
  });
  return found;
}

const VOID_TAGS = new Set(["meta", "link", "br", "img", "hr", "input", "source", "area", "base", "col", "embed", "param", "track", "wbr"]);

function parseHTML(source) {
  const root = new Element("#document-fragment");
  const stack = [root];
  let index = 0;
  while (index < source.length) {
    const lt = source.indexOf("<", index);
    if (lt === -1) {
      addText(source.slice(index));
      break;
    }
    if (lt > index) addText(source.slice(index, lt));
    if (source.startsWith("<!--", lt)) {
      const end = source.indexOf("-->", lt);
      index = end === -1 ? source.length : end + 3;
      continue;
    }
    if (source.startsWith("<!", lt)) {
      const end = source.indexOf(">", lt);
      index = end === -1 ? source.length : end + 1;
      continue;
    }
    const gt = source.indexOf(">", lt);
    if (gt === -1) {
      addText(source.slice(lt));
      break;
    }
    const raw = source.slice(lt + 1, gt).trim();
    if (raw.startsWith("/")) {
      const name = raw.slice(1).trim().toLowerCase();
      for (let depth = stack.length - 1; depth > 0; depth -= 1) {
        if (stack[depth].tagName.toLowerCase() === name) { stack.length = depth; break; }
      }
    } else {
      const selfClosing = raw.endsWith("/");
      const body = selfClosing ? raw.slice(0, -1) : raw;
      const tagMatch = /^([A-Za-z][A-Za-z0-9-]*)/.exec(body);
      const tag = tagMatch ? tagMatch[1] : "div";
      const element = new Element(tag);
      const attrText = body.slice(tagMatch ? tagMatch[1].length : 0);
      const attrRe = /([^\s=/>]+)(?:\s*=\s*"([^"]*)")?/g;
      let match = attrRe.exec(attrText);
      while (match !== null) {
        if (match[1]) element.setAttribute(match[1], match[2] === undefined ? "" : decodeEntities(match[2]));
        match = attrRe.exec(attrText);
      }
      stack[stack.length - 1].appendChild(element);
      if (!selfClosing && !VOID_TAGS.has(tag.toLowerCase())) stack.push(element);
    }
    index = gt + 1;
  }
  function addText(text) {
    if (text) stack[stack.length - 1].appendChild(new TextNode(decodeEntities(text)));
  }
  return root;
}

const htmlPath = process.argv[2];
const jsPath = process.argv[3];
const scenarioPath = process.argv[4];
const scenario = JSON.parse(fs.readFileSync(scenarioPath, "utf8"));
const htmlSource = fs.readFileSync(htmlPath, "utf8");

const documentRoot = parseHTML(htmlSource);
const document = {
  readyState: "complete",
  title: "mw decide monitor",
  cookie: "",
  createElement(tag) { return new Element(tag); },
  createTextNode(text) { return new TextNode(text); },
  getElementById(id) { return findFirst(documentRoot, "#" + id); },
  querySelectorAll(selector) { return findAll(documentRoot, selector); },
  addEventListener() {},
};
document.body = findFirst(documentRoot, "body");
document.documentElement = findFirst(documentRoot, "html");

const location = {
  href: "http://127.0.0.1:43170/",
  protocol: "http:",
  host: "127.0.0.1:43170",
  hostname: "127.0.0.1",
  port: "43170",
  pathname: "/",
  search: "",
  hash: scenario.hash || "",
};
const historyCalls = [];
const historyApi = {
  replaceState(_state, _title, url) {
    historyCalls.push(String(url));
    const parsed = new URL(String(url), location.href);
    location.pathname = parsed.pathname;
    location.search = parsed.search;
    location.hash = parsed.hash;
    location.href = parsed.href;
  },
};

const fetchCalls = [];
const consoleMessages = [];
const storageWrites = [];
function storageTrap(area) {
  return {
    getItem() { return null; },
    removeItem() {},
    setItem(key, value) { storageWrites.push({ area, key: String(key), value: String(value) }); },
    clear() { storageWrites.push({ area, key: "<clear>", value: "" }); },
  };
}

function responseFor(entry) {
  const status = entry && typeof entry.status === "number" ? entry.status : 200;
  const body = entry ? entry.body : { ok: false, data: null, error: { code: "no-mock", message: "no mock" } };
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get() { return null; } },
    async json() { return body; },
    async text() { return JSON.stringify(body); },
  };
}

function pickHistory(url) {
  const match = /(?:^|\?)key=([^&]*)/.exec(url);
  if (match) {
    const raw = decodeURIComponent(match[1]);
    if (scenario.historyByFilterKey && Object.prototype.hasOwnProperty.call(scenario.historyByFilterKey, raw)) {
      return scenario.historyByFilterKey[raw];
    }
  }
  const offsetMatch = /(?:^|&)offset=(\d+)/.exec(url);
  const offset = offsetMatch ? offsetMatch[1] : "0";
  if (scenario.historyByOffset && Object.prototype.hasOwnProperty.call(scenario.historyByOffset, offset)) {
    return scenario.historyByOffset[offset];
  }
  return scenario.history;
}

async function mockFetch(input, options) {
  const raw = String(input);
  const parsed = new URL(raw, location.href);
  const url = parsed.pathname + parsed.search;
  const opts = options || {};
  const headers = Object.assign({}, opts.headers || {});
  fetchCalls.push({
    url,
    method: String(opts.method || "GET").toUpperCase(),
    headers,
    body: opts.body === undefined || opts.body === null ? null : String(opts.body),
  });
  if (url === "/api/bootstrap") {
    return responseFor(scenario.bootstrap);
  }
  if (url.startsWith("/api/history/")) {
    return responseFor(scenario.detail);
  }
  if (url.startsWith("/api/history")) {
    const entry = pickHistory(url);
    if (!entry) return responseFor({ status: 404, body: { ok: false, data: null, error: { code: "no-mock" } } });
    return responseFor(entry);
  }
  return responseFor({ status: 404, body: { ok: false, data: null, error: { code: "unexpected-route", message: url } } });
}

const sandbox = {
  document,
  location,
  history: historyApi,
  fetch: mockFetch,
  URL,
  URLSearchParams,
  setTimeout,
  clearTimeout,
  setInterval,
  clearInterval,
  console: {
    log(...args) { consoleMessages.push(["log", args.map(String)]); },
    warn(...args) { consoleMessages.push(["warn", args.map(String)]); },
    error(...args) { consoleMessages.push(["error", args.map(String)]); },
  },
  localStorage: storageTrap("localStorage"),
  sessionStorage: storageTrap("sessionStorage"),
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.self = sandbox;

function nodeText(id) {
  const node = document.getElementById(id);
  return node ? node.textContent : null;
}
function hasAttr(id, name) {
  const node = document.getElementById(id);
  return Boolean(node && node.hasAttribute(name));
}
function cellTexts(attribute) {
  return document.querySelectorAll("[" + attribute + "]").map((node) => node.textContent);
}
function snapshot(label) {
  const rows = document.querySelectorAll('[data-testid="record-row"]');
  return {
    label,
    hash: location.hash,
    href: location.href,
    fetchCalls: fetchCalls.map((call) => ({
      url: call.url,
      method: call.method,
      headers: Object.assign({}, call.headers),
      body: call.body,
    })),
    storage: storageWrites.slice(),
    consoleMessages: consoleMessages.slice(),
    bootStatus: nodeText("boot-status"),
    error: nodeText("error-banner"),
    summary: nodeText("history-summary"),
    filterNotes: nodeText("filters-notes"),
    pageInfo: nodeText("page-info"),
    rowCount: rows.length,
    rows: rows.map((row) => row.textContent),
    sourceClaims: cellTexts('data-claim="source"'),
    actorClaims: cellTexts('data-claim="actor"'),
    answerClaims: cellTexts('data-claim="answer_source"'),
    detailText: nodeText("detail-body"),
    detailVisible: !hasAttr("detail-panel", "hidden"),
    playgroundVisible: !hasAttr("panel-playground", "hidden"),
    playgroundText: nodeText("panel-playground"),
    playgroundForms: document.querySelectorAll('#panel-playground form, #panel-playground input, #panel-playground button[type="submit"]').length,
    nextDisabled: hasAttr("page-next", "disabled"),
    prevDisabled: hasAttr("page-prev", "disabled"),
    imgCount: document.querySelectorAll("img").length,
    scriptTags: document.querySelectorAll("script").length,
    pwned: Boolean(sandbox.PWNED),
    bodyText: document.body ? document.body.textContent : "",
  };
}

async function drain() {
  for (let index = 0; index < 20; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

function find(selector) {
  const node = findFirst(documentRoot, selector);
  if (!node) throw new Error("selector not found: " + selector);
  return node;
}

async function run() {
  const vmContext = vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(jsPath, "utf8"), vmContext, { filename: jsPath, timeout: 20000 });
  await drain();
  const snapshots = [snapshot("boot")];
  for (const step of scenario.steps || []) {
    if (step.type === "click") {
      find(step.target).click();
    } else if (step.type === "setValue") {
      find(step.target).value = String(step.value);
    } else if (step.type === "submit") {
      find(step.target).submit();
    } else if (step.type === "snapshot") {
      snapshots.push(snapshot(step.label || "step"));
      continue;
    } else {
      throw new Error("unknown step " + JSON.stringify(step));
    }
    await drain();
    if (step.snapshot) snapshots.push(snapshot(step.snapshot));
  }
  return { ok: true, snapshots, fetchCalls, storageWrites, location: { hash: location.hash, href: location.href }, historyCalls };
}

run().then((result) => {
  process.stdout.write(JSON.stringify(result));
}).catch((error) => {
  process.stdout.write(JSON.stringify({
    ok: false,
    error: String((error && error.stack) || error),
    snapshots: [],
    fetchCalls,
    storageWrites,
  }));
  process.exitCode = 1;
});
'''


def _run_dom(tmp_path: pathlib.Path, scenario: dict) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is unavailable: the DOM behaviour cannot be exercised in this environment")
    work = tmp_path / "dom"
    work.mkdir(parents=True, exist_ok=True)
    harness = work / "dom_harness.cjs"
    harness.write_text(DOM_HARNESS_JS, encoding="utf-8")
    scenario_path = work / "scenario.json"
    scenario_path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
    process = subprocess.run(
        [
            node,
            str(harness),
            str(decision_monitor.ASSET_DIR / ASSET_NAMES["/"]),
            str(decision_monitor.ASSET_DIR / ASSET_NAMES["/app.js"]),
            str(scenario_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(work),
        timeout=180,
    )
    assert process.stdout, f"node produced no output (stderr={process.stderr})"
    assert process.returncode == 0, (
        f"node exit={process.returncode}\n" + process.stdout + "\n--- stderr ---\n" + process.stderr
    )
    result = json.loads(process.stdout.strip().splitlines()[-1])
    assert result.get("ok") is True, (
        process.stdout
        + "\n--- stderr ---\n"
        + process.stderr
    )
    return result


def _snapshot(result: dict, label: str) -> dict:
    for snapshot in result["snapshots"]:
        if snapshot["label"] == label:
            return snapshot
    raise AssertionError(f"missing snapshot {label}: {[s['label'] for s in result['snapshots']]}")


def _all_text(result: dict) -> str:
    return "\n".join(snapshot["bodyText"] for snapshot in result["snapshots"])


# ---------------------------------------------------------------------------
# DOM behaviour over the real monitor JSON
# ---------------------------------------------------------------------------


def _dom_payload(tmp_path: pathlib.Path, root: pathlib.Path, instance: object):
    token = monitor_suite._page_token(instance)
    default = _capture(instance, "/api/history?limit=5", token)
    next_page = _capture(instance, "/api/history?limit=5&offset=5", token)
    alpha = _capture(instance, "/api/history?key=mw-alpha", token)
    withheld = _capture(instance, "/api/history?key=" + SECRET, token)
    opaque = alpha["data"]["records"][0]["opaque_id"]
    detail = _capture(instance, f"/api/history/{opaque}", token)
    return {
        "token": token,
        "default": default,
        "next": next_page,
        "alpha": alpha,
        "withheld": withheld,
        "detail": detail,
        "opaque": opaque,
    }


def test_dashboard_boot_list_filter_pagination_and_detail_dom(tmp_path):
    root = monitor_suite._root(tmp_path)
    ids = _seed_dashboard_history(root)
    with monitor_suite._running(root, deps=decision_monitor.MonitorDeps(redactor=REDACTOR)) as instance:
        payloads = _dom_payload(tmp_path, root, instance)

    scenario = {
        "hash": "#boot=one-time-boot-code",
        "bootstrap": {
            "status": 200,
            "body": {"ok": True, "data": {"page_token": payloads["token"]}, "error": None, "capture_status": None},
        },
        "history": {"status": 200, "body": payloads["default"]},
        "historyByOffset": {"5": {"status": 200, "body": payloads["next"]}},
        "historyByFilterKey": {
            "mw-alpha": {"status": 200, "body": payloads["alpha"]},
            SECRET: {"status": 200, "body": payloads["withheld"]},
        },
        "detail": {"status": 200, "body": payloads["detail"]},
        "steps": [
            {"type": "click", "target": "#page-next", "snapshot": "after-next"},
            {"type": "setValue", "target": "#filter-key", "value": "mw-alpha"},
            {"type": "click", "target": "#filter-apply", "snapshot": "after-filter"},
            {"type": "setValue", "target": "#filter-dp", "value": "dp1-dispatch-type"},
            {"type": "setValue", "target": "#filter-source", "value": "model"},
            {"type": "click", "target": "#filter-apply", "snapshot": "after-more-filters"},
            {"type": "click", "target": '[data-testid="record-open"]', "snapshot": "detail"},
            {"type": "click", "target": "#detail-close"},
            {"type": "setValue", "target": "#filter-key", "value": SECRET},
            {"type": "click", "target": "#filter-apply", "snapshot": "withheld-filter"},
            {"type": "click", "target": "#tab-playground", "snapshot": "playground"},
        ],
    }
    result = _run_dom(tmp_path, scenario)

    boot = _snapshot(result, "boot")
    # Startup exchange: POST bootstrap with the fragment code, then a page-token GET.
    assert boot["fetchCalls"][0]["method"] == "POST"
    assert boot["fetchCalls"][0]["url"] == "/api/bootstrap"
    assert json.loads(boot["fetchCalls"][0]["body"]) == {"code": "one-time-boot-code"}
    assert "X-MW-Monitor-Token" not in boot["fetchCalls"][0]["headers"]
    assert boot["hash"] == "", "the boot fragment must be cleared"
    assert "#boot=" not in boot["href"]
    assert boot["storage"] == [], "the page token must stay in memory, never in web storage"
    assert "已通过一次性引导码" in (boot["bootStatus"] or "")
    assert boot["error"] in (None, "")
    history_calls = [call for call in boot["fetchCalls"] if call["url"].startswith("/api/history")]
    assert len(history_calls) == 1
    assert history_calls[0]["headers"].get("X-MW-Monitor-Token") == payloads["token"]
    assert payloads["token"] not in history_calls[0]["url"]
    assert "limit=5" in history_calls[0]["url"] and "offset=0" in history_calls[0]["url"]
    assert "scope=production" in history_calls[0]["url"]
    # List rows: the default page, honest labels.
    assert boot["rowCount"] == 5
    # The list does not render a provenance column at all (it never fabricates
    # one); the three separate claims render in the detail view, asserted below.
    assert boot["sourceClaims"] == [] and boot["actorClaims"] == []
    assert boot["answerClaims"] == []
    assert str(payloads["default"]["data"]["total"]) in (boot["summary"] or "")
    assert any("未记录" in row for row in boot["rows"]), boot["rows"]
    for record, row in zip(payloads["default"]["data"]["records"], boot["rows"]):
        if record["usage"]["recorded"] is not True:
            assert "未记录" in row
            assert "tokens=0" not in row, "an absent usage counter is never filled with 0"
    assert boot["nextDisabled"] is False
    assert boot["prevDisabled"] is True
    assert payloads["default"]["data"]["has_more"] is True
    # The shipped CSS selector hooks exist and the playground tab is honest.
    assert boot["playgroundVisible"] is False

    after_next = _snapshot(result, "after-next")
    next_calls = [call for call in after_next["fetchCalls"] if call["url"].startswith("/api/history")]
    assert len(next_calls) == 2
    assert "offset=5" in next_calls[-1]["url"] and "limit=5" in next_calls[-1]["url"]
    assert after_next["rowCount"] == len(payloads["next"]["data"]["records"])
    assert after_next["rows"] != boot["rows"]
    assert after_next["prevDisabled"] is False

    after_filter = _snapshot(result, "after-filter")
    filter_calls = [call for call in after_filter["fetchCalls"] if call["url"].startswith("/api/history")]
    assert "key=mw-alpha" in filter_calls[-1]["url"]
    assert "offset=0" in filter_calls[-1]["url"], "a new filter restarts at offset 0"
    assert after_filter["rowCount"] == 1
    assert "mw-alpha" in after_filter["rows"][0]
    assert after_filter["filterNotes"] in (None, ""), "debug filter prose is not normal UI"
    assert payloads["alpha"]["data"]["filters_basis"], "API retains filter provenance"

    after_more = _snapshot(result, "after-more-filters")
    more_calls = [call for call in after_more["fetchCalls"] if call["url"].startswith("/api/history")]
    assert "key=mw-alpha" in more_calls[-1]["url"]
    assert "dp=dp1-dispatch-type" in more_calls[-1]["url"]
    assert "source=model" in more_calls[-1]["url"]
    assert "offset=0" in more_calls[-1]["url"]
    assert after_more["rowCount"] == 1

    detail = _snapshot(result, "detail")
    # Minimal logs omit provenance columns, but the API retains the facts.
    assert detail["sourceClaims"] == detail["actorClaims"] == detail["answerClaims"] == []
    assert all(name in payloads["detail"]["data"] for name in ("source", "actor", "answer_source"))
    detail_calls = [call for call in detail["fetchCalls"] if call["url"].startswith("/api/history/")]
    assert len(detail_calls) == 1
    assert detail_calls[0]["url"] == "/api/history/" + payloads["opaque"]
    assert detail_calls[0]["headers"].get("X-MW-Monitor-Token") == payloads["token"]
    text = detail["detailText"] or ""
    assert detail["detailVisible"] is True
    assert "实际请求" in text and "实际返回" in text
    assert all(hidden not in text for hidden in ("决策本", "book-v1", "input-memory", "wire_len", "stored_len"))
    request = payloads["detail"]["data"]["calls"][0]["attempts"][0]["request"]
    assert request["output_omitted"] is True, "the read policy retains its omission fact"
    assert "本次输出省略正文" in text
    assert SECRET not in text, "an output-omitted capture must not leak the stored secret"
    assert "未记录" in text and "tokens=0" not in text
    assert "接收与处理结果" in text
    assert "response-read" in text
    # Inferred/unknown/missing honesty in the claims/stages tables.
    assert "未记录" in text
    assert XSS in text, "free text is rendered literally"
    assert detail["imgCount"] == 0 and detail["pwned"] is False
    assert detail["consoleMessages"] == []

    withheld = _snapshot(result, "withheld-filter")
    withheld_text = withheld["bodyText"] or ""
    assert withheld["rowCount"] == 1
    assert SECRET not in withheld_text, "the withheld filter value must not be echoed into the DOM"
    assert withheld["filterNotes"] in (None, "")
    assert "部分详情因安全限制未显示" in withheld_text
    assert payloads["withheld"]["data"]["filters_withheld"] == ["key"]
    assert withheld["consoleMessages"] == []

    playground = _snapshot(result, "playground")
    assert playground["playgroundVisible"] is True
    assert "待接入" in (playground["playgroundText"] or "")
    assert playground["playgroundForms"] == 0
    before_playground = len(playground["fetchCalls"])
    added = playground["fetchCalls"][len(withheld["fetchCalls"]):]
    assert added == [{"url": "/api/dps", "method": "GET", "headers": {"X-MW-Monitor-Token": payloads["token"]}, "body": None}], added
    assert before_playground == len(withheld["fetchCalls"]) + 1
    assert "DP 契约加载失败" in playground["playgroundText"], "missing mock fails honestly"

    # Tab entry adds read-only metadata; no observation POST is allowed.
    for snapshot in result["snapshots"]:
        for call in snapshot["fetchCalls"]:
            assert not call["url"].startswith("/api/test/"), call["url"]
            assert call["url"] in ("/api/bootstrap", "/api/dps") or call["url"].startswith("/api/history"), call["url"]
            assert call["url"] != "/api/dps" or call["method"] == "GET"
            assert "boot=one-time-boot-code" not in call["url"]
            assert payloads["token"] not in call["url"]
    assert ids["mw-alpha"] in json.dumps(payloads["alpha"], ensure_ascii=False)


def test_dashboard_renders_inferred_unknown_and_missing_without_fabrication(tmp_path):
    """The renderer contract for labels the current fold may not emit yet.

    ``inferred`` / ``unknown`` / ``未记录`` are part of the T07 payload contract;
    a hand-shaped (contract-only) payload proves the DOM path labels them
    instead of inventing a value. It does not claim that a current writer emits
    ``inferred``.
    """
    root = monitor_suite._root(tmp_path)
    _seed_dashboard_history(root)
    with monitor_suite._running(root, deps=decision_monitor.MonitorDeps(redactor=REDACTOR)) as instance:
        payloads = _dom_payload(tmp_path, root, instance)

    detail = json.loads(json.dumps(payloads["detail"]))
    data = detail["data"]
    data["stages"]["consumed"] = {
        "state": "inferred",
        "basis": ["ledger.call-id inferred link"],
        "ts": None,
        "detail": "association inferred, not a recorded receipt",
        "event_id": None,
        "actor": None,
        "answer_source": None,
        "target": None,
        "supersedes": None,
        "result": None,
    }
    data["actor"] = {"value": None, "basis": ["inferred from a call_id, not a recorded actor"]}
    data["usage"] = {
        "recorded": False,
        "counters": {},
        "missing": [],
        "complete": False,
        "semantics": "none",
        "attempts_with_usage": 0,
        "conflicting": False,
        "basis": ["no usage rows"],
    }
    scenario = {
        "hash": "#boot=render-contract",
        "bootstrap": {
            "status": 200,
            "body": {"ok": True, "data": {"page_token": "page-token-only-in-memory"}, "error": None, "capture_status": None},
        },
        "history": {"status": 200, "body": payloads["default"]},
        "detail": {"status": 200, "body": detail},
        "steps": [
            {"type": "click", "target": '[data-testid="record-open"]', "snapshot": "detail"},
        ],
    }
    result = _run_dom(tmp_path, scenario)
    snapshot = _snapshot(result, "detail")
    text = snapshot["detailText"] or ""
    assert "inferred（推断关联）" in text
    assert "未记录" in text
    assert data["actor"]["value"] is None and data["usage"]["recorded"] is False
    assert "来源（分列）" not in text
    assert "tokens=0" not in text, "a missing usage row is never filled with 0"
    assert snapshot["storage"] == []


def test_dashboard_bootstrap_failure_is_explicit_and_makes_no_reads(tmp_path):
    scenario = {
        "hash": "#boot=expired-code",
        "bootstrap": {
            "status": 401,
            "body": {
                "ok": False,
                "data": None,
                "error": {"code": "bad-boot-code", "message": "the boot code is unknown or expired"},
                "capture_status": None,
            },
        },
        "steps": [
            {"type": "click", "target": "#filter-apply", "snapshot": "after-click"},
            {"type": "click", "target": "#page-next", "snapshot": "after-next"},
        ],
    }
    result = _run_dom(tmp_path, scenario)
    boot = _snapshot(result, "boot")
    assert boot["hash"] == ""
    assert "bad-boot-code" in (boot["error"] or "")
    assert "引导失败" in (boot["bootStatus"] or "")
    assert all(not call["url"].startswith("/api/history") for call in boot["fetchCalls"])
    assert boot["rowCount"] == 0
    after = _snapshot(result, "after-next")
    assert all(not call["url"].startswith("/api/history") for call in after["fetchCalls"])


def test_dashboard_without_a_boot_code_makes_no_request(tmp_path):
    scenario = {"hash": "", "steps": []}
    result = _run_dom(tmp_path, scenario)
    boot = _snapshot(result, "boot")
    assert boot["fetchCalls"] == []
    assert "引导码" in (boot["bootStatus"] or "")
    assert boot["storage"] == []

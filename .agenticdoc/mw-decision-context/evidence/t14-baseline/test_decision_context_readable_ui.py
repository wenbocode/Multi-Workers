"""test_decision_context_readable_ui.py - T11: the readable decision workbench.

Card ``T11-readable-ui`` / spec AC-015 (revised), AC-021..AC-024. This file is
the *behavioural* acceptance of the shipped ``decision_dashboard.{html,js,css}``:

* AC-021: the ten approved nodes are a real directed graph (SVG edge layer +
  positioned node controls), every node is clickable and shows the readable
  detail of *this* decision, and no vertical list is passed off as a DAG;
* AC-022: the input node shows only the business material (never the book
  wrapper/ref/hash/version/mode/intent/basis); request/response show the stored
  capture text, JSON prettified, non-JSON verbatim, and the copy button copies
  the *original* captured string (not the formatted view);
* AC-023: a below-threshold API confidence is explained as "not adopted" with
  the documented selection/confidence/effective threshold/human fallback, a
  missing threshold stays "not recorded", and an HTTP 200 is never called an
  API failure;
* AC-024: the four offline cases load their complete native questions, the
  state and instructions (criteria for non-dp3) are editable, the dp3 criteria
  stays a read-only derivation of ``state.handling_options``, the validate
  request carries ``questions`` and the page shows the server's own
  ``request_preview`` (model/state/questions), and nothing but the explicit
  observe-only submission ever leaves the page.

The run uses a self-contained Node DOM shim (no browser, no new dependency):
it parses the *shipped* HTML, executes the *shipped* JS in a vm context, feeds
JSON captured from a real loopback monitor where the shape exists today, and a
clearly-labelled published-interface fixture for the T10 fields (``material``,
``policy_result``, ``case.questions``, ``request_preview``) that have not been
published yet. Real visible-browser / real-model acceptance stays a separate,
unauthorized layer.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import subprocess

import pytest

import decision_monitor

import test_decision_context_readable_backend as backend_suite
import test_decision_dashboard_assets as assets_suite
import test_decision_context_workbench as wb
import test_decision_monitor as monitor_suite

SECRET = monitor_suite.SECRET
REDACTOR = monitor_suite.REDACTOR

ASSET_DIR = pathlib.Path(decision_monitor.__file__).resolve().parent
CASES_DIR = ASSET_DIR / "decide_cases"
NODE_IDS = list(wb.NODE_IDS)
STATES = list(wb.STATES)

HTML_NAME = "decision_dashboard.html"
JS_NAME = "decision_dashboard.js"
CSS_NAME = "decision_dashboard.css"

#: The published-interface fixture marker: the T10 backend lane has not written
#: its ``progress.md`` yet, so these fields are asserted against the interface
#: the card fixed (``detail.material`` / ``detail.policy_result`` /
#: ``case.questions`` / ``request_preview``), not against a producer run.
FIXTURE_NOTE = "published-interface fixture (T10 progress not yet published)"


# ---------------------------------------------------------------------------
# Isolation (same discipline as the other dashboard suites)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_environment(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(home / "pi-agent"))
    for name in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "TIMI_API_KEY",
        "TIMI_BASE_URL",
        "MW_DECIDE_API_KEY",
        "MW_DECISION_API_KEY",
        "PI_API_KEY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "PI_WORKER_TASK",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


# ---------------------------------------------------------------------------
# Node DOM harness (self-contained: SVG namespace, clipboard spy, keyboard)
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

const SVG_NS = "http://www.w3.org/2000/svg";
let activeElement = null;

class Element {
  constructor(tagName) {
    this.nodeType = 1;
    this.tagName = String(tagName).toUpperCase();
    this.childNodes = [];
    this.parentNode = null;
    this._attrs = Object.create(null);
    this._listeners = Object.create(null);
    this.id = "";
    this.className = "";
    this.value = "";
    this.namespaceURI = "http://www.w3.org/1999/xhtml";
    this.selected = false;
  }
  get children() { return this.childNodes.filter((node) => node.nodeType === 1); }
  get textContent() { return this.childNodes.map((node) => node.textContent).join(""); }
  set textContent(value) {
    this.childNodes.forEach((node) => { node.parentNode = null; });
    this.childNodes = [];
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
    if (index >= 0) { this.childNodes.splice(index, 1); node.parentNode = null; }
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
    (this._listeners[payload.type] || []).slice().forEach((fn) => fn(payload));
    return !payload.defaultPrevented;
  }
  click() { this.dispatchEvent({ type: "click" }); }
  submit() { this.dispatchEvent({ type: "submit" }); }
  focus() { activeElement = this; }
  select() {}
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
    if (child.nodeType === 1) { visit(child); walk(child, visit); }
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
    if (lt === -1) { addText(source.slice(index)); break; }
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
    if (gt === -1) { addText(source.slice(lt)); break; }
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
  get activeElement() { return activeElement; },
  createElement(tag) { return new Element(tag); },
  createElementNS(namespace, tag) {
    const node = new Element(tag);
    node.namespaceURI = String(namespace);
    return node;
  },
  createTextNode(text) { return new TextNode(text); },
  getElementById(id) { return findFirst(documentRoot, "#" + id); },
  querySelectorAll(selector) { return findAll(documentRoot, selector); },
  execCommand() { return false; },
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
const historyApi = {
  replaceState(_state, _title, url) {
    const parsed = new URL(String(url), location.href);
    location.pathname = parsed.pathname;
    location.search = parsed.search;
    location.hash = parsed.hash;
    location.href = parsed.href;
  },
};

const fetchCalls = [];
const timers = new Map();
const timerDelays = [];
const deferred = new Map();
let timerSeq = 0;
function fakeTimeout(fn, delay) {
  const id = ++timerSeq;
  timerDelays.push(delay);
  timers.set(id, {fn, delay});
  return id;
}
const consoleMessages = [];
const storageWrites = [];
const clipboardWrites = [];
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
  const keyMatch = /(?:^|[?&])key=([^&]*)/.exec(url);
  if (keyMatch) {
    const raw = decodeURIComponent(keyMatch[1]);
    const table = scenario.historyByFilterKey || {};
    if (Object.prototype.hasOwnProperty.call(table, raw)) return table[raw];
  }
  const offsetMatch = /(?:^|[?&])offset=(\d+)/.exec(url);
  const offset = offsetMatch ? offsetMatch[1] : "0";
  if (scenario.historyByOffset && Object.prototype.hasOwnProperty.call(scenario.historyByOffset, offset)) {
    return scenario.historyByOffset[offset];
  }
  return scenario.history;
}

function routeFor(url) {
  if (url === "/api/bootstrap") return scenario.bootstrap;
  if (url.startsWith("/api/history/")) {
    const opaque = decodeURIComponent(url.slice("/api/history/".length));
    const table = scenario.detailByOpaque || {};
    if (Object.prototype.hasOwnProperty.call(table, opaque)) return table[opaque];
    return scenario.detail;
  }
  if (url.startsWith("/api/history")) return pickHistory(url);
  if (url.startsWith("/api/test/cases")) return scenario.cases;
  if (url === "/api/dps") return scenario.dps;
  if (url === "/api/test/history") return scenario.testHistory;
  if (url === "/api/test/validate") return scenario.validate;
  if (url === "/api/test/submit") return scenario.submit;
  if (url.startsWith("/api/test/submissions/")) return scenario.submission;
  if (url === "/api/test/scaffold") return scenario.scaffold;
  return undefined;
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
  let entry = routeFor(url);
  if (Array.isArray(entry)) entry = entry.shift();
  if (entry && entry.defer) {
    return new Promise((resolve) => deferred.set(entry.defer, () => resolve(responseFor(entry))));
  }
  if (!entry) {
    return responseFor({ status: 404, body: { ok: false, data: null, error: { code: "unexpected-route", message: url } } });
  }
  return responseFor(entry);
}

const sandbox = {
  document,
  location,
  history: historyApi,
  fetch: mockFetch,
  URL,
  URLSearchParams,
  setTimeout: fakeTimeout,
  clearTimeout: (id) => timers.delete(id),
  console: {
    log(...args) { consoleMessages.push(["log", args.map(String)]); },
    warn(...args) { consoleMessages.push(["warn", args.map(String)]); },
    error(...args) { consoleMessages.push(["error", args.map(String)]); },
  },
  localStorage: storageTrap("localStorage"),
  sessionStorage: storageTrap("sessionStorage"),
  navigator: {
    clipboard: {
      writeText(text) { clipboardWrites.push(String(text)); return Promise.resolve(); },
    },
  },
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
function texts(testid) { return findAll(documentRoot, '[data-testid="' + testid + '"]').map((node) => node.textContent); }
function attrs(testid, name) {
  return findAll(documentRoot, '[data-testid="' + testid + '"]').map((node) => node.getAttribute(name));
}
function values(testid) {
  return findAll(documentRoot, '[data-testid="' + testid + '"]').map((node) => String(node.value === undefined ? "" : node.value));
}
function headersOf(testid) {
  const table = findFirst(documentRoot, '[data-testid="' + testid + '"]');
  return table ? findAll(table, "th").map((node) => node.textContent) : [];
}
function captureBlocks() {
  return findAll(documentRoot, '[data-testid="capture-block"]').map((block) => {
    const pre = findFirst(block, '[data-testid="capture-text"]');
    const copy = findFirst(block, '[data-testid="capture-copy"]');
    return {
      scope: block.getAttribute("data-scope"),
      capture: block.getAttribute("data-capture"),
      attempt: block.getAttribute("data-attempt"),
      format: block.getAttribute("data-format"),
      status: block.getAttribute("data-status"),
      statusText: nodeTextOf(findFirst(block, '[data-testid="capture-status"]')),
      text: pre ? pre.textContent : null,
      copyPrompt: copy ? copy.textContent : null,
      copyStatus: nodeTextOf(findFirst(block, '[data-testid="capture-copy-status"]')),
    };
  });
}
function nodeTextOf(node) { return node ? node.textContent : null; }
function graphOf(prefix) {
  const nodes = findAll(documentRoot, '[data-testid="' + prefix + '-node"]');
  const edges = findAll(documentRoot, '[data-testid="' + prefix + '-node-edge"]');
  return {
    nodes: nodes.map((node) => ({
      id: node.getAttribute("data-node-id"),
      step: node.getAttribute("data-step"),
      state: node.getAttribute("data-node-state"),
      position: node.getAttribute("data-pos"),
      kind: node.tagName,
      pressed: node.getAttribute("aria-pressed"),
      text: node.textContent,
    })),
    edges: edges.map((edge) => ({
      from: edge.getAttribute("data-from"),
      to: edge.getAttribute("data-to"),
      order: edge.getAttribute("data-order"),
      marker: edge.getAttribute("marker-end"),
      ariaHidden: edge.getAttribute("aria-hidden"),
      kind: edge.tagName,
      namespace: edge.namespaceURI,
      x1: edge.getAttribute("x1"),
      y1: edge.getAttribute("y1"),
      x2: edge.getAttribute("x2"),
      y2: edge.getAttribute("y2"),
    })),
    svgCount: findAll(documentRoot, "svg").length,
    legacyListCount: findAll(documentRoot, "ol.dag").length,
    note: nodeText("dag-graph-note"),
  };
}
function questionsOf() {
  return findAll(documentRoot, '[data-testid="pg-question"]').map((block) => {
    const instructions = findFirst(block, '[data-testid="pg-question-instructions"]');
    const criteriaInput = findFirst(block, '[data-testid="pg-question-criteria-input"]');
    const derived = findFirst(block, '[data-testid="pg-question-criteria-derived"]');
    return {
      id: block.getAttribute("data-question-id"),
      kind: block.getAttribute("data-kind"),
      instructions: instructions ? String(instructions.value) : null,
      criteriaInput: criteriaInput ? String(criteriaInput.value) : null,
      derived: derived ? derived.textContent : null,
      text: block.textContent,
    };
  });
}
function previewOf() {
  const holder = findFirst(documentRoot, '[data-testid="pg-request-preview"]');
  if (!holder) return null;
  const part = function (testid) {
    const node = findFirst(holder, '[data-testid="' + testid + '"]');
    return node ? node.textContent : null;
  };
  return {
    present: true,
    model: part("pg-preview-model"),
    state: part("pg-preview-state"),
    questions: part("pg-preview-questions"),
    text: holder.textContent,
  };
}
function snapshot(label) {
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
    clipboard: clipboardWrites.slice(),
    activeElement: activeElement ? (activeElement.getAttribute("data-node-id") || activeElement.id || null) : null,
    portText: nodeText("monitor-port"),
    materialValue: (document.getElementById("material-editor") || {value: ""}).value,
    bootStatus: nodeText("boot-status"),
    error: nodeText("error-banner"),
    summary: nodeText("history-summary"),
    headers: headersOf("workbench-table"),
    rowCount: findAll(documentRoot, '[data-testid="record-row"]').length,
    rows: texts("record-row"),
    stateValues: attrs("record-state", "data-processing-state"),
    dialogVisible: !hasAttr("record-dialog", "hidden"),
    dagTabDisabled: hasAttr("record-dialog-tab-dag", "disabled"),
    dagPanelVisible: !hasAttr("record-dialog-dag-panel", "hidden"),
    dagSummary: nodeText("record-dialog-dag-summary"),
    legacyNote: nodeText("record-dialog-legacy-note"),
    dialogMeta: nodeText("record-dialog-meta"),
    graph: graphOf("dag"),
    graphContainer: (document.getElementById("dag-graph") || {}).className || null,
    nodeDetail: nodeText("dag-node-detail"),
    nodeDetailId: (document.getElementById("dag-node-detail") || { getAttribute() { return null; } }).getAttribute("data-node-id"),
    nodeDetailIsSide: Boolean(
      document.getElementById("dag-node-detail") &&
      document.getElementById("dag-node-detail").parentNode &&
      String(document.getElementById("dag-node-detail").parentNode.className || "").indexOf("dag-layout") !== -1
    ),
    logVisible: !hasAttr("record-dialog-log-panel", "hidden"),
    logText: nodeText("detail-body"),
    logSections: findAll(documentRoot, '[data-testid="log-section"]').map(function (section) {
      const heading = findFirst(section, "h3");
      return heading ? heading.textContent : null;
    }),
    captures: captureBlocks(),
    editorValue: (document.getElementById("book-editor") || { value: "" }).value,
    questions: questionsOf(),
    questionsStatus: nodeText("pg-questions-status"),
    preview: previewOf(),
    validateText: nodeText("pg-validate-out"),
    submitText: nodeText("pg-submit-out"),
    playgroundVisible: !hasAttr("panel-playground", "hidden"),
    pgGraph: graphOf("pg-dag"),
    pgNodeDetail: nodeText("pg-dag-node-detail"),
    pgStatus: nodeText("playground-status"),
    pgOperations: nodeText("pg-operation-rows"),
    pgHistory: nodeText("pg-history-rows"),
    activeTimers: timers.size,
    timerDelays: timerDelays.slice(),
    submitDisabled: hasAttr("pg-submit", "disabled"),
    imgCount: findAll(documentRoot, "img").length,
    scriptTags: findAll(documentRoot, "script").length,
    pwned: Boolean(sandbox.PWNED),
    bodyText: document.body ? document.body.textContent : "",
  };
}

async function drain() {
  for (let index = 0; index < 30; index += 1) {
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
    if (step.type === "tick") {
      const pending = [...timers.entries()];
      timers.clear();
      pending.forEach(([, timer]) => timer.fn());
    } else if (step.type === "release") {
      const resolve = deferred.get(step.id);
      if (!resolve) throw new Error("missing deferred " + step.id);
      deferred.delete(step.id);
      resolve();
    } else if (step.type === "click") {
      find(step.target).click();
    } else if (step.type === "setValue") {
      find(step.target).value = String(step.value);
    } else if (step.type === "dispatch") {
      find(step.target).dispatchEvent(Object.assign({}, step.event || {}));
    } else if (step.type === "submit") {
      find(step.target).submit();
    } else {
      throw new Error("unknown step " + JSON.stringify(step));
    }
    await drain();
    if (step.snapshot) snapshots.push(snapshot(step.snapshot));
  }
  return { ok: true, snapshots, fetchCalls, storageWrites, clipboardWrites };
}

run().then((result) => {
  process.stdout.write(JSON.stringify(result));
}).catch((error) => {
  process.stdout.write(JSON.stringify({
    ok: false,
    error: String((error && error.stack) || error),
    snapshots: [],
    fetchCalls,
    clipboardWrites,
  }));
  process.exitCode = 1;
});
'''


def _run_dom(tmp_path: pathlib.Path, scenario: dict) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is unavailable: the DOM behaviour cannot be exercised here")
    work = tmp_path / "readable-dom"
    work.mkdir(parents=True, exist_ok=True)
    harness = work / "dom_harness.cjs"
    harness.write_text(DOM_HARNESS_JS, encoding="utf-8")
    scenario_path = work / "scenario.json"
    scenario_path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
    process = subprocess.run(
        [
            node,
            str(harness),
            str(ASSET_DIR / HTML_NAME),
            str(ASSET_DIR / JS_NAME),
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
    assert result.get("ok") is True, process.stdout + "\n--- stderr ---\n" + process.stderr
    return result


def _snapshot(result: dict, label: str) -> dict:
    for snapshot in result["snapshots"]:
        if snapshot["label"] == label:
            return snapshot
    raise AssertionError(f"missing snapshot {label}: {[s['label'] for s in result['snapshots']]}")


def _envelope(data: object) -> dict:
    return {"ok": True, "data": data, "error": None, "capture_status": None}


# ---------------------------------------------------------------------------
# Published-interface fixtures (clearly separated from the producer run)
# ---------------------------------------------------------------------------

RAW_JSON = '{"state":{"task_goal":"ship the readable graph"},"model":"jev","headers":{"x-note":"<b>&amp;</b>"}}'
RAW_TEXT = "raw upstream reply: not JSON <keep> as-is"
XSS_TEXT = '<img src=x onerror="globalThis.PWNED=1">'


def _capture_copy(raw_text: str, **overrides) -> dict:
    copy = {
        "text": raw_text,
        "text_omitted": False,
        "output_omitted": False,
        "byte_exact": True,
        "wire_len": len(raw_text.encode("utf-8")),
        "stored_len": len(raw_text.encode("utf-8")),
        "truncated": False,
        "redactions": 0,
        "read_capped": False,
        "boundary_scrubbed": False,
        "decode_errors": False,
        "captured_redacted_sha256": None,
    }
    copy.update(overrides)
    return copy


def _published_v2_detail(detail_data: dict) -> dict:
    """The published T06 detail data, plus the T10 published fields (fixture).

    Node ids/statuses/labels come from the shipped projection vocabulary; the
    bodies are the published interface the card fixed (``material``,
    ``policy_result``, capture copies). This is a fixture, not a producer run.
    """
    detail = json.loads(json.dumps(detail_data, ensure_ascii=False))
    nodes = {node["id"]: node for node in detail["workbench"]["nodes"]}
    nodes["input"]["detail"]["material"] = {
        "task_goal": "让工作台用图形讲清一次决策",
        "task_requirements": "十节点有向图；点击侧栏读详情；保留安全边界。",
        "task_deliverables": "decision_dashboard.{html,js,css} 与 DOM 行为测试。",
    }
    # Audit wrappers the input node must never render by default.
    nodes["input"]["detail"]["state_digest"] = "digest-should-not-render"
    nodes["input"]["detail"]["mode"] = "auto"
    nodes["input"]["detail"]["intent"] = "advisory"
    nodes["request"]["detail"]["attempts"] = [
        {
            "attempt_index": 0,
            "method": "POST",
            "url_path": "/v1/decisions",
            "model": "jev",
            "timeout_s": 30,
            "header_names": ["content-type"],
            "capture_status": "ok",
            "request": _capture_copy(RAW_JSON),
        }
    ]
    nodes["response"]["detail"]["attempts"] = [
        {
            "attempt_index": 0,
            "http_status": 200,
            "latency_ms": 41,
            "content_type": "application/json",
            "error_class": None,
            "error_detail": None,
            "usage": {"input_tokens": 12, "output_tokens": 4},
            "capture_status": "ok",
            "response": _capture_copy(RAW_JSON),
        },
        {
            "attempt_index": 1,
            "http_status": 200,
            "latency_ms": 7,
            "content_type": "text/plain",
            "error_class": None,
            "error_detail": None,
            "usage": {"input_tokens": 12},
            "capture_status": "ok",
            "response": _capture_copy(RAW_TEXT),
        },
        {
            "attempt_index": 2,
            "http_status": 200,
            "latency_ms": 9,
            "content_type": "application/json",
            "error_class": None,
            "error_detail": None,
            "usage": {"input_tokens": 12},
            "capture_status": "ok",
            "response": _capture_copy(
                '{"answers":{"q1":{"value":"keep"}}}',
                text='{"answers":{"q1":{"value":"keep","cut":"tail"}}}',
                truncated=True,
                byte_exact=False,
                redactions=1,
                wire_len=420,
                stored_len=160,
            ),
        },
    ]
    nodes["decide"]["detail"]["policy_result"] = {
        "reason": "below-confidence-threshold",
        "selection": "split",
        "confidence": 0.62,
        "min_confidence": 0.7,
        "disposition": "not-adopted",
    }
    nodes["model"]["detail"]["confidence"] = 0.62
    nodes["model"]["detail"]["confidence_source"] = "api"
    return {"status": 200, "body": {"ok": True, "data": detail, "error": None, "capture_status": None}}


def _log_detail_with_real_captures(tmp_path: pathlib.Path) -> dict:
    """A real loopback detail whose wire captures exist (legacy row, real fold)."""
    root = monitor_suite._root(tmp_path, "log-root")
    assets_suite._seed_dashboard_history(root)
    with monitor_suite._running(
        root, deps=decision_monitor.MonitorDeps(redactor=REDACTOR)
    ) as instance:
        token = monitor_suite._page_token(instance)
        gamma = assets_suite._capture(instance, "/api/history?key=mw-gamma", token)
        alpha = assets_suite._capture(instance, "/api/history?key=mw-alpha", token)
        gamma_opaque = gamma["data"]["records"][0]["opaque_id"]
        alpha_opaque = alpha["data"]["records"][0]["opaque_id"]
        gamma_detail = assets_suite._capture(instance, f"/api/history/{gamma_opaque}", token)
        alpha_detail = assets_suite._capture(instance, f"/api/history/{alpha_opaque}", token)
    return {
        "token": token,
        "gamma": {"status": 200, "body": gamma_detail},
        "alpha": {"status": 200, "body": alpha_detail},
        "gammaOpaque": gamma_opaque,
        "alphaOpaque": alpha_opaque,
        "gammaList": {"status": 200, "body": gamma},
        "alphaList": {"status": 200, "body": alpha},
    }


def _v2_record(opaque: str, key: str, dp: str, processing: str, version, role) -> dict:
    return {
        "opaque_id": opaque,
        "record_kind": "decision",
        "scope": "production",
        "project_id": "p-fixture",
        "key": key,
        "task_key": "T11-readable-ui",
        "dp": dp,
        "ts": "2026-10-23T09:00:00+00:00",
        "status": "ok",
        "capture_status": "ok",
        "usage": {"recorded": False, "counters": {}, "missing": [], "complete": False, "semantics": "none"},
        "call_counts": {"recorded": True, "logical_calls": 1, "actual_http_attempts": 1, "zero_call": False},
        "calls": [],
        "stages": {},
        "workbench": {
            "record_version": version,
            "processing_state": processing,
            "key": key,
            "task_key": "T11-readable-ui",
            "question_summary": "继续、拆小、直接执行还是上抛人？",
            "dp_id": dp,
            "selection": {"checkpoint_action": {"value": "split"}},
            "initiator_role": role,
            "nodes": [],
        },
    }


def _v2_detail(record: dict) -> dict:
    """A ten-node detail payload with the documented node bodies.

    The node vocabulary (ids/labels/statuses) is imported from the shipped
    projection module, so this fixture cannot drift from the contract it claims
    to feed; the bodies are the published interface (T10 ``material`` /
    ``policy_result``) plus the T06 capture copy shape.
    """
    bases = {
        node_id: ["published-interface fixture: the T06 node vocabulary"]
        for node_id in NODE_IDS
    }
    nodes = [
        {
            "id": "key",
            "label": "key",
            "status": "observed",
            "basis": bases["key"],
            "detail": {
                "logical_id": "lg-fixture",
                "record_version": 2,
                "key": "mw-alpha",
                "task_key": "T11-readable-ui",
                "retry_of": None,
            },
        },
        {
            "id": "role",
            "label": "角色",
            "status": "observed",
            "basis": bases["role"],
            "detail": {"initiator_role": "pm", "actor_kind": "pm"},
        },
        {
            "id": "dp",
            "label": "DP",
            "status": "observed",
            "basis": bases["dp"],
            "detail": {
                "dp_id": record["dp"],
                "decision_id": record["dp"] + ":ckpt-a",
                "questions_version": "q-1234abcd",
            },
        },
        {
            "id": "input",
            "label": "输入",
            "status": "observed",
            "basis": bases["input"],
            "detail": {
                "state_digest": "digest-should-not-render",
                "questions_version": "q-1234abcd",
                "truncated": [],
                "mode": "auto",
                "intent": "advisory",
                "book_ref": "input-memory",
                "book_version": "book-v1",
                "book": _capture_copy(
                    '{"schema_version":1,"decision_point":"dp2-checkpoint-split"}'
                ),
            },
        },
        {
            "id": "decide",
            "label": "decide 处理",
            "status": "observed",
            "basis": bases["decide"],
            "detail": {
                "available": True,
                "status": "ok",
                "reason": None,
                "escalated_reason": None,
                "zero_call": False,
                "archive": "created",
                "mode": "auto",
                "intent": "advisory",
                "book_ref": "input-memory",
            },
        },
        {
            "id": "request",
            "label": "API 请求",
            "status": "observed",
            "basis": bases["request"],
            "detail": {"attempts": []},
        },
        {
            "id": "model",
            "label": "决策模型",
            "status": "observed",
            "basis": bases["model"],
            "detail": {
                "transport": "timi-decisions",
                "model": "jev",
                "answer_source": "api",
                "confidence_source": "api",
                "confidence": 0.62,
            },
        },
        {
            "id": "response",
            "label": "返回结果",
            "status": "observed",
            "basis": bases["response"],
            "detail": {
                "attempts": [],
                "usage": {
                    "recorded": False,
                    "counters": {},
                    "missing": [],
                    "complete": False,
                    "semantics": "none",
                },
            },
        },
        {
            "id": "receipt",
            "label": "接收签收",
            "status": "observed",
            "basis": bases["receipt"],
            "detail": {
                "consumed": {
                    "ts": "2026-10-23T09:01:00+00:00",
                    "answer": "split",
                    "answer_source": "api",
                    "actor_kind": "pm",
                },
                "signoff": None,
                "errors": [],
            },
        },
        {
            "id": "action",
            "label": "行动反馈",
            "status": "observed",
            "basis": bases["action"],
            "detail": {
                "executed": [
                    {
                        "ts": "2026-10-23T09:02:00+00:00",
                        "action": "split",
                        "result": "created two follow-up tasks",
                        "answer_source": "api",
                        "actor_kind": "pm",
                    }
                ],
                "settled": {"ts": "2026-10-23T09:03:00+00:00", "outcome": "ok", "reason": "split done"},
                "errors": [],
            },
        },
    ]
    assert [node["id"] for node in nodes] == NODE_IDS
    detail = json.loads(json.dumps(record, ensure_ascii=False))
    detail["workbench"] = dict(detail["workbench"])
    detail["workbench"]["nodes"] = nodes
    detail["archive"] = None
    detail["archive_rows"] = []
    return {"status": 200, "body": {"ok": True, "data": detail, "error": None, "capture_status": None}}


def _published_payloads() -> dict:
    alpha = "h-" + "1" * 20
    beta = "h-" + "2" * 20
    gamma = "h-" + "3" * 20
    delta = "h-" + "4" * 20
    records = [
        _v2_record(alpha, "mw-alpha", "dp2-checkpoint-split", "completed", 2, "pm"),
        _v2_record(beta, "mw-beta", "dp1-dispatch-type", "failed", 2, "pm"),
        _v2_record(gamma, "mw-gamma", "dp3-worker-clarify", "processing", 2, "worker"),
        _v2_record(delta, "mw-delta", "dp25-signoff-conclusion", "legacy", None, None),
    ]
    listing = {
        "status": 200,
        "body": {
            "ok": True,
            "data": {
                "records": records,
                "total": len(records),
                "offset": 0,
                "limit": 50,
                "has_more": False,
                "facets": {
                    "keys": [record["key"] for record in records],
                    "dps": [record["dp"] for record in records],
                },
                "filters": {"scope": "production"},
                "filters_withheld": [],
                "filters_basis": ["fixture"],
            },
            "error": None,
            "capture_status": None,
        },
    }
    points = []
    for dp in CASES:
        points.append(
            {
                "id": dp,
                "tier": "P1",
                "default_enabled": True,
                "default_mode": "auto",
                "enabled": True,
                "mode": "auto",
                "config_source": "fixture",
                "questions_version": "q-1234abcd",
                "executor": "none",
                "wired": False,
                "required_state_fields": [],
                "optional_state_fields": [],
            }
        )
    dps = {
        "status": 200,
        "body": _envelope(
            {
                "points": points,
                "budget": {"max_state_bytes": 8192},
                "transport": {"state": "configured", "detail": "fixture"},
                "config": {"layer": "fixture", "warnings": []},
                "observe_only": True,
            }
        ),
    }
    submission = {
        "submission_id": "ui-test-1",
        "dp": "dp1-dispatch-type",
        "state": "succeeded",
        "decision_ran": True,
        "decision_id": "dp1-dispatch-type:ui-test-1",
        "call_id": "call-1",
        "zero_call": False,
        "http_attempts": 1,
        "book_ref": "book-1",
        "state_digest": "digest-1",
        "answer_persisted": False,
        "projection_status": "not-recorded",
        "issues": [],
        "outcome": {"status": "suggested", "mode": "auto"},
        "attempts": [],
        "observe_only": True,
    }
    test_history = {
        "source": "test",
        "scope": "test",
        "observe_only": True,
        "records": [
            {
                "submission_id": "ui-test-1",
                "dp": "dp1-dispatch-type",
                "state": "succeeded",
                "retry_of": None,
                "call_id": "call-1",
                "book_ref": "book-1",
                "zero_call": False,
                "http_attempts": 1,
                "answer_persisted": False,
                "projection_status": "not-recorded",
                "projection_sha256": None,
            }
        ],
        "total": 1,
        "limit": 50,
        "warnings": [],
    }
    return {
        "token": "fixture-page-token",
        "default": listing,
        "detailByOpaque": {alpha: _v2_detail(records[0])},
        "alpha": alpha,
        "dps": dps,
        "testHistory": {"status": 200, "body": _envelope(test_history)},
        "submission": {"status": 200, "body": _envelope(submission)},
    }


CASES = {
    "dp1-dispatch-type": json.loads((CASES_DIR / "dp1.json").read_text(encoding="utf-8")),
    "dp2-checkpoint-split": json.loads((CASES_DIR / "dp2.json").read_text(encoding="utf-8")),
    "dp3-worker-clarify": json.loads((CASES_DIR / "dp3.json").read_text(encoding="utf-8")),
    "dp25-signoff-conclusion": json.loads((CASES_DIR / "dp25.json").read_text(encoding="utf-8")),
}

#: The four native questions (registry shapes) the T10 case route publishes.
PUBLISHED_QUESTIONS = {
    "dp1-dispatch-type": [
        {
            "id": "triage_type",
            "type": "choice",
            "instructions": "这个任务应该派给哪一类 worker？",
            "choices": ["coding", "research", "review"],
            "labels": {
                "coding": "需要写代码或改代码或跑命令",
                "research": "只做检索取证不改代码",
                "review": "审计别人已完成的产出",
            },
            "criteria": ["coding: 有代码或命令改动", "research: 只取证", "review: 审计产出"],
        }
    ],
    "dp2-checkpoint-split": [
        {
            "id": "checkpoint_action",
            "type": "choice",
            "instructions": "以当前进度，这一步该继续、拆小、直接执行还是上抛人？",
            "choices": ["narrow", "split", "direct-exec", "escalate"],
            "labels": {
                "narrow": "收窄到剩余预算内能完成的一小块",
                "split": "拆成多个任务重派",
                "direct-exec": "PM 自己直接做完",
                "escalate": "风险高到必须问人",
            },
        }
    ],
    "dp3-worker-clarify": [
        {
            "id": "handling",
            "type": "choice",
            "instructions": "针对这个问题，从候选处理方式中选出最合适的一项。",
            "dynamic_choices": "handling_options",
        }
    ],
    "dp25-signoff-conclusion": [
        {
            "id": "q-conclusion",
            "type": "choice",
            "instructions": "按交付目标、实际完成与验证证据判断：这次交付可以收尾，还是需要继续完成，或交用户确认？",
            "choices": ["finalize", "continue", "user-confirm"],
            "labels": {
                "finalize": "可以收尾：按交付目标与验收条件直接签收",
                "continue": "继续完成：交 PM 推进未完成的缺口",
                "user-confirm": "交用户确认：由 PM 提出具体待确认项",
            },
        }
    ],
}


def _published_cases_payload() -> dict:
    cases = []
    for dp, shell in CASES.items():
        cases.append(
            {
                "dp": dp,
                "title": shell["title"],
                "note": shell["note"],
                "book": shell["book"],
                "questions": {q["id"]: json.loads(json.dumps(q, ensure_ascii=False)) for q in PUBLISHED_QUESTIONS[dp]},
                "sha256": "sha-" + dp,
                "bytes": 1,
            }
        )
    return {"status": 200, "body": _envelope({"case_version": 1, "source": "offline", "cases": cases})}


# ---------------------------------------------------------------------------
# AC-021: a real ten-node directed graph, clickable nodes, readable side detail
# ---------------------------------------------------------------------------


def test_graph_is_ten_nodes_with_directed_edges_and_clickable_readable_detail(tmp_path):
    payloads = _published_payloads()
    alpha = payloads["alpha"]
    detail = _published_v2_detail(payloads["detailByOpaque"][alpha]["body"]["data"])
    scenario = {
        "hash": "#boot=dom-boot-code",
        "bootstrap": wb._bootstrap(payloads["token"]),
        "history": payloads["default"],
        "detailByOpaque": {alpha: detail},
        "steps": [
            {
                "type": "click",
                "target": '[data-testid="record-dag-open"][data-opaque="' + alpha + '"]',
                "snapshot": "dag",
            },
            {
                "type": "click",
                "target": '[data-testid="dag-node"][data-node-id="key"]',
                "snapshot": "node-key",
            },
            {
                "type": "dispatch",
                "target": '[data-testid="dag-node"][data-node-id="key"]',
                "event": {"type": "keydown", "key": "ArrowRight"},
                "snapshot": "after-arrow",
            },
        ]
        + [
            {
                "type": "click",
                "target": '[data-testid="dag-node"][data-node-id="' + node_id + '"]',
                "snapshot": "node-" + node_id,
            }
            for node_id in NODE_IDS[1:]
        ],
    }
    result = _run_dom(tmp_path, scenario)
    dag = _snapshot(result, "dag")

    # The graph, not a list: one SVG edge layer, ten positioned node controls.
    assert dag["graph"]["svgCount"] >= 1, "the DAG needs an SVG edge layer"
    assert dag["graph"]["legacyListCount"] == 0, "a vertical <ol> list must not pass as a DAG"
    assert dag["dialogVisible"] is True and dag["dagPanelVisible"] is True
    assert [node["id"] for node in dag["graph"]["nodes"]] == NODE_IDS
    assert [node["step"] for node in dag["graph"]["nodes"]] == [
        "%02d" % (index + 1) for index in range(10)
    ], "the node order markers follow the approved order"
    positions = [node["position"] for node in dag["graph"]["nodes"]]
    assert len(set(positions)) == 10, "every node has its own graph position"
    assert all(position and position.startswith("dag-pos-") for position in positions)
    assert all(node["kind"] == "BUTTON" for node in dag["graph"]["nodes"]), "nodes are controls"
    assert all(node["state"] in wb.NODE_STATUSES for node in dag["graph"]["nodes"])
    assert "已记录" in " ".join(node["text"] for node in dag["graph"]["nodes"])
    for node in dag["graph"]["nodes"]:
        assert any(
            label in node["text"] for label in ("已记录", "未记录", "失败", "未执行")
        ), node
        assert "步骤 " + node["step"] in node["text"], node

    # Directed edges: exactly the nine consecutive steps, each with an arrowhead.
    edges = dag["graph"]["edges"]
    assert len(edges) == 9, edges
    assert [(edge["from"], edge["to"]) for edge in edges] == list(zip(NODE_IDS, NODE_IDS[1:]))
    assert [edge["order"] for edge in edges] == [str(index) for index in range(9)]
    assert all(edge["kind"] == "LINE" for edge in edges), "edges are drawn as SVG lines"
    assert all(edge["namespace"].endswith("/2000/svg") for edge in edges)
    assert all(edge["marker"] == "url(#dag-node-arrow)" for edge in edges), "each edge is directed"
    turn = edges[4]
    assert (turn["y1"], turn["y2"]) == ("78", "174"), "the down edge ends at the next node's top, not through its body"
    assert all(edge["ariaHidden"] == "true" for edge in edges)
    assert all(
        edge["x1"] != edge["x2"] or edge["y1"] != edge["y2"] for edge in edges
    ), "edges carry real coordinates (no collapsed line)"
    assert "不代表" in (dag["graph"]["note"] or ""), (
        "the page must state that an edge is the declared order, not a proof the step happened"
    )
    assert "10/10" in (dag["dagSummary"] or "")
    assert dag["pwned"] is False and dag["consoleMessages"] == []

    # Every node click shows the readable detail of this same decision, on the side.
    assert dag["nodeDetailIsSide"] is True, "the detail is a side panel, not a footer list"
    for node_id in NODE_IDS:
        snapshot = _snapshot(result, "node-" + node_id)
        assert snapshot["nodeDetailId"] == node_id, (node_id, snapshot["nodeDetailId"])
        text = snapshot["nodeDetail"] or ""
        assert text.strip(), node_id
        assert "节点 " + node_id in text, (node_id, text[:200])

    key_detail = (_snapshot(result, "node-key")["nodeDetail"] or "")
    assert "task" in key_detail and "T11-readable-ui" in key_detail, key_detail
    request_detail = _snapshot(result, "node-request")["nodeDetail"] or ""
    assert RAW_JSON.split(",")[0][1:] not in request_detail, "the JSON capture is formatted, not raw"
    assert "实际请求" in request_detail or "请求" in request_detail

    # Keyboard access: ArrowRight moves focus to the next node control.
    after_arrow = _snapshot(result, "after-arrow")
    assert after_arrow["activeElement"] == NODE_IDS[1], after_arrow["activeElement"]


def test_playground_submission_detail_uses_the_same_graph(tmp_path):
    payloads = _published_payloads()
    scenario = {
        "hash": "#boot=dom-boot-code",
        "bootstrap": wb._bootstrap(payloads["token"]),
        "history": payloads["default"],
        "detailByOpaque": payloads["detailByOpaque"],
        "dps": payloads["dps"],
        "testHistory": payloads["testHistory"],
        "submission": payloads["submission"],
        "steps": [
            {"type": "click", "target": "#tab-playground"},
            {"type": "click", "target": "#pg-load"},
            {"type": "click", "target": '[data-testid="pg-history-open"]', "snapshot": "pg-dag"},
        ],
    }
    pg_dag = _snapshot(_run_dom(tmp_path, scenario), "pg-dag")
    assert [node["id"] for node in pg_dag["pgGraph"]["nodes"]] == NODE_IDS
    assert len(pg_dag["pgGraph"]["edges"]) == 9
    assert all(edge["marker"] == "url(#pg-dag-node-arrow)" for edge in pg_dag["pgGraph"]["edges"])
    assert pg_dag["graph"]["edges"] == [], "hidden history graph has no fabricated nodes"
    assert "未执行" in " ".join(node["text"] for node in pg_dag["pgGraph"]["nodes"])


# ---------------------------------------------------------------------------
# AC-022 (input): business material only, legacy snapshot parsed, never guessed
# ---------------------------------------------------------------------------


def test_observation_dag_clicks_show_this_submission_captures_and_material(tmp_path):
    payloads = _published_payloads()
    row = payloads["submission"]["body"]["data"]
    request = json.dumps({"model": "jev-latest", "state": {"task_goal": "Recorded observation goal"}, "questions": {}})
    response = '{"answers":{"triage_type":{"choice":"research","confidence":0.62}}}'
    row["attempts"] = [{
        "attempt_index": 0, "model": "jev-latest", "http_status": 200,
        "request": {"text": request, "byte_exact": True},
        "response": {"text": response, "byte_exact": True},
    }]
    row["outcome"] = {"status": "escalated", "escalated_reason": "low-confidence", "response": {"confidence_source": "api"}}
    steps = [
        {"type": "click", "target": "#tab-playground"},
        {"type": "click", "target": "#pg-load"},
        {"type": "click", "target": '[data-testid="pg-history-open"]'},
    ]
    for node in ("input", "request", "response", "decide", "action"):
        steps.append({"type": "click", "target": f'[data-testid="pg-dag-node"][data-node-id="{node}"]', "snapshot": node})
    result = _run_dom(tmp_path, {
        "hash": "#boot=fixture", "bootstrap": wb._bootstrap(payloads["token"]),
        "history": payloads["default"], "dps": payloads["dps"],
        "testHistory": payloads["testHistory"], "submission": payloads["submission"], "steps": steps,
    })
    assert "Recorded observation goal" in _snapshot(result, "input")["pgNodeDetail"]
    assert "jev-latest" in _snapshot(result, "request")["pgNodeDetail"]
    assert "research" in _snapshot(result, "response")["pgNodeDetail"]
    decide = _snapshot(result, "decide")["pgNodeDetail"]
    assert "low-confidence" in decide and "未记录" in decide
    assert "未执行" in _snapshot(result, "action")["pgNodeDetail"]
    assert result["storageWrites"] == []


def test_invalid_business_editor_never_submits_the_previous_book(tmp_path):
    payloads = _published_payloads()
    scenario = {
        "hash": "#boot=fixture", "bootstrap": wb._bootstrap(payloads["token"]),
        "history": payloads["default"], "dps": payloads["dps"],
        "testHistory": payloads["testHistory"], "cases": _published_cases_payload(),
        "steps": [
            {"type": "click", "target": "#tab-playground"},
            {"type": "click", "target": "#pg-load"},
            {"type": "click", "target": "#pg-cases-load"},
            {"type": "setValue", "target": "#case-select", "value": "dp1-dispatch-type"},
            {"type": "click", "target": "#pg-case-open"},
            {"type": "setValue", "target": "#material-editor", "value": "{invalid"},
            {"type": "dispatch", "target": "#material-editor", "event": {"type": "input"}},
            {"type": "click", "target": "#pg-submit", "snapshot": "invalid"},
        ],
    }
    result = _run_dom(tmp_path, scenario)
    assert not any(call["url"] == "/api/test/submit" for call in result["fetchCalls"])
    assert "未发起请求" in _snapshot(result, "invalid")["validateText"]


def test_real_observation_http_detail_reaches_the_shipped_dag(tmp_path):
    with backend_suite._Live(tmp_path) as live:
        case = backend_suite._case(live, backend_suite.DP1)
        status, submitted = backend_suite._post(live, "/api/test/submit", {
            "dp": backend_suite.DP1, "book": case["book"], "questions": case["questions"],
            "submit_id": "t12-http-dom", "observe_only": True,
        })
        assert status == 200 and backend_suite._data(submitted)["state"] == "succeeded"
        status, detail = backend_suite._get(live, "/api/test/submissions/t12-http-dom")
        assert status == 200
        status, history = backend_suite._get(live, "/api/test/history")
        assert status == 200
        status, dps = backend_suite._get(live, "/api/dps")
        assert status == 200
        assert live.fixture.calls == 1
    payloads = _published_payloads()
    steps = [{"type": "click", "target": target} for target in ("#tab-playground", "#pg-load", '[data-testid="pg-history-open"]')]
    for node in ("input", "request", "response", "receipt", "action"):
        steps.append({"type": "click", "target": f'[data-testid="pg-dag-node"][data-node-id="{node}"]', "snapshot": node})
    result = _run_dom(tmp_path, {
        "hash": "#boot=fixture", "bootstrap": wb._bootstrap("fixture-page-token"),
        "history": payloads["default"], "dps": {"status": 200, "body": dps},
        "testHistory": {"status": 200, "body": history}, "submission": {"status": 200, "body": detail}, "steps": steps,
    })
    assert case["book"]["state"]["task_goal"] in _snapshot(result, "input")["pgNodeDetail"]
    assert "jev-latest" in _snapshot(result, "request")["pgNodeDetail"]
    assert "HTTP 200" in _snapshot(result, "response")["pgNodeDetail"]
    assert "未记录" in _snapshot(result, "receipt")["pgNodeDetail"]
    assert "未执行" in _snapshot(result, "action")["pgNodeDetail"]
    assert result["storageWrites"] == []


def _input_node_detail_request(tmp_path: pathlib.Path, mutations: dict | None = None) -> dict:
    payloads = _published_payloads()
    alpha = payloads["alpha"]
    detail = _published_v2_detail(payloads["detailByOpaque"][alpha]["body"]["data"])
    nodes = {node["id"]: node for node in detail["body"]["data"]["workbench"]["nodes"]}
    for path, value in (mutations or {}).items():
        parts = path.split(".")
        target = nodes
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]] = value
    return {
        "scenario": {
            "hash": "#boot=dom-boot-code",
            "bootstrap": wb._bootstrap(payloads["token"]),
            "history": payloads["default"],
            "detailByOpaque": {alpha: detail},
            "steps": [
                {
                    "type": "click",
                    "target": '[data-testid="record-dag-open"][data-opaque="' + alpha + '"]',
                },
                {
                    "type": "click",
                    "target": '[data-testid="dag-node"][data-node-id="input"]',
                    "snapshot": "input",
                },
            ],
        },
        "material": nodes["input"]["detail"]["material"],
    }


def test_input_node_shows_business_material_only(tmp_path):
    request = _input_node_detail_request(tmp_path)
    text = _snapshot(_run_dom(tmp_path, request["scenario"]), "input")["nodeDetail"] or ""
    assert "任务目标" in text and "任务要求" in text and "交付物" in text, text
    for value in request["material"].values():
        assert value in text, value
    # The book wrapper / audit fields are not the material and must not render.
    for forbidden in (
        "input-memory",
        "book-v1",
        "digest-should-not-render",
        "book_ref",
        "book_version",
        "state_digest",
        "questions_version",
        "q-1234abcd",
        "mode",
        "intent",
        "依据",
    ):
        assert forbidden not in text, (forbidden, text)


def test_input_node_parses_the_legacy_snapshot_state_without_guessing(tmp_path):
    legacy_book = '{"schema_version":1,"decision_point":"dp2-checkpoint-split","state":{"task_goal":"legacy goal text","pm_decision_background":"legacy background text"}}'
    request = _input_node_detail_request(
        tmp_path,
        {
            "input.detail.material": None,
            "input.detail.book": _capture_copy(legacy_book),
        },
    )
    text = _snapshot(_run_dom(tmp_path, request["scenario"]), "input")["nodeDetail"] or ""
    assert "legacy goal text" in text and "legacy background text" in text, text
    assert "schema_version" not in text and "decision_point" not in text

    empty_book = '{"schema_version":1,"decision_point":"dp1-dispatch-type"}'
    request = _input_node_detail_request(
        tmp_path,
        {
            "input.detail.material": None,
            "input.detail.book": _capture_copy(empty_book),
        },
    )
    text = _snapshot(_run_dom(tmp_path, request["scenario"]), "input")["nodeDetail"] or ""
    assert "未记录" in text, text
    assert "schema_version" not in text and "decision_point" not in text


# ---------------------------------------------------------------------------
# AC-022 (captures): prettified JSON, verbatim non-JSON, raw copy, honest marks
# ---------------------------------------------------------------------------


def test_request_and_response_show_formatted_text_and_copy_the_raw_capture(tmp_path):
    payloads = _published_payloads()
    alpha = payloads["alpha"]
    detail = _published_v2_detail(payloads["detailByOpaque"][alpha]["body"]["data"])
    scenario = {
        "hash": "#boot=dom-boot-code",
        "bootstrap": wb._bootstrap(payloads["token"]),
        "history": payloads["default"],
        "detailByOpaque": {alpha: detail},
        "steps": [
            {
                "type": "click",
                "target": '[data-testid="record-dag-open"][data-opaque="' + alpha + '"]',
            },
            {"type": "click", "target": '[data-testid="dag-node"][data-node-id="request"]'},
            {
                "type": "click",
                "target": '[data-testid="capture-copy"][data-scope="dag"][data-capture="request"][data-attempt="0"]',
                "snapshot": "copied-request",
            },
            {"type": "click", "target": '[data-testid="dag-node"][data-node-id="response"]', "snapshot": "response"},
            {
                "type": "click",
                "target": '[data-testid="capture-copy"][data-scope="dag"][data-capture="response"][data-attempt="0"]',
                "snapshot": "copied-response",
            },
        ],
    }
    result = _run_dom(tmp_path, scenario)

    copied_request = _snapshot(result, "copied-request")
    request_block = next(
        block for block in copied_request["captures"]
        if block["scope"] == "dag" and block["capture"] == "request" and block["attempt"] == "0"
    )
    assert request_block["format"] == "json"
    assert "\n" in (request_block["text"] or ""), "valid JSON is prettified"
    assert json.loads(request_block["text"]) == json.loads(RAW_JSON), "the formatted view is the same value"
    assert request_block["status"] == "complete"
    assert "完整" in (request_block["statusText"] or "")
    # Double-layer escaping: the HTML entities in the JSON payload stay raw
    # characters inside the text node (no second escaping pass).
    assert json.loads(request_block["text"])["headers"]["x-note"] == "<b>&amp;</b>"
    assert "&amp;amp;" not in request_block["text"]
    # The copy button copies the ORIGINAL captured string, not the view.
    assert copied_request["clipboard"] == [RAW_JSON], copied_request["clipboard"]
    assert request_block["copyStatus"] in ("", None) or "已复制" in request_block["copyStatus"]

    response = _snapshot(result, "response")
    response_blocks = [block for block in response["captures"] if block["capture"] == "response"]
    assert [block["attempt"] for block in response_blocks] == ["0", "1", "2"]
    assert json.loads(response_blocks[0]["text"]) == json.loads(RAW_JSON)
    assert response_blocks[1]["format"] == "text"
    assert response_blocks[1]["text"] == RAW_TEXT, "non-JSON keeps the original text"
    assert response_blocks[2]["status"] == "truncated"
    assert "截断" in (response_blocks[2]["statusText"] or ""), response_blocks[2]["statusText"]

    copied_response = _snapshot(result, "copied-response")
    assert copied_response["clipboard"][-1] == RAW_JSON, (
        "the copy keeps the raw capture, never the prettified bytes"
    )
    copy_status = [
        block["copyStatus"] for block in copied_response["captures"]
        if block["capture"] == "response" and block["attempt"] == "0"
    ][0]
    assert "已复制" in (copy_status or ""), copy_status


def test_log_detail_defaults_to_time_task_role_captures_receipt_and_errors(tmp_path):
    payload = _log_detail_with_real_captures(tmp_path)
    scenario = {
        "hash": "#boot=dom-boot-code",
        "bootstrap": {"status": 200, "body": _envelope({"page_token": payload["token"]})},
        "history": payload["gammaList"],
        "historyByFilterKey": {
            "mw-gamma": payload["gammaList"],
            "mw-alpha": payload["alphaList"],
        },
        "detailByOpaque": {
            payload["gammaOpaque"]: payload["gamma"],
            payload["alphaOpaque"]: payload["alpha"],
        },
        "steps": [
            {"type": "setValue", "target": "#filter-key", "value": "mw-gamma"},
            {"type": "click", "target": "#filter-apply"},
            {
                "type": "click",
                "target": '[data-testid="record-open"][data-opaque="' + payload["gammaOpaque"] + '"]',
                "snapshot": "gamma-log",
            },
            {"type": "click", "target": "#detail-close"},
            {"type": "setValue", "target": "#filter-key", "value": "mw-alpha"},
            {"type": "click", "target": "#filter-apply"},
            {
                "type": "click",
                "target": '[data-testid="record-open"][data-opaque="' + payload["alphaOpaque"] + '"]',
                "snapshot": "alpha-log",
            },
        ],
    }
    result = _run_dom(tmp_path, scenario)
    gamma = _snapshot(result, "gamma-log")
    assert gamma["logVisible"] is True
    assert gamma["logSections"] == ["概要", "实际请求与返回", "接收与处理结果", "错误"], gamma["logSections"]
    log_text = gamma["logText"] or ""
    assert "时间" in log_text and "mw-gamma" in log_text and "发起角色" in log_text
    # The removed default columns are gone; the underlying record is untouched.
    for forbidden in ("来源（分列）", "阶段", "决策本", "book-v1", "版本", "hash"):
        assert forbidden not in log_text, (forbidden, log_text[:400])
    gamma_payload = payload["gamma"]["body"]["data"]
    assert gamma_payload["stages"] and gamma_payload["calls"], "the record itself still carries them"
    # Real captures rendered readably + copyable.
    gamma_captures = [block for block in gamma["captures"] if block["scope"] == "log"]
    assert {block["capture"] for block in gamma_captures} == {"request", "response"}
    for block in gamma_captures:
        assert block["format"] == "json"
        assert "\n" in (block["text"] or "")
        assert json.loads(block["text"]) == json.loads(
            '{"answers":{"q-task":"keep"}}' if block["capture"] == "response" else '{"state":{"a":1}}'
        )

    alpha = _snapshot(result, "alpha-log")
    alpha_text = alpha["logText"] or ""
    assert SECRET not in alpha_text, "an output-omitted capture never leaks the stored secret"
    assert "本次输出省略正文" in alpha_text or "未记录" in alpha_text
    assert "response-read" in alpha_text, "a recorded error stays visible in the default log"
    assert XSS_TEXT in alpha_text, "free text is rendered literally, not as markup"
    assert alpha["imgCount"] == 0 and alpha["pwned"] is False
    assert alpha["consoleMessages"] == []
    assert alpha["storage"] == []


# ---------------------------------------------------------------------------
# AC-023: below-threshold confidence is "not adopted", not an API failure
# ---------------------------------------------------------------------------


def _decide_text(tmp_path: pathlib.Path, mutate) -> str:
    payloads = _published_payloads()
    alpha = payloads["alpha"]
    detail = _published_v2_detail(payloads["detailByOpaque"][alpha]["body"]["data"])
    nodes = {node["id"]: node for node in detail["body"]["data"]["workbench"]["nodes"]}
    mutate(nodes)
    scenario = {
        "hash": "#boot=dom-boot-code",
        "bootstrap": wb._bootstrap(payloads["token"]),
        "history": payloads["default"],
        "detailByOpaque": {alpha: detail},
        "steps": [
            {
                "type": "click",
                "target": '[data-testid="record-dag-open"][data-opaque="' + alpha + '"]',
            },
            {"type": "click", "target": '[data-testid="dag-node"][data-node-id="decide"]', "snapshot": "decide"},
        ],
    }
    snapshot = _snapshot(_run_dom(tmp_path, scenario), "decide")
    assert set(snapshot["stateValues"]) == set(STATES), "the four main states are unchanged"
    return snapshot["nodeDetail"] or ""


def test_low_confidence_decide_is_explained_as_not_adopted(tmp_path):
    text = _decide_text(tmp_path, lambda nodes: None)
    assert "0.62" in text and "0.7" in text, text
    assert "本次阈值" in text
    assert "未采纳" in text
    assert "split" in text, "the model selection is shown"
    assert "API" in text and "confidence" in text
    assert "人工兜底" in text or "not-adopted" in text
    assert "API 调用失败" not in text
    assert "HTTP 200" in text or "已返回" in text


def test_unknown_threshold_is_reported_as_not_recorded(tmp_path):
    def mutate(nodes):
        policy = nodes["decide"]["detail"]["policy_result"]
        policy["min_confidence"] = None

    text = _decide_text(tmp_path, mutate)
    assert "未记录" in text, text
    assert "0.70" not in text and "0.7 " not in text
    assert "未采纳" in text
    assert "API 调用失败" not in text


def test_decide_without_policy_result_does_not_invent_a_verdict(tmp_path):
    def mutate(nodes):
        nodes["decide"]["detail"].pop("policy_result", None)
        nodes["response"]["detail"]["attempts"][0]["http_status"] = 200

    text = _decide_text(tmp_path, mutate)
    assert "策略判定：未记录" in text, text
    assert "API 调用失败" not in text
    assert "0.62" in text, "the recorded API confidence stays visible"


# ---------------------------------------------------------------------------
# AC-024: complete case questions, editable state/instructions/criteria, preview
# ---------------------------------------------------------------------------


def _questions_scenario(tmp_path: pathlib.Path, dp: str, instructions_edit: str, state_edit: tuple[str, str]):
    payloads = _published_payloads()
    cases = _published_cases_payload()
    cases["body"]["data"]["cases"] = [
        case for case in cases["body"]["data"]["cases"] if case["dp"] == dp
    ]
    case = next(item for item in cases["body"]["data"]["cases"] if item["dp"] == dp)
    book = json.loads(json.dumps(case["book"], ensure_ascii=False))
    field, value = state_edit
    book["state"][field] = value
    sent_questions = json.loads(json.dumps(PUBLISHED_QUESTIONS[dp], ensure_ascii=False))
    sent_questions[0]["instructions"] = instructions_edit
    if dp == "dp3-worker-clarify":
        # Candidates live only in state.handling_options; the page never
        # duplicates them (or their criteria) into questions.
        sent_questions[0].pop("criteria", None)
    state_sent = dict(book["state"])
    preview = {
        "model": {"model": "jev", "transport": "timi-decisions"},
        "state": state_sent,
        "questions": {q["id"]: json.loads(json.dumps(q, ensure_ascii=False)) for q in sent_questions},
    }
    # The server is the authority for the preview (it may normalize criteria).
    preview["questions"][sent_questions[0]["id"]]["normalized_by"] = "server"
    validate = {
        "status": 200,
        "body": _envelope(
            {
                "dp": dp,
                "ok": True,
                "issues": [],
                "observe_only": True,
                "context_sent": False,
                "request_preview": preview,
            }
        ),
    }
    submit = {
        "status": 200,
        "body": _envelope(
            {
                "submission_id": "ui-questions",
                "dp": dp,
                "state": "succeeded",
                "accepted": True,
                "observe_only": True,
                "record_status": "recorded",
                "decision_ran": True,
                "zero_call": False,
                "http_attempts": 1,
                "answer_persisted": False,
                "projection_status": "not-recorded",
                "issues": [],
                "outcome": {"status": "suggested", "mode": "auto"},
                "attempts": [],
            }
        ),
    }
    scenario = {
        "hash": "#boot=dom-boot-code",
        "bootstrap": wb._bootstrap(payloads["token"]),
        "history": payloads["default"],
        "detailByOpaque": payloads["detailByOpaque"],
        "cases": cases,
        "dps": payloads["dps"],
        "testHistory": payloads["testHistory"],
        "validate": validate,
        "submit": submit,
        "steps": [
            {"type": "click", "target": "#tab-playground"},
            {"type": "click", "target": "#pg-load"},
            {"type": "click", "target": "#pg-cases-load"},
            {"type": "setValue", "target": "#case-select", "value": dp},
            {"type": "click", "target": "#pg-case-open", "snapshot": "opened"},
            {
                "type": "setValue",
                "target": '[data-testid="pg-question-instructions"]',
                "value": instructions_edit,
            },
            {
                "type": "setValue",
                "target": "#book-editor",
                "value": json.dumps(book, ensure_ascii=False, indent=2),
            },
            {"type": "click", "target": "#pg-validate", "snapshot": "validated"},
            {"type": "click", "target": "#pg-submit", "snapshot": "submitted"},
        ],
    }
    return {
        "scenario": scenario,
        "book": book,
        "sentQuestions": {q["id"]: q for q in sent_questions},
        "preview": preview,
        "field": field,
        "value": value,
    }


def test_case_questions_are_complete_editable_and_previewed_before_submit(tmp_path):
    fixture = _questions_scenario(
        tmp_path,
        "dp1-dispatch-type",
        "edited: which worker type fits this task?",
        ("task_goal", "edited goal for the questions path"),
    )
    result = _run_dom(tmp_path, fixture["scenario"])
    opened = _snapshot(result, "opened")

    assert opened["questionsStatus"], "the questions area states its scope"
    assert len(opened["questions"]) == 1, "the opened case exposes its own question block"
    dp1 = opened["questions"][0]
    assert dp1["id"] == "triage_type"
    assert dp1["kind"] == "choice"
    assert "choices" in dp1["text"] and "coding" in dp1["text"]
    assert dp1["instructions"].startswith("这个任务应该派给哪一类 worker")
    assert dp1["criteriaInput"] and "coding" in dp1["criteriaInput"], "non-dp3 criteria is editable"
    assert dp1["derived"] is None
    assert opened["preview"] is None, "loading a case never produces a request preview"

    validated = _snapshot(result, "validated")
    validate_calls = [call for call in validated["fetchCalls"] if call["url"] == "/api/test/validate"]
    assert len(validate_calls) == 1
    body = json.loads(validate_calls[0]["body"])
    assert body["dp"] == "dp1-dispatch-type"
    assert body["book"]["state"]["task_goal"] == fixture["value"]
    assert isinstance(body["questions"], dict) and body["questions"], "validate carries the native questions mapping"
    sent = body["questions"]["triage_type"]
    assert sent["id"] == "triage_type"
    assert sent["instructions"].startswith("edited:")
    assert sent["criteria"] == fixture["sentQuestions"]["triage_type"]["criteria"], "criteria edits travel too"
    assert sent["choices"] == fixture["sentQuestions"]["triage_type"]["choices"], "native choices stay intact"

    preview = validated["preview"]
    assert preview and preview["present"] is True
    assert json.loads(preview["model"]) == fixture["preview"]["model"]
    assert json.loads(preview["state"]) == fixture["preview"]["state"]
    assert json.loads(preview["questions"]) == fixture["preview"]["questions"], (
        "the page shows the server's own preview (no client re-derivation)"
    )
    assert "normalized_by" in preview["questions"], "server normalization is what is displayed"

    submitted = _snapshot(result, "submitted")
    submit_calls = [call for call in submitted["fetchCalls"] if call["url"] == "/api/test/submit"]
    assert len(submit_calls) == 1
    submit_body = json.loads(submit_calls[0]["body"])
    assert submit_body["observe_only"] is True
    assert submit_body["questions"] == body["questions"], (
        "the same questions object is validated and submitted"
    )
    # Editing never writes production: only page/observe routes were called.
    for call in submitted["fetchCalls"]:
        assert call["url"] in ("/api/bootstrap", "/api/dps", "/api/test/history", "/api/test/cases",
                              "/api/test/validate", "/api/test/submit") or call["url"].startswith("/api/history") or (call["method"] == "GET" and call["url"].startswith("/api/test/submissions/")), call["url"]
    assert submitted["storage"] == []
    assert submitted["pwned"] is False and submitted["consoleMessages"] == []


def test_dp3_criteria_is_read_only_and_derived_from_handling_options(tmp_path):
    fixture = _questions_scenario(
        tmp_path,
        "dp3-worker-clarify",
        "edited: which handling option should be taken?",
        ("question", "edited question for the dp3 questions path"),
    )
    result = _run_dom(tmp_path, fixture["scenario"])
    opened = _snapshot(result, "opened")
    dp3 = next(question for question in opened["questions"] if question["id"] == "handling")
    assert dp3["criteriaInput"] is None, "dp3 criteria is not a free-text input"
    assert dp3["derived"], "dp3 criteria is shown as a read-only derivation"
    assert "readonly" in dp3["derived"].lower() or "只读" in dp3["derived"], dp3["derived"]
    for option in fixture["book"]["state"]["handling_options"]:
        assert option["description"] in dp3["derived"], (
            "the derivation reads state.handling_options (the single candidate source)"
        )

    validated = _snapshot(result, "validated")
    body = json.loads(
        next(call for call in validated["fetchCalls"] if call["url"] == "/api/test/validate")["body"]
    )
    sent = body["questions"]["handling"]
    assert sent["id"] == "handling"
    assert sent["instructions"].startswith("edited:")
    assert "criteria" not in sent, (
        "dp3 candidates live only in state.handling_options; the page never duplicates them into questions"
    )
    assert body["book"]["state"]["question"].startswith("edited question")


def test_all_four_cases_carry_their_complete_editable_questions(tmp_path):
    payloads = _published_payloads()
    scenario = {
        "hash": "#boot=dom-boot-code",
        "bootstrap": wb._bootstrap(payloads["token"]),
        "history": payloads["default"],
        "detailByOpaque": payloads["detailByOpaque"],
        "cases": _published_cases_payload(),
        "dps": payloads["dps"],
        "testHistory": payloads["testHistory"],
        "steps": [
            {"type": "click", "target": "#tab-playground"},
            {"type": "click", "target": "#pg-load"},
            {"type": "click", "target": "#pg-cases-load"},
        ]
        + [
            step
            for dp in CASES
            for step in (
                {"type": "setValue", "target": "#case-select", "value": dp},
                {"type": "click", "target": "#pg-case-open", "snapshot": "case-" + dp},
            )
        ],
    }
    result = _run_dom(tmp_path, scenario)
    expected_ids = {
        "dp1-dispatch-type": "triage_type",
        "dp2-checkpoint-split": "checkpoint_action",
        "dp3-worker-clarify": "handling",
        "dp25-signoff-conclusion": "q-conclusion",
    }
    for dp, question_id in expected_ids.items():
        opened = _snapshot(result, "case-" + dp)
        questions = opened["questions"]
        assert len(questions) == 1, (dp, questions)
        question = questions[0]
        assert question["id"] == question_id, (dp, question["id"])
        assert question["kind"] == "choice"
        assert question["instructions"].strip(), (dp, "instructions must be editable material")
        assert question["instructions"] == PUBLISHED_QUESTIONS[dp][0]["instructions"]
        assert json.loads(opened["editorValue"])["decision_point"] == dp
        if dp == "dp3-worker-clarify":
            assert question["criteriaInput"] is None, "dp3 criteria is derived, never typed"
            assert question["derived"] and "handling_options" in question["derived"].lower()
        else:
            assert question["derived"] is None
            if "criteria" in PUBLISHED_QUESTIONS[dp][0]:
                assert question["criteriaInput"], (dp, "published criteria is editable")
    # Loading/reading questions never calls the model or the observe routes.
    posts = [
        call for call in result["fetchCalls"]
        if call["method"] == "POST" and call["url"] != "/api/bootstrap"
    ]
    assert posts == [], posts


def test_real_case_route_questions_open_in_the_shipped_editor(tmp_path):
    """Real loopback case/DPS payloads, not the published-interface fixture."""
    payloads = wb._workbench_dom_payload(tmp_path)
    scenario = {
        "hash": "#boot=dom-boot-code",
        "bootstrap": wb._bootstrap(payloads["token"]),
        "history": payloads["default"],
        "cases": payloads["cases"],
        "dps": payloads["dps"],
        "testHistory": payloads["testHistory"],
        "steps": [
            {"type": "click", "target": "#tab-playground"},
            {"type": "click", "target": "#pg-load"},
            {"type": "click", "target": "#pg-cases-load"},
        ] + [step for case in payloads["cases"]["body"]["data"]["cases"] for step in (
            {"type": "setValue", "target": "#case-select", "value": case["dp"]},
            {"type": "click", "target": "#pg-case-open", "snapshot": case["dp"]},
        )],
    }
    result = _run_dom(tmp_path, scenario)
    for case in payloads["cases"]["body"]["data"]["cases"]:
        snapshot = _snapshot(result, case["dp"])
        assert json.loads(snapshot["editorValue"]) == case["book"]
        assert {q["id"]: q["instructions"] for q in snapshot["questions"]} == {
            qid: spec["instructions"] for qid, spec in case["questions"].items()
        }
        for question in snapshot["questions"]:
            if case["dp"] != "dp3-worker-clarify":
                assert json.loads(question["criteriaInput"]) == case["questions"][question["id"]]["labels"]
        assert json.loads(snapshot["materialValue"]) == case["book"]["state"]
        assert snapshot["error"] in (None, "")
    assert all(call["method"] == "GET" or call["url"] == "/api/bootstrap" for call in result["fetchCalls"])
    assert result["storageWrites"] == []


def test_no_case_questions_means_no_questions_field_is_sent(tmp_path):
    """Today's backend publishes no ``case.questions``: the page stays honest."""
    payloads = _published_payloads()
    book = json.loads((CASES_DIR / "dp1.json").read_text(encoding="utf-8"))["book"]
    cases = _published_cases_payload()
    for case in cases["body"]["data"]["cases"]:
        case.pop("questions", None)
    scenario = {
        "hash": "#boot=dom-boot-code",
        "bootstrap": wb._bootstrap(payloads["token"]),
        "history": payloads["default"],
        "detailByOpaque": payloads["detailByOpaque"],
        "cases": cases,
        "dps": payloads["dps"],
        "testHistory": payloads["testHistory"],
        "validate": {
            "status": 200,
            "body": _envelope({"dp": "dp1-dispatch-type", "ok": True, "issues": [], "observe_only": True}),
        },
        "steps": [
            {"type": "click", "target": "#tab-playground"},
            {"type": "click", "target": "#pg-load"},
            {"type": "click", "target": "#pg-cases-load"},
            {"type": "setValue", "target": "#case-select", "value": "dp1-dispatch-type"},
            {"type": "click", "target": "#pg-case-open", "snapshot": "opened"},
            {"type": "click", "target": "#pg-validate", "snapshot": "validated"},
        ],
    }
    result = _run_dom(tmp_path, scenario)
    opened = _snapshot(result, "opened")
    assert opened["questions"] == []
    assert "未记录" in (opened["questionsStatus"] or ""), opened["questionsStatus"]
    validated = _snapshot(result, "validated")
    body = json.loads(
        next(call for call in validated["fetchCalls"] if call["url"] == "/api/test/validate")["body"]
    )
    assert "questions" not in body, "no invented questions reach the server"
    assert body["book"] == book


def test_questions_editing_does_not_change_production_files(tmp_path):
    registry = ASSET_DIR / "decide_registry.json"
    case_paths = sorted(CASES_DIR.glob("*.json"))

    def digest() -> dict[str, str]:
        return {
            path.relative_to(ASSET_DIR).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [registry, *case_paths]
        }

    before = digest()
    fixture = _questions_scenario(
        tmp_path,
        "dp2-checkpoint-split",
        "edited: continue, narrow, split or escalate?",
        ("pm_decision_background", "edited background for the dp2 questions path"),
    )
    _run_dom(tmp_path, fixture["scenario"])
    assert digest() == before, "a test edit never rewrites the registry or a shipped case"


# ---------------------------------------------------------------------------
# Shipped asset discipline (CSP, no unsafe constructs, SVG DOM API)
# ---------------------------------------------------------------------------


def test_port_five_row_paging_and_no_inline_diagnostics(tmp_path):
    payloads = _published_payloads()
    data = payloads["default"]["body"]["data"]
    data.update(limit=5, total=9, has_more=True, stats={"archive_rows":54}, warnings=["free-text-withheld: internal diagnostic"], filters_basis=["no redactor injected: internal policy"])
    result = _run_dom(tmp_path, {
        "hash":"#boot=dom-boot-code", "bootstrap":wb._bootstrap(payloads["token"]),
        "history":payloads["default"], "steps":[{"type":"click","target":"#page-next","snapshot":"next"}],
    })
    boot = _snapshot(result, "boot")
    assert boot["portText"] == "端口：43170"
    assert "limit=5&offset=0" in result["fetchCalls"][1]["url"]
    assert any("limit=5&offset=5" in call["url"] for call in result["fetchCalls"])
    for text in ("下拉全集", "筛选输出策略", "读取统计", "archive_rows=", "internal diagnostic", "internal policy"):
        assert text not in boot["bodyText"]
    assert "部分详情因安全限制未显示" in boot["bodyText"]


def test_dag_details_stack_at_every_viewport():
    css = (ASSET_DIR / CSS_NAME).read_text(encoding="utf-8")
    layout = re.search(r"\.dag-layout\s*\{([^}]+)\}", css).group(1)
    assert "flex-direction: column" in layout
    side = re.search(r"\.dag-side\s*\{([^}]+)\}", css).group(1)
    assert "width: 100%" in side


def test_shipped_readable_assets_keep_the_csp_and_safe_dom_discipline():
    html = (ASSET_DIR / HTML_NAME).read_text(encoding="utf-8")
    js = (ASSET_DIR / JS_NAME).read_text(encoding="utf-8")
    css = (ASSET_DIR / CSS_NAME).read_text(encoding="utf-8")

    for needle in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert needle not in js, needle
    assert "textContent" in js
    assert "createElementNS" in js and "http://www.w3.org/2000/svg" in js, "SVG via the safe DOM API"
    assert "setAttribute" in js
    assert ".style." not in js, "no inline styles (CSP has no 'unsafe-inline')"
    assert "localStorage" not in js and "sessionStorage" not in js and "document.cookie" not in js
    assert "X-MW-Monitor-Token" in js
    assert "@import" not in css
    assert not re.search(r"<[^>]+\son[a-z]+\s*=", html), "no inline event handler attributes"
    assert "<script>" not in html and "javascript:" not in html
    assert css.count(".dag-pos-") >= 10, "every graph position is a static class (no inline style)"
    assert re.search(r"\.dag-pos-0\b", css)
    assert "dag-edge" in css and "dag-node" in css
    csp = decision_monitor._CSP
    assert "'unsafe-inline'" not in csp and "unsafe-eval" not in csp
    for element_id in ("dag-graph", "dag-node-detail", "pg-questions", "pg-question", "pg-request-preview"):
        if element_id in ("pg-question", "pg-request-preview"):
            continue
        assert html.count(' id="' + element_id + '"') == 1, element_id
    assert html.count(' id="dag-node-detail"') == 1


def _interaction_scenario():
    payloads = _published_payloads()
    return {
        "hash": "#boot=fixture", "bootstrap": wb._bootstrap(payloads["token"]),
        "history": payloads["default"], "dps": payloads["dps"],
        "testHistory": payloads["testHistory"], "submission": payloads["submission"],
        "scaffold": {"status": 200, "body": _envelope({"book": CASES["dp1-dispatch-type"]["book"]})},
        "validate": {"status": 200, "body": _envelope({"ok": True, "request_preview": {"model": "jev-latest", "state": {"task_goal": "preview-only"}, "questions": {}}})},
    }


def test_test_tab_and_explicit_refresh_load_only_test_reads_and_switch_dag(tmp_path):
    scenario = _interaction_scenario()
    scenario["steps"] = [
        {"type": "click", "target": '[data-testid="record-dag-open"]'},
        {"type": "click", "target": "#tab-playground", "snapshot": "test"},
        {"type": "click", "target": "#dashboard-refresh", "snapshot": "refresh"},
    ]
    result = _run_dom(tmp_path, scenario)
    switched = _snapshot(result, "test")
    assert switched["dialogVisible"] is False
    assert [n["id"] for n in switched["pgGraph"]["nodes"]] == NODE_IDS
    assert any(c["url"] == "/api/test/history" for c in switched["fetchCalls"])
    assert len(_snapshot(result, "refresh")["fetchCalls"]) > len(switched["fetchCalls"])
    assert all(c["method"] == "GET" or c["url"] == "/api/bootstrap" for c in result["fetchCalls"])


def test_scaffold_preview_and_refusal_have_local_feedback_without_fake_api_capture(tmp_path):
    scenario = _interaction_scenario()
    scenario["steps"] = [
        {"type": "click", "target": "#tab-playground"},
        {"type": "click", "target": "#pg-scaffold", "snapshot": "scaffold"},
        {"type": "click", "target": "#pg-validate", "snapshot": "preview"},
        {"type": "click", "target": '[data-testid="pg-dag-node"][data-node-id="request"]', "snapshot": "request"},
        {"type": "setValue", "target": "#material-editor", "value": "{bad"},
        {"type": "dispatch", "target": "#material-editor", "event": {"type": "input"}},
        {"type": "click", "target": "#pg-submit", "snapshot": "refused"},
    ]
    result = _run_dom(tmp_path, scenario)
    assert "骨架" in _snapshot(result, "scaffold")["pgOperations"]
    assert "预览" in _snapshot(result, "preview")["pgOperations"]
    assert "preview-only" in _snapshot(result, "request")["pgNodeDetail"]
    assert "未发送" in _snapshot(result, "request")["pgNodeDetail"]
    assert not _snapshot(result, "request")["captures"]
    assert "拒绝" in _snapshot(result, "refused")["pgOperations"]
    assert not any(c["url"] == "/api/test/submit" for c in result["fetchCalls"])


def test_submission_polls_each_second_until_terminal_and_retry_uses_new_id(tmp_path):
    scenario = _interaction_scenario()
    terminal = dict(scenario["submission"]["body"]["data"], record_status="recorded")
    running = dict(terminal, state="running", decision_ran=False, http_attempts=0, call_id=None)
    scenario["submit"] = [
        {"status": 200, "body": _envelope(terminal), "defer": "submit"},
        {"status": 200, "body": _envelope(terminal)},
    ]
    scenario["submission"] = [scenario["submission"],
        {"status": 200, "body": _envelope(running)},
        {"status": 200, "body": _envelope(terminal)},
        {"status": 200, "body": _envelope(terminal)},
    ]
    scenario["steps"] = [
        {"type": "click", "target": "#tab-playground"},
        {"type": "click", "target": "#pg-scaffold"},
        {"type": "click", "target": "#pg-submit", "snapshot": "start"},
        {"type": "tick", "snapshot": "running"},
        {"type": "click", "target": '[data-testid="pg-dag-node"][data-node-id="dp"]'},
        {"type": "tick", "snapshot": "terminal"},
        {"type": "release", "id": "submit", "snapshot": "done"},
        {"type": "tick", "snapshot": "stopped"},
        {"type": "click", "target": "#pg-retry", "snapshot": "retried"},
    ]
    result = _run_dom(tmp_path, scenario)
    start = _snapshot(result, "start")
    assert start["submitDisabled"] and start["activeTimers"] == 1
    assert "进行" in start["pgStatus"]
    running = _snapshot(result, "running")
    assert len(running["fetchCalls"]) > len(start["fetchCalls"])
    assert running["pgHistory"] and running["pgOperations"]
    terminal_snap = _snapshot(result, "terminal")
    assert terminal_snap["activeTimers"] == 0
    assert "节点 dp" in terminal_snap["pgNodeDetail"]
    done, stopped = _snapshot(result, "done"), _snapshot(result, "stopped")
    assert len(done["fetchCalls"]) == len(stopped["fetchCalls"])
    assert not done["submitDisabled"] and "succeeded" in done["pgStatus"]
    bodies = [json.loads(c["body"]) for c in result["fetchCalls"] if c["url"] == "/api/test/submit"]
    assert len(bodies) == 2 and bodies[0]["submit_id"] != bodies[1]["submit_id"]
    assert bodies[1]["retry_of"] == bodies[0]["submit_id"]
    assert all(b["observe_only"] is True for b in bodies)
    assert all(d == 1000 for d in stopped["timerDelays"])
    assert result["storageWrites"] == []


@pytest.mark.parametrize("stage", ["history", "detail"])
def test_late_poll_does_not_overwrite_final_result_or_overlap(tmp_path, stage):
    scenario = _interaction_scenario()
    terminal = dict(scenario["submission"]["body"]["data"], record_status="recorded")
    running = dict(terminal, state="running")
    scenario["submit"] = {"status": 200, "body": _envelope(terminal), "defer": "submit"}
    if stage == "history":
        scenario["testHistory"] = [scenario["testHistory"],
            {"status": 200, "body": _envelope({"records": [], "total": 0}), "defer": "poll"},
            _interaction_scenario()["testHistory"]]
    else:
        scenario["submission"] = [scenario["submission"],
            {"status": 200, "body": _envelope(running), "defer": "poll"},
            {"status": 200, "body": _envelope(terminal)}]
    scenario["steps"] = [
        {"type": "click", "target": "#tab-playground"},
        {"type": "click", "target": "#pg-scaffold"},
        {"type": "click", "target": "#pg-submit"},
        {"type": "tick", "snapshot": "held"},
        {"type": "tick", "snapshot": "no-overlap"},
        {"type": "release", "id": "submit", "snapshot": "finished"},
        {"type": "release", "id": "poll", "snapshot": "late"},
    ]
    result = _run_dom(tmp_path, scenario)
    held = _snapshot(result, "held")
    assert held["activeTimers"] == 0
    assert held["fetchCalls"] == _snapshot(result, "no-overlap")["fetchCalls"]
    finished, late = _snapshot(result, "finished"), _snapshot(result, "late")
    assert late["fetchCalls"] == finished["fetchCalls"]
    assert late["pgStatus"] == finished["pgStatus"] and "succeeded" in late["pgStatus"]
    assert late["pgHistory"] == finished["pgHistory"]
    assert late["pgGraph"] == finished["pgGraph"]
    assert late["activeTimers"] == 0
    assert sum(c["url"] == "/api/test/submit" for c in result["fetchCalls"]) == 1


def test_poll_read_failure_retries_reads_only_and_submit_failure_is_honest(tmp_path):
    scenario = _interaction_scenario()
    scenario["submit"] = {"status": 503, "body": {"ok": False, "error": {"code": "transport", "message": "unreadable"}}, "defer": "submit"}
    scenario["testHistory"] = [scenario["testHistory"],
        {"status": 503, "body": {"ok": False, "error": {"code": "offline", "message": "fixture"}}},
        _interaction_scenario()["testHistory"], _interaction_scenario()["testHistory"]]
    scenario["submission"] = [scenario["submission"],
        {"status": 200, "body": _envelope({"dp": "dp1-dispatch-type", "state": "running", "attempts": []})}]
    scenario["steps"] = [
        {"type": "click", "target": "#tab-playground"},
        {"type": "click", "target": "#pg-scaffold"},
        {"type": "click", "target": "#pg-submit"},
        {"type": "tick", "snapshot": "failed-read"},
        {"type": "tick", "snapshot": "running"},
        {"type": "release", "id": "submit", "snapshot": "failure"},
        {"type": "tick", "snapshot": "stopped"},
    ]
    result = _run_dom(tmp_path, scenario)
    assert "状态读取失败" in _snapshot(result, "failed-read")["pgStatus"]
    assert _snapshot(result, "failed-read")["activeTimers"] == 1
    failed = _snapshot(result, "failure")
    assert "失败" in failed["pgStatus"] and "未知" in failed["bodyText"]
    assert not failed["submitDisabled"] and failed["activeTimers"] == 0
    assert failed["fetchCalls"] == _snapshot(result, "stopped")["fetchCalls"]
    assert sum(c["url"] == "/api/test/submit" for c in result["fetchCalls"]) == 1

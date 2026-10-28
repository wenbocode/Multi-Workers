"use strict";
/*
 * mw decide monitor - history tab.
 *
 * Security shape (design §9):
 * - the page token is exchanged from a single-use boot code in the URL
 *   fragment, kept in this closure only, and never written to storage or a URL;
 * - the fragment is cleared before anything else happens;
 * - every rendered value goes through textContent (the el() helper below); no
 *   markup string is ever assigned; there is no dynamic code evaluation.
 * - opening, refreshing and filtering only read /api/history; switching to the
 *   DP-test tab reads nothing at all. Only an explicit click loads the DP
 *   registry and the isolated test records (metadata + records), and only an
 *   explicit "observe submit" click can reach the model - it carries a fresh
 *   submission id, ``observe_only=true`` and a book the same review accepted.
 * - every DP-test value is rendered with textContent too; the persisted answer
 *   is the safe projection the provider already redacted, never a raw body.
 */
(function () {
  const TOKEN_HEADER = "X-MW-Monitor-Token";
  const NOT_RECORDED = "未记录";
  const UNKNOWN = "unknown";
  const SCOPE_DEFAULT = "production";
  const STAGE_ORDER = [
    "suggested",
    "adopted",
    "consumed",
    "responded",
    "steered",
    "executed",
    "human_answer",
    "human_override",
    "authority_change",
    "signoff",
    "settled",
    "book",
  ];
  const STAGE_LABELS = {
    suggested: "模型建议",
    adopted: "已采纳",
    consumed: "已吸收",
    responded: "已应答",
    steered: "已引导",
    executed: "已执行",
    human_answer: "人工回答",
    human_override: "人工覆盖",
    authority_change: "授权调整",
    signoff: "签收",
    settled: "settle",
    book: "决策本快照",
  };
  const STATE_LABELS = {
    recorded: "已记录",
    pending: "待发生（pending，未记录）",
    "not-recorded": NOT_RECORDED,
    inferred: "inferred（推断关联）",
    unknown: "unknown（未知）",
  };
  // Closed processing states of the backend workbench projection (T06 owns the
  // derivation). The UI only renders; it never infers a state from wire rows.
  const PROCESSING_STATE_LABELS = {
    processing: "处理中",
    completed: "处理完成",
    failed: "失败",
    legacy: "旧数据无状态",
  };
  // Node availability as recorded by T06: missing is "not recorded", failed is
  // a *recorded failure* (never folded into "not recorded").
  const DAG_NODE_STATE_LABELS = {
    observed: "已记录",
    missing: NOT_RECORDED,
    failed: "失败（已记录）",
    // UI-only, used by the isolated test-scope DAG: the observation path never
    // performs a business action, so that node is "not executed", not missing.
    "not-executed": "未执行（模拟）",
  };
  // The four offline cases the test page can load (the backend is the authority;
  // this list is only used by the offline local structural check).
  const DESIGN_FIELDS = {
    "dp1-dispatch-type": ["task_goal", "task_requirements", "task_deliverables"],
    "dp2-checkpoint-split": [
      "task_goal",
      "task_requirements",
      "task_deliverables",
      "pm_decision_background",
    ],
    "dp3-worker-clarify": ["question", "background", "handling_options"],
    "dp25-signoff-conclusion": [
      "delivery_goal",
      "actual_completion",
      "verification_evidence",
      "unfinished_impact",
    ],
  };
  const PLACEHOLDER_PATTERN = /(<string|<integer|<number|<boolean|<array|<object|EVIDENCE_PLACEHOLDER|TODO|TBD|FIXME|\.\.\.|\u2026)/;

  // The workbench graph is drawn from fixed geometry (no measurement, no inline
  // style): one SVG edge layer plus absolutely positioned node controls whose
  // positions come from static ``dag-pos-N`` classes in the shipped CSS.
  const SVG_NS = "http://www.w3.org/2000/svg";
  const DAG_NODE_WIDTH = 176;
  const DAG_NODE_HEIGHT = 66;
  const DAG_GAP_X = 32;
  const DAG_GAP_Y = 96;
  const DAG_MARGIN = 12;
  const DAG_COLUMNS = 5;
  // Business material labels (the dp vocabulary of the four approved dps). An
  // unknown key is shown with its own name: material is never dropped silently.
  const MATERIAL_LABELS = {
    task_goal: "任务目标",
    task_requirements: "任务要求",
    task_deliverables: "交付物",
    pm_decision_background: "PM 决策背景",
    worker_execution: "worker 执行情况（真实、可选）",
    question: "问题原文",
    background: "背景",
    handling_options: "处理候选",
    delivery_goal: "交付目标与验收条件",
    actual_completion: "实际完成情况",
    verification_evidence: "验证证据",
    unfinished_impact: "未完成项及影响",
    verified: "已验证",
    unverified: "未验证",
    current_state: "现状",
    decision_reason: "需要决策的原因",
    constraints_impact: "约束与影响",
    id: "候选 id",
    label: "候选名称",
    description: "候选说明",
    time_budget: "时间预算",
  };
  // Input material must never re-render the audit wrapper of the book snapshot.
  const MATERIAL_HIDDEN_KEYS = {
    book: true,
    book_ref: true,
    book_version: true,
    state_digest: true,
    questions_version: true,
    mode: true,
    intent: true,
    basis: true,
    logical_id: true,
    record_version: true,
    schema_version: true,
    decision_point: true,
  };

  const state = {
    token: null,
    booted: false,
    filters: { key: "", dp: "", source: "", status: "", scope: SCOPE_DEFAULT },
    offset: 0,
    limit: 50,
    total: 0,
    hasMore: false,
    recordCount: 0,
    lastHistory: null,
    lastDetail: null,
    busy: false,
    playground: {
      loaded: false,
      points: [],
      byId: Object.create(null),
      selected: "",
      budget: null,
      transport: null,
      config: null,
      observeOnly: false,
      cases: [],
      caseLoaded: null,
      caseQuestions: null,
      questionNodes: [],
      submitId: null,
      lastDigest: null,
      lastSubmittedId: null,
      history: null,
      inflight: false,
      seq: 0,
    },
  };

  // -- tiny safe DOM helpers ------------------------------------------------

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (name) {
        const value = attrs[name];
        if (value === null || value === undefined || value === false) return;
        if (name === "text") {
          node.textContent = String(value);
        } else if (name === "class") {
          node.className = String(value);
        } else {
          node.setAttribute(name, value === true ? "" : String(value));
        }
      });
    }
    (children || []).forEach(function (child) {
      if (child === null || child === undefined) return;
      if (typeof child === "string") {
        node.appendChild(document.createTextNode(child));
      } else {
        node.appendChild(child);
      }
    });
    return node;
  }

  function line(label, value, className) {
    return el("p", { class: className || "meta" }, [
      el("strong", { text: label + "：" }),
      el("span", { text: value }),
    ]);
  }

  function definitionList(pairs) {
    const list = el("dl", { class: "detail-grid" });
    pairs.forEach(function (pair) {
      list.appendChild(el("dt", { text: pair[0] }));
      list.appendChild(el("dd", { text: pair[1] }));
    });
    return list;
  }

  function setText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = value === null || value === undefined ? "" : String(value);
  }

  function setHidden(id, hidden) {
    const node = document.getElementById(id);
    if (!node) return;
    if (hidden) {
      node.setAttribute("hidden", "");
    } else {
      node.removeAttribute("hidden");
    }
  }

  function setDisabled(id, disabled) {
    const node = document.getElementById(id);
    if (!node) return;
    if (disabled) {
      node.setAttribute("disabled", "");
    } else {
      node.removeAttribute("disabled");
    }
  }

  function inputValue(id) {
    const node = document.getElementById(id);
    return node && typeof node.value === "string" ? node.value.trim() : "";
  }

  function selectValue(id, fallback) {
    const node = document.getElementById(id);
    const value = node && typeof node.value === "string" ? node.value : "";
    return value || fallback;
  }

  // -- honest value labels --------------------------------------------------

  function isMissing(value) {
    return value === null || value === undefined;
  }

  function missing(value) {
    return isMissing(value) ? NOT_RECORDED : String(value);
  }

  function flag(value) {
    if (isMissing(value)) return NOT_RECORDED;
    return value === true ? "true" : "false";
  }

  function formatFree(value) {
    if (isMissing(value)) return NOT_RECORDED;
    if (typeof value === "string") return value === "" ? "（空）" : value;
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    if (Array.isArray(value)) {
      if (!value.length) return "（空列表）";
      return value.map(formatFree).join("; ");
    }
    if (typeof value === "object") {
      const keys = Object.keys(value);
      if (!keys.length) return "（空对象）";
      return keys
        .map(function (key) {
          return key + ": " + formatFree(value[key]);
        })
        .join("; ");
    }
    return String(value);
  }

  function stateLabel(value) {
    if (isMissing(value)) return NOT_RECORDED;
    return STATE_LABELS[value] || String(value);
  }

  function claimParts(claim) {
    if (!claim || typeof claim !== "object") return { value: UNKNOWN, basis: "" };
    const basis = Array.isArray(claim.basis) ? claim.basis.join("; ") : "";
    let value = isMissing(claim.value) ? UNKNOWN : String(claim.value);
    if (basis.toLowerCase().indexOf("inferred") !== -1) value += "（inferred 推断）";
    return { value: value, basis: basis };
  }

  function countedValue(recorded, value) {
    if (recorded !== true) return NOT_RECORDED;
    return isMissing(value) ? NOT_RECORDED : String(value);
  }

  function usageText(usage, options) {
    const opts = options || {};
    if (!usage || typeof usage !== "object") return NOT_RECORDED;
    let recorded = usage.recorded === true;
    let counters = usage.counters && typeof usage.counters === "object" ? usage.counters : null;
    if (!counters && usage.recorded === undefined) {
      // A per-attempt / per-call usage row is a bare counter map: the writer
      // recorded exactly these keys, so they are facts (missing keys are not
      // enumerated at that level and are never filled with 0).
      const direct = {};
      Object.keys(usage).forEach(function (name) {
        if (typeof usage[name] === "number") direct[name] = usage[name];
      });
      if (Object.keys(direct).length) {
        counters = direct;
        recorded = true;
      }
    }
    if (!recorded) {
      return NOT_RECORDED + (opts.compact ? "" : "（未采集 usage，不按 0 显示）");
    }
    counters = counters || {};
    const names = Object.keys(counters);
    const parts = names.map(function (name) {
      return name + "=" + String(counters[name]);
    });
    const missingNames = Array.isArray(usage.missing) ? usage.missing : [];
    let text = parts.length ? parts.join(" ") : NOT_RECORDED;
    if (missingNames.length) text += " · 缺失（未补 0）：" + missingNames.join(", ");
    if (usage.semantics && usage.semantics !== "none") text += " · " + usage.semantics;
    if (usage.conflicting === true) text += " · 多次尝试 usage 不一致";
    if (opts.compact && usage.complete !== true) text += " · 不完整";
    return text;
  }

  function callsSummary(counts) {
    if (!counts || typeof counts !== "object") return NOT_RECORDED;
    const recorded = counts.recorded === true;
    const parts = [
      "逻辑调用=" + countedValue(recorded, counts.logical_calls),
      "HTTP attempts=" + countedValue(recorded, counts.actual_http_attempts),
      "zero_call=" + countedValue(recorded, counts.zero_call),
    ];
    if (recorded && counts.unrecorded_wire_attempts) {
      parts.push("未记录 wire_attempts=" + String(counts.unrecorded_wire_attempts));
    }
    if (!recorded) parts.push("（未采集调用台账）");
    return parts.join(" · ");
  }

  // -- workbench projection helpers ----------------------------------------

  function workbenchOf(record) {
    const workbench = record && record.workbench;
    return workbench && typeof workbench === "object" && !Array.isArray(workbench) ? workbench : null;
  }

  function hasV2Workbench(record) {
    const workbench = workbenchOf(record);
    return Boolean(workbench && workbench.record_version === 2);
  }

  function dagAvailable(record) {
    // The v2 creation fact is the explicit marker (T06). The list projection
    // carries nodes=[] by contract, so availability never depends on bodies;
    // the ten nodes are read from the single-record detail read.
    return hasV2Workbench(record);
  }

  function processingStateOf(record) {
    const workbench = workbenchOf(record);
    // No workbench block at all is the honest old-data answer.
    if (!workbench) return "legacy";
    const state = typeof workbench.processing_state === "string" ? workbench.processing_state : "";
    return state || "unknown";
  }

  function processingLabel(record) {
    const state = processingStateOf(record);
    if (state === "unknown") return NOT_RECORDED;
    return PROCESSING_STATE_LABELS[state] || state + "（非闭集）";
  }

  function selectionEntries(selection) {
    // T06 records the selection as stored (a string, the stored answer mapping,
    // or None). Nothing is composed here: each recorded question gets one line.
    if (isMissing(selection)) return [];
    if (typeof selection === "string") {
      return selection ? [{ question: "", value: selection, label: "", basis: "" }] : [];
    }
    if (typeof selection !== "object" || Array.isArray(selection)) return [];
    if (typeof selection.value === "string" || typeof selection.value === "number") {
      return [{
        question: typeof selection.question_id === "string" ? selection.question_id : "",
        value: String(selection.value),
        label: typeof selection.label === "string" ? selection.label : "",
        basis: Array.isArray(selection.basis) ? selection.basis.join("; ") : "",
      }];
    }
    const entries = [];
    Object.keys(selection).forEach(function (questionId) {
      const spec = selection[questionId];
      if (spec === null || spec === undefined) {
        entries.push({ question: questionId, value: NOT_RECORDED, label: "", basis: "" });
        return;
      }
      if (typeof spec !== "object" || Array.isArray(spec)) {
        entries.push({ question: questionId, value: formatFree(spec), label: "", basis: "" });
        return;
      }
      const value = isMissing(spec.value) ? UNKNOWN : formatFree(spec.value);
      entries.push({
        question: questionId,
        value: value,
        label: typeof spec.label === "string" ? spec.label : "",
        basis: Array.isArray(spec.basis) ? spec.basis.join("; ") : "",
      });
    });
    return entries;
  }

  function nodeStatusOf(node) {
    // T06 emits ``status`` in observed/missing/failed; the local test-scope DAG
    // additionally uses not-executed for the observe-only action node.
    const value = node && (typeof node.status === "string" ? node.status : node.state);
    return typeof value === "string" && value ? value : "missing";
  }

  function nodeStateLabel(status) {
    if (isMissing(status) || status === "") return NOT_RECORDED;
    return DAG_NODE_STATE_LABELS[status] || String(status);
  }

  // -- list rendering -------------------------------------------------------

  function renderRecordRow(record) {
    const row = el("tr", {
      "data-testid": "record-row",
      "data-opaque": record.opaque_id || "",
      "data-processing-state": processingStateOf(record),
    });
    const workbench = workbenchOf(record);
    const selectableDag = dagAvailable(record);

    const keyCell = el("td");
    keyCell.appendChild(el("div", { text: "key=" + missing(record.key) }));
    keyCell.appendChild(el("div", { class: "basis", text: "task=" + missing(record.task_key) }));
    const actions = el("div", { class: "row-actions" });
    if (selectableDag) {
      const dagButton = el("button", {
        type: "button",
        "data-testid": "record-dag-open",
        "data-opaque": record.opaque_id || "",
      }, ["单次 DAG"]);
      dagButton.addEventListener("click", function (event) {
        if (event && typeof event.stopPropagation === "function") event.stopPropagation();
        openRecord(record.opaque_id, "dag");
      });
      actions.appendChild(dagButton);
    }
    // Legacy rows keep exactly one entry (the technical log) and no DAG entry.
    const logButton = el("button", {
      type: "button",
      "data-testid": selectableDag ? "record-log-open" : "record-open",
      "data-opaque": record.opaque_id || "",
    }, ["日志"]);
    logButton.addEventListener("click", function (event) {
      if (event && typeof event.stopPropagation === "function") event.stopPropagation();
      openRecord(record.opaque_id, "log");
    });
    actions.appendChild(logButton);
    keyCell.appendChild(actions);
    row.appendChild(keyCell);

    row.appendChild(el("td", { text: workbench && workbench.record_version === 2 ? missing(workbench.question_summary) : NOT_RECORDED }));

    const dpValue = workbench && workbench.dp_id ? workbench.dp_id : record.dp;
    row.appendChild(el("td", { text: missing(dpValue) }));

    const selectionCell = el("td");
    const entries = selectionEntries(workbench && workbench.selection);
    if (!entries.length) {
      selectionCell.appendChild(el("span", { text: NOT_RECORDED }));
    } else {
      entries.forEach(function (entry) {
        const block = el("div", { class: "selection", "data-question": entry.question || "" });
        block.appendChild(el("div", { text: entry.value + (entry.label ? " · " + entry.label : "") }));
        if (entry.question) block.appendChild(el("div", { class: "basis", text: "question=" + entry.question }));
        if (entry.basis) block.appendChild(el("div", { class: "basis", text: "依据：" + entry.basis }));
        selectionCell.appendChild(block);
      });
    }
    row.appendChild(selectionCell);

    const state = processingStateOf(record);
    const stateCell = el("td");
    stateCell.appendChild(el("span", {
      class: "state state-" + state,
      "data-testid": "record-state",
      "data-processing-state": state,
      text: processingLabel(record),
    }));
    if (state === "legacy") {
      stateCell.appendChild(el("div", { class: "basis", text: "无 v2 创建事实（旧数据）" }));
    }
    row.appendChild(stateCell);

    if (selectableDag) {
      row.addEventListener("click", function () {
        openRecord(record.opaque_id, "dag");
      });
    }
    return row;
  }

  function renderFiltersNotes(data) {
    const notes = [];
    const emitted = data && data.filters && typeof data.filters === "object" ? data.filters : {};
    const withheld = data && Array.isArray(data.filters_withheld) ? data.filters_withheld : [];
    const basis = data && Array.isArray(data.filters_basis) ? data.filters_basis : [];
    ["key", "dp", "source", "status", "scope"].forEach(function (name) {
      if (!Object.prototype.hasOwnProperty.call(emitted, name)) return;
      const value = emitted[name];
      notes.push(name + "=" + (value === null ? NOT_RECORDED + "（本次输出已省略）" : value === "" ? "（无）" : value));
    });
    if (withheld.length) notes.push("筛选值在本次输出中已省略（仅报告名称）：" + withheld.join(", "));
    basis.forEach(function (entry) {
      notes.push("筛选输出策略：" + String(entry));
    });
    setText("filters-notes", notes.join(" · "));
  }

  function renderHistoryStats(data) {
    const stats = data && data.stats && typeof data.stats === "object" ? data.stats : null;
    const warnings = data && Array.isArray(data.warnings) ? data.warnings : [];
    const parts = [];
    if (stats) {
      Object.keys(stats).forEach(function (name) {
        parts.push(name + "=" + formatFree(stats[name]));
      });
    }
    if (!parts.length) parts.push("stats=" + NOT_RECORDED);
    parts.push("warnings=" + (warnings.length ? warnings.join("; ") : "（无）"));
    setText("history-stats", "读取统计：" + parts.join(" · "));
  }

  function renderFacetOptions(data) {
    const facets = data && data.facets && typeof data.facets === "object" ? data.facets : null;
    const keys = facets && Array.isArray(facets.keys) ? facets.keys : null;
    const dps = facets && Array.isArray(facets.dps) ? facets.dps : null;
    const emitted = data && data.filters && typeof data.filters === "object" ? data.filters : {};
    const withheld = data && Array.isArray(data.filters_withheld) ? data.filters_withheld : [];
    // The value a dropdown shows is the value THIS response echoed
    // (`data.filters`). A name the output policy withheld is never re-inserted
    // from local state, so a recognised secret cannot be echoed back into the DOM.
    function applied(name) {
      if (withheld.indexOf(name) !== -1) return "";
      if (Object.prototype.hasOwnProperty.call(emitted, name)) return emitted[name] || "";
      return state.filters[name] || "";
    }
    renderSelectOptions("filter-key", keys, applied("key"));
    renderSelectOptions("filter-dp", dps, applied("dp"));
    if (keys && dps) {
      setText(
        "facets-notes",
        "key/DP 下拉全集（后端快照）：keys=" + String(keys.length) + " · dps=" + String(dps.length) +
          "；下拉不受分页影响，只在这里取值。"
      );
    } else {
      setText(
        "facets-notes",
        "key/DP 下拉全集：未记录（后端 facets 未记录）。只保留当前已选值，不按本页记录推断全集。"
      );
    }
  }

  function renderSelectOptions(id, values, current) {
    const node = document.getElementById(id);
    if (!node) return;
    node.replaceChildren();
    node.appendChild(el("option", { value: "", text: "全部" }));
    const list = [];
    (values || []).forEach(function (value) {
      if (typeof value === "string" && value && list.indexOf(value) === -1) list.push(value);
    });
    // Keep the applied filter visible even when a stale facet snapshot lacks it.
    if (current && list.indexOf(current) === -1) list.unshift(current);
    list.forEach(function (value) {
      node.appendChild(el("option", { value: value, text: value }));
    });
    node.value = current || "";
  }

  function renderHistory(data) {
    const body = document.getElementById("history-rows");
    if (body) body.replaceChildren();
    const records = data && Array.isArray(data.records) ? data.records : [];
    renderFacetOptions(data);
    records.forEach(function (record) {
      if (body) body.appendChild(renderRecordRow(record || {}));
    });
    if (!records.length && body) {
      const empty = el("tr", null, [
        el("td", { colspan: "5", class: "empty", text: "未记录任何决策记录（当前筛选没有可显示的记录）" }),
      ]);
      body.appendChild(empty);
    }
    setText(
      "history-summary",
      "共 " + missing(data && data.total) +
        " 条 · 本页 " + String(records.length) + " 条 · offset " +
        missing(data && data.offset) +
        " · limit " + missing(data && data.limit)
    );
    const offset = data && typeof data.offset === "number" ? data.offset : null;
    const total = data && typeof data.total === "number" ? data.total : NOT_RECORDED;
    const start = records.length && offset !== null ? offset + 1 : 0;
    const end = offset !== null ? offset + records.length : NOT_RECORDED;
    setText("page-info", "第 " + String(start) + "–" + String(end) + " 条 / 共 " + String(total) + " 条");
    setDisabled("page-prev", !(offset !== null && offset > 0));
    setDisabled("page-next", data.has_more !== true);
    renderHistoryStats(data);
  }

  // -- readable rendering helpers -------------------------------------------

  function parseJson(text) {
    if (typeof text !== "string") return { ok: false, value: null };
    try {
      return { ok: true, value: JSON.parse(text) };
    } catch (error) {
      return { ok: false, value: null };
    }
  }

  function formatCaptureText(text) {
    // The stored capture is the only authority: valid JSON is shown pretty,
    // anything else is shown verbatim. The raw string is never rewritten for
    // copying (see copyCaptureRaw), so the view and the copy stay distinct.
    const parsed = parseJson(text);
    if (parsed.ok) {
      try {
        return { kind: "json", display: JSON.stringify(parsed.value, null, 2) };
      } catch (error) {
        return { kind: "text", display: String(text) };
      }
    }
    return { kind: "text", display: String(text) };
  }

  function captureStateOf(copy) {
    if (!copy || typeof copy !== "object") {
      return { status: "missing", text: "未记录（未采集）" };
    }
    if (copy.output_omitted === true) {
      return { status: "omitted", text: "本次输出省略正文（存储层仍有记录；此处不补造）" };
    }
    if (isMissing(copy.text) || copy.text_omitted === true) {
      return { status: "missing", text: "未记录（未采集正文）" };
    }
    const marks = [];
    if (copy.redactions) marks.push("已脱敏 " + String(copy.redactions) + " 处");
    if (copy.truncated === true) marks.push("已截断（存储正文不完整）");
    if (copy.byte_exact !== true && !copy.truncated) marks.push("非逐字节原文");
    if (marks.length) {
      return {
        status: copy.truncated === true ? "truncated" : "redacted",
        text: marks.join(" · ") + "（复制得到的是当前存储正文，不是完整原文）",
      };
    }
    return { status: "complete", text: "完整原文" };
  }

  function copyCaptureRaw(text, statusNode) {
    const raw = String(text);
    const done = function (ok) {
      if (!statusNode) return;
      statusNode.textContent = ok
        ? "已复制原始捕获（" + String(raw.length) + " 字符）"
        : "复制失败：请手动选择正文";
    };
    if (
      typeof navigator !== "undefined" &&
      navigator &&
      navigator.clipboard &&
      typeof navigator.clipboard.writeText === "function"
    ) {
      try {
        const pending = navigator.clipboard.writeText(raw);
        if (pending && typeof pending.then === "function") {
          pending.then(function () { done(true); }, function () { done(false); });
        } else {
          done(true);
        }
        return;
      } catch (error) {
        done(false);
        return;
      }
    }
    // Fallback for a page without the async clipboard API: copy the same raw
    // string through a temporary textarea (still no markup, no inline handler).
    try {
      const area = el("textarea", { class: "copy-fallback", readonly: "readonly" });
      area.value = raw;
      document.body.appendChild(area);
      if (typeof area.select === "function") area.select();
      const ok = typeof document.execCommand === "function" && document.execCommand("copy") === true;
      document.body.removeChild(area);
      done(ok);
    } catch (error) {
      done(false);
    }
  }

  function renderCaptureBlock(holder, side, attemptIndex, scope, copy, metaText) {
    const label = side === "request" ? "实际请求" : "实际返回";
    const captureState = captureStateOf(copy);
    const block = el("div", {
      class: "capture",
      "data-testid": "capture-block",
      "data-scope": scope,
      "data-capture": side,
      "data-attempt": String(attemptIndex),
      "data-format": "missing",
      "data-status": captureState.status,
    });
    const head = el("div", { class: "capture-head" });
    head.appendChild(el("h5", { text: label + " #" + String(attemptIndex) + (metaText ? " · " + metaText : "") }));
    head.appendChild(el("span", {
      class: "capture-status",
      "data-testid": "capture-status",
      "data-status": captureState.status,
      text: captureState.text,
    }));
    block.appendChild(head);
    if (captureState.status === "omitted" || captureState.status === "missing") {
      block.appendChild(el("p", { class: "muted", text: captureState.text }));
      holder.appendChild(block);
      return block;
    }
    const formatted = formatCaptureText(copy.text);
    block.setAttribute("data-format", formatted.kind);
    const raw = String(copy.text);
    const copyButton = el("button", {
      type: "button",
      "data-testid": "capture-copy",
      "data-scope": scope,
      "data-capture": side,
      "data-attempt": String(attemptIndex),
    }, ["复制原始捕获"]);
    const copyStatus = el("span", {
      class: "capture-copy-status",
      "data-testid": "capture-copy-status",
      "aria-live": "polite",
    });
    copyButton.addEventListener("click", function () {
      copyCaptureRaw(raw, copyStatus);
    });
    head.appendChild(copyButton);
    head.appendChild(copyStatus);
    block.appendChild(el("pre", {
      class: "copy-text",
      "data-testid": "capture-text",
      "data-format": formatted.kind,
      text: formatted.display,
    }));
    holder.appendChild(block);
    return block;
  }

  function renderCaptureAttempts(holder, detail, scope, side) {
    const attempts = detail && Array.isArray(detail.attempts) ? detail.attempts : [];
    holder.appendChild(el("h5", { text: side === "request" ? "实际请求（存储层捕获）" : "实际返回（存储层捕获）" }));
    if (!attempts.length) {
      holder.appendChild(el("p", { class: "muted", text: "未记录（没有记录任何 attempt）" }));
      return;
    }
    attempts.forEach(function (raw, index) {
      const attempt = raw && typeof raw === "object" ? raw : {};
      const indexText = isMissing(attempt.attempt_index) ? String(index) : String(attempt.attempt_index);
      const meta = [];
      if (side === "request") {
        if (!isMissing(attempt.method)) meta.push(String(attempt.method));
        if (!isMissing(attempt.url_path)) meta.push(String(attempt.url_path));
        if (!isMissing(attempt.model)) meta.push("model=" + String(attempt.model));
      } else {
        if (!isMissing(attempt.http_status)) meta.push("HTTP " + String(attempt.http_status));
        if (!isMissing(attempt.latency_ms)) meta.push(String(attempt.latency_ms) + " ms");
      }
      const copy = side === "request" ? attempt.request : attempt.response;
      renderCaptureBlock(holder, side, indexText, scope, copy, meta.join(" · "));
      if (side === "response") {
        const errors = [];
        if (!isMissing(attempt.error_class)) errors.push("error_class=" + String(attempt.error_class));
        if (!isMissing(attempt.error_detail)) errors.push(formatFree(attempt.error_detail));
        if (errors.length) {
          holder.appendChild(el("p", { class: "muted", text: "本次返回的错误记录：" + errors.join(" · ") }));
        }
        if (attempt.usage && typeof attempt.usage === "object") {
          holder.appendChild(el("p", { class: "muted", text: "usage：" + usageText(attempt.usage, { compact: true }) }));
        }
      }
    });
  }

  // -- material (input node): business sections only ------------------------

  function inputMaterialOf(detail) {
    let source = detail;
    if (typeof source === "string") {
      const parsedText = parseJson(source);
      source = parsedText.ok ? parsedText.value : null;
    }
    if (source && typeof source === "object" && !Array.isArray(source)) {
      const material = source.material;
      if (material && typeof material === "object" && !Array.isArray(material)) {
        const inner =
          material.state && typeof material.state === "object" && !Array.isArray(material.state)
            ? material.state
            : material;
        return { state: inner, note: null };
      }
      const book = source.book;
      if (book && typeof book === "object" && typeof book.text === "string") {
        const parsedBook = parseJson(book.text);
        const value = parsedBook.ok ? parsedBook.value : null;
        if (value && typeof value === "object" && !Array.isArray(value)) {
          const state = value.state;
          if (state && typeof state === "object" && !Array.isArray(state)) {
            return { state: state, note: "材料来自旧 book 快照的 state（原样读取，不补造）" };
          }
          return { state: null, note: "旧 book 快照里没有可读的 state：未记录（不猜正文）" };
        }
        return { state: null, note: "旧 book 快照不是可解析的 JSON：未记录（不猜正文）" };
      }
      if (source.state && typeof source.state === "object" && !Array.isArray(source.state)) {
        return { state: source.state, note: null };
      }
    }
    return { state: null, note: "未记录（未采集业务材料）" };
  }

  function renderMaterialValue(holder, label, value) {
    const block = el("div", { class: "material-block" });
    block.appendChild(el("h5", { text: label }));
    holder.appendChild(block);
    if (typeof value === "string") {
      block.appendChild(el("p", { class: "material-text", text: value === "" ? "（空）" : value }));
      return;
    }
    if (Array.isArray(value)) {
      if (!value.length) {
        block.appendChild(el("p", { class: "muted", text: "（空列表）" }));
        return;
      }
      const list = el("ul", { class: "plain" });
      value.forEach(function (item) {
        const itemHolder = el("li", { class: "material-item" });
        if (item && typeof item === "object" && !Array.isArray(item)) {
          Object.keys(item).forEach(function (key) {
            if (MATERIAL_HIDDEN_KEYS[key]) return;
            renderMaterialValue(itemHolder, MATERIAL_LABELS[key] || key, item[key]);
          });
        } else {
          itemHolder.appendChild(el("span", { text: isMissing(item) ? NOT_RECORDED : String(item) }));
        }
        list.appendChild(itemHolder);
      });
      block.appendChild(list);
      return;
    }
    if (value && typeof value === "object") {
      Object.keys(value).forEach(function (key) {
        if (MATERIAL_HIDDEN_KEYS[key]) return;
        renderMaterialValue(block, MATERIAL_LABELS[key] || key, value[key]);
      });
      return;
    }
    block.appendChild(el("p", { class: "material-text", text: missing(value) }));
  }

  function renderInputNode(holder, detail) {
    const material = inputMaterialOf(detail);
    holder.appendChild(el("h5", { text: "业务材料（本次判断的输入）" }));
    if (material.note) holder.appendChild(el("p", { class: "muted", text: material.note }));
    if (!material.state) {
      if (!material.note) holder.appendChild(el("p", { class: "muted", text: "未记录（未采集业务材料）" }));
      return;
    }
    const keys = Object.keys(material.state).filter(function (key) {
      return !MATERIAL_HIDDEN_KEYS[key];
    });
    if (!keys.length) {
      holder.appendChild(el("p", { class: "muted", text: "未记录（材料里没有业务字段）" }));
      return;
    }
    keys.forEach(function (key) {
      renderMaterialValue(holder, MATERIAL_LABELS[key] || key, material.state[key]);
    });
  }

  // -- decide node: policy verdict, never "API failure" for an HTTP 200 ------

  function policyDispositionLabel(disposition) {
    if (disposition === "adopted") return "已采纳（adopted）";
    if (disposition === "not-adopted" || disposition === "rejected") return "未采纳（" + disposition + "）";
    if (disposition === "escalated" || disposition === "human" || disposition === "human-review") {
      return "转人工兜底（" + disposition + "）";
    }
    if (disposition === "") return NOT_RECORDED;
    return disposition + "（未识别，按原值显示）";
  }

  function policyFallbackText(policy) {
    const disposition = policy && typeof policy.disposition === "string" ? policy.disposition : "";
    if (disposition === "escalated" || disposition === "human" || disposition === "human-review") {
      return "已转人工判断（见 disposition）";
    }
    if (policy && !isMissing(policy.reason)) {
      return "按策略不采用时交由发起角色/人工处理（reason=" + String(policy.reason) + "）";
    }
    return NOT_RECORDED;
  }

  function responseHttpStatus(nodes) {
    const response = (nodes || []).filter(function (node) {
      return node && node.id === "response" && node.detail && typeof node.detail === "object";
    })[0];
    const attempts = response && Array.isArray(response.detail.attempts) ? response.detail.attempts : [];
    for (let index = 0; index < attempts.length; index += 1) {
      const status = attempts[index] && attempts[index].http_status;
      if (typeof status === "number") return status;
    }
    return null;
  }

  function renderDecideNode(holder, detail, context) {
    const policy = detail.policy_result && typeof detail.policy_result === "object" ? detail.policy_result : null;
    const nodes = (context && Array.isArray(context.nodes) ? context.nodes : []);
    const model = nodes.filter(function (node) { return node && node.id === "model"; })[0];
    const modelDetail = model && model.detail && typeof model.detail === "object" ? model.detail : {};
    const httpStatus = responseHttpStatus(nodes);
    const apiConfidence =
      policy && typeof policy.confidence === "number"
        ? policy.confidence
        : typeof modelDetail.confidence === "number"
          ? modelDetail.confidence
          : null;
    if (policy) {
      holder.appendChild(line("策略判定", policyDispositionLabel(
        typeof policy.disposition === "string" ? policy.disposition : ""
      )));
      holder.appendChild(line("模型选择", formatFree(policy.selection)));
      holder.appendChild(line("API confidence", isMissing(policy.confidence) ? NOT_RECORDED : String(policy.confidence)));
      holder.appendChild(line(
        "本次阈值",
        typeof policy.min_confidence === "number"
          ? String(policy.min_confidence)
          : "未记录（本记录未持久化本次生效阈值，不按当前配置补造）"
      ));
      if (!isMissing(policy.reason)) holder.appendChild(line("判定依据", String(policy.reason)));
    } else {
      holder.appendChild(line("策略判定：未记录", "本记录未持久化本次阈值/处置，不按当前配置推断"));
      holder.appendChild(line("API confidence", isMissing(apiConfidence) ? NOT_RECORDED : String(apiConfidence)));
      if (!isMissing(modelDetail.confidence_source)) {
        holder.appendChild(line("confidence_source", String(modelDetail.confidence_source)));
      }
    }
    if (!isMissing(detail.status)) holder.appendChild(line("decide 状态", String(detail.status)));
    if (detail.available === false) holder.appendChild(line("available", "false（决策接口未返回可用答案）"));
    if (detail.zero_call === true) {
      holder.appendChild(line("zero_call", "true（客户端零调用，不是一次真实 HTTP 请求）"));
    }
    if (policy) {
      const notAdopted =
        policy.disposition === "not-adopted" ||
        policy.disposition === "rejected" ||
        policy.disposition === "escalated" ||
        policy.disposition === "human";
      if (notAdopted) {
        const parts = ["未采纳：模型选择没有满足本次策略，按策略不采用。"];
        if (httpStatus === 200) {
          parts.push("决策接口已正常返回（HTTP 200）：这是策略判定，不代表接口调用失败。");
        } else {
          parts.push("这是策略判定，不代表接口调用失败。");
        }
        parts.push("人工兜底：" + policyFallbackText(policy));
        holder.appendChild(el("p", { class: "notes", "data-testid": "decide-policy-note", text: parts.join(" ") }));
      }
      if (isMissing(policy.min_confidence)) {
        holder.appendChild(el("p", {
          class: "muted",
          "data-testid": "decide-threshold-note",
          text: "本次生效阈值未记录：旧记录不以当前配置补猜。",
        }));
      }
    } else {
      holder.appendChild(el("p", {
        class: "muted",
        "data-testid": "decide-policy-missing",
        text: "本记录没有 policy_result（本次阈值/处置/未采纳原因未记录），不补造阈值，也不把 HTTP 200 当作接口失败。",
      }));
    }
    if (!isMissing(detail.reason)) holder.appendChild(line("decide reason", formatFree(detail.reason)));
    if (!isMissing(detail.escalated_reason)) {
      holder.appendChild(line("escalated_reason（升级人判断的原因）", formatFree(detail.escalated_reason)));
    }
  }

  // -- receipt / action / errors (shared by the node detail and the log) -----

  function renderReceiptFacts(holder, detail) {
    const consumed = detail.consumed && typeof detail.consumed === "object" ? detail.consumed : null;
    if (consumed) {
      holder.appendChild(line("接收时间", missing(consumed.ts)));
      holder.appendChild(line("收到的答案", formatFree(consumed.answer)));
      holder.appendChild(line("answer_source", missing(consumed.answer_source)));
      holder.appendChild(line("actor_kind", missing(consumed.actor_kind)));
    } else {
      holder.appendChild(line("接收签收", "未记录（没有收到/签收的事实）"));
    }
    const signoff = detail.signoff && typeof detail.signoff === "object" ? detail.signoff : null;
    if (signoff) {
      holder.appendChild(line(
        "签收文件",
        signoff.file_verified === true ? "已验证（文件即完成依据）" : "未验证：" + missing(signoff.file_reason)
      ));
    }
  }

  function renderActionFacts(holder, detail) {
    const executed = Array.isArray(detail.executed) ? detail.executed : [];
    if (!executed.length) {
      holder.appendChild(line("已执行行动", "未记录"));
    }
    executed.forEach(function (row) {
      holder.appendChild(line(
        "已执行行动（" + missing(row.action) + "）",
        formatFree(row.result) + " · 时间：" + missing(row.ts) + " · answer_source：" + missing(row.answer_source)
      ));
    });
    const settled = detail.settled && typeof detail.settled === "object" ? detail.settled : null;
    holder.appendChild(line(
      "处理结果",
      settled
        ? missing(settled.outcome) + " · 原因：" + formatFree(settled.reason) + " · 时间：" + missing(settled.ts)
        : "未记录"
    ));
  }

  function feedbackErrors(record, byId) {
    const items = [];
    const calls = Array.isArray(record.calls) ? record.calls : [];
    calls.forEach(function (call) {
      const attempts = call && Array.isArray(call.attempts) ? call.attempts : [];
      attempts.forEach(function (attempt) {
        if (!isMissing(attempt.error_class) || !isMissing(attempt.error_detail)) {
          items.push(
            "call " + missing(call.call_id) + " · attempt " + missing(attempt.attempt_index) +
              " · " + missing(attempt.error_class) + " · " + formatFree(attempt.error_detail)
          );
        }
      });
    });
    [byId.receipt, byId.action].forEach(function (node) {
      const errors = node && node.detail && Array.isArray(node.detail.errors) ? node.detail.errors : [];
      errors.forEach(function (row) {
        items.push(
          "反馈写入失败 · stage=" + missing(row.stage) + " · error_class=" + missing(row.error_class) +
            " · " + formatFree(row.detail) + " · 时间：" + missing(row.ts)
        );
      });
    });
    const decide = byId.decide && byId.decide.detail && typeof byId.decide.detail === "object" ? byId.decide.detail : null;
    if (decide && !isMissing(decide.escalated_reason)) {
      items.push("decide 升级人判断 · " + formatFree(decide.escalated_reason));
    }
    return items;
  }

  function renderReceiptAndAction(holder, record, byId) {
    let rendered = 0;
    if (byId.receipt && byId.receipt.detail && typeof byId.receipt.detail === "object") {
      holder.appendChild(el("h4", { text: "接收签收" }));
      renderReceiptFacts(holder, byId.receipt.detail);
      rendered += 1;
    }
    if (byId.action && byId.action.detail && typeof byId.action.detail === "object") {
      holder.appendChild(el("h4", { text: "行动与处理" }));
      renderActionFacts(holder, byId.action.detail);
      rendered += 1;
    }
    if (rendered) return;
    // Legacy records have no v2 node bodies: the folded archive/stage facts are
    // the receipt, and only those facts are shown (never the whole stage table).
    const stages = record.stages && typeof record.stages === "object" ? record.stages : {};
    ["consumed", "responded", "executed", "settled"].forEach(function (name) {
      const fact = stages[name];
      if (!fact || typeof fact !== "object") return;
      // Only a recorded fact is a result: an empty stage row stays silent.
      if (isMissing(fact.result) && isMissing(fact.detail) && isMissing(fact.ts)) return;
      holder.appendChild(line(
        STAGE_LABELS[name] + "（" + name + " · " + stateLabel(fact.state) + "）",
        formatFree(fact.result) + " · 详情：" + formatFree(fact.detail) + " · 时间：" + missing(fact.ts)
      ));
      rendered += 1;
    });
    const archive = record.archive && typeof record.archive === "object" ? record.archive : null;
    if (
      archive &&
      (!isMissing(archive.answer) || !isMissing(archive.actual_action) || !isMissing(archive.outcome))
    ) {
      holder.appendChild(line("吸收的应答", formatFree(archive.answer)));
      holder.appendChild(line("实际动作", formatFree(archive.actual_action)));
      holder.appendChild(line("结果", missing(archive.outcome)));
      rendered += 1;
    }
    if (!rendered) holder.appendChild(el("p", { class: "muted", text: "未记录（没有接收/行动反馈）" }));
  }

  function logSection(title, name, build) {
    const section = el("section", {
      class: "detail-section",
      "data-testid": "log-section",
      "data-section": name,
    });
    section.appendChild(el("h3", { text: title }));
    build(section);
    return section;
  }

  function renderLogDetail(record) {
    // AC-015: only time + associated task, initiator role, the actual
    // request/response, the receipt/action result and errors. Source/stage/
    // book/version/hash keep their underlying records but get no default column.
    const body = document.getElementById("detail-body");
    if (!body) return;
    body.replaceChildren();
    const workbench = workbenchOf(record);
    const nodes = workbench && Array.isArray(workbench.nodes) ? workbench.nodes : [];
    const byId = Object.create(null);
    nodes.forEach(function (node) {
      if (node && typeof node.id === "string") byId[node.id] = node;
    });

    body.appendChild(logSection("概要", "summary", function (section) {
      section.appendChild(definitionList([
        ["时间", missing(record.ts)],
        ["key", missing(record.key)],
        ["task", missing(record.task_key)],
        ["发起角色", workbench ? missing(workbench.initiator_role) : NOT_RECORDED],
        ["DP", missing(record.dp)],
        ["处理状态", processingLabel(record)],
      ]));
    }));

    body.appendChild(logSection("实际请求与返回", "captures", function (section) {
      const calls = Array.isArray(record.calls) ? record.calls : [];
      let rendered = 0;
      calls.forEach(function (call) {
        const attempts = call && Array.isArray(call.attempts) ? call.attempts : [];
        attempts.forEach(function (attempt) {
          rendered += 1;
          const index = isMissing(attempt.attempt_index) ? String(rendered - 1) : String(attempt.attempt_index);
          const requestMeta = [];
          if (!isMissing(attempt.method)) requestMeta.push(String(attempt.method));
          if (!isMissing(attempt.url_path)) requestMeta.push(String(attempt.url_path));
          const responseMeta = [];
          if (!isMissing(attempt.http_status)) responseMeta.push("HTTP " + String(attempt.http_status));
          if (!isMissing(attempt.latency_ms)) responseMeta.push(String(attempt.latency_ms) + " ms");
          renderCaptureBlock(section, "request", index, "log", attempt.request, requestMeta.join(" · "));
          renderCaptureBlock(section, "response", index, "log", attempt.response, responseMeta.join(" · "));
        });
      });
      if (!rendered) {
        section.appendChild(el("p", { class: "muted", text: "未记录（没有采集到实际请求/返回）" }));
      }
    }));

    body.appendChild(logSection("接收与处理结果", "receipt", function (section) {
      renderReceiptAndAction(section, record, byId);
    }));

    body.appendChild(logSection("错误", "errors", function (section) {
      const items = feedbackErrors(record, byId);
      if (!items.length) {
        section.appendChild(el("p", { class: "muted", text: "（无记录的错误）" }));
        return;
      }
      items.forEach(function (text) {
        section.appendChild(el("p", { class: "error", text: text }));
      });
    }));
    setHidden("detail-panel", false);
  }

  // -- HTTP ----------------------------------------------------------------

  function requestError(payload, status) {
    const error = payload && payload.error && typeof payload.error === "object" ? payload.error : {};
    const code = error.code || "http-" + String(status);
    const message = error.message || "请求失败";
    const issues = Array.isArray(error.issues) ? error.issues : [];
    const problem = new Error(code + ": " + message + (issues.length ? "（" + issues.join("; ") + "）" : ""));
    problem.code = code;
    problem.status = status;
    problem.data = payload && payload.data && typeof payload.data === "object" ? payload.data : null;
    return problem;
  }

  async function readEnvelope(response) {
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      payload = null;
    }
    if (!response.ok || !payload || payload.ok !== true) {
      throw requestError(payload, response.status);
    }
    return payload;
  }

  async function getJson(path) {
    const headers = {};
    if (state.token) headers[TOKEN_HEADER] = state.token;
    const response = await fetch(path, {
      method: "GET",
      headers: headers,
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
    });
    return readEnvelope(response);
  }

  async function postJson(path, body) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
    });
    return readEnvelope(response);
  }

  async function postJsonPage(path, body) {
    // DP test routes are page-role routes: the in-memory token is required.
    // It stays in this closure (never a URL, never web storage).
    const headers = { "Content-Type": "application/json" };
    if (state.token) headers[TOKEN_HEADER] = state.token;
    const response = await fetch(path, {
      method: "POST",
      headers: headers,
      body: JSON.stringify(body),
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
    });
    return readEnvelope(response);
  }

  function showError(error) {
    const code = error && error.code ? error.code : "error";
    const message = error && error.message ? error.message : String(error);
    setText("error-banner", code + " · " + message);
  }

  function clearError() {
    setText("error-banner", "");
  }

  function queryFor(offset) {
    const params = new URLSearchParams();
    const filters = state.filters;
    if (filters.key) params.set("key", filters.key);
    if (filters.dp) params.set("dp", filters.dp);
    if (filters.source) params.set("source", filters.source);
    if (filters.status) params.set("status", filters.status);
    params.set("scope", filters.scope || SCOPE_DEFAULT);
    params.set("limit", String(state.limit));
    params.set("offset", String(offset));
    return "?" + params.toString();
  }

  async function loadHistory(offset) {
    if (!state.token) return;
    clearError();
    setText("history-summary", "正在读取历史…");
    try {
      const payload = await getJson("/api/history" + queryFor(offset));
      const data = payload.data && typeof payload.data === "object" ? payload.data : {};
      data.total = typeof data.total === "number" ? data.total : null;
      data.limit = typeof data.limit === "number" ? data.limit : state.limit;
      data.offset = typeof data.offset === "number" ? data.offset : offset;
      data.has_more = data.has_more === true;
      state.limit = data.limit;
      state.offset = data.offset;
      state.total = data.total;
      state.hasMore = data.has_more;
      state.recordCount = Array.isArray(data.records) ? data.records.length : 0;
      state.lastHistory = data;
      renderFiltersNotes(data);
      renderHistory(data);
    } catch (error) {
      showError(error);
      setText("history-summary", "历史读取失败，未显示任何伪造数据。");
    }
  }

  // -- record dialog: single-decision DAG vs technical log -------------------

  function setDagTabAvailable(available) {
    const dagTab = document.getElementById("record-dialog-tab-dag");
    if (!dagTab) return;
    if (available) {
      dagTab.removeAttribute("disabled");
    } else {
      dagTab.setAttribute("disabled", "");
    }
    setHidden("record-dialog-legacy-note", available);
  }

  function selectDialogTab(name) {
    const dagTab = document.getElementById("record-dialog-tab-dag");
    const dagDisabled = Boolean(dagTab && dagTab.hasAttribute("disabled"));
    const showDag = name === "dag" && !dagDisabled;
    if (dagTab) dagTab.setAttribute("aria-selected", showDag ? "true" : "false");
    const logTab = document.getElementById("record-dialog-tab-log");
    if (logTab) logTab.setAttribute("aria-selected", showDag ? "false" : "true");
    setHidden("record-dialog-dag-panel", !showDag);
    setHidden("record-dialog-log-panel", showDag);
  }

  // -- the ten-node directed graph (shared by history and the test page) ----

  function dagPositions(count) {
    const positions = [];
    for (let index = 0; index < count; index += 1) {
      const row = Math.floor(index / DAG_COLUMNS);
      const withinRow = index % DAG_COLUMNS;
      const column = row % 2 === 0 ? withinRow : DAG_COLUMNS - 1 - withinRow;
      positions.push({
        row: row,
        left: DAG_MARGIN + column * (DAG_NODE_WIDTH + DAG_GAP_X),
        top: DAG_MARGIN + row * (DAG_NODE_HEIGHT + DAG_GAP_Y),
      });
    }
    return positions;
  }

  function dagGraphSize(count) {
    const positions = dagPositions(count);
    let width = DAG_MARGIN;
    let height = DAG_MARGIN;
    positions.forEach(function (position) {
      width = Math.max(width, position.left + DAG_NODE_WIDTH + DAG_MARGIN);
      height = Math.max(height, position.top + DAG_NODE_HEIGHT + DAG_MARGIN);
    });
    return { width: width, height: height };
  }

  function dagEdgePoints(from, to) {
    if (from.row === to.row) {
      const forward = to.left > from.left;
      return {
        x1: forward ? from.left + DAG_NODE_WIDTH : from.left,
        y1: from.top + DAG_NODE_HEIGHT / 2,
        x2: forward ? to.left : to.left + DAG_NODE_WIDTH,
        y2: to.top + DAG_NODE_HEIGHT / 2,
      };
    }
    return {
      x1: from.left + DAG_NODE_WIDTH / 2,
      y1: from.row < to.row ? from.top + DAG_NODE_HEIGHT : from.top,
      x2: to.left + DAG_NODE_WIDTH / 2,
      y2: to.row < from.row ? to.top + DAG_NODE_HEIGHT : to.top,
    };
  }

  function svgNode(tag, attrs) {
    const node =
      typeof document.createElementNS === "function"
        ? document.createElementNS(SVG_NS, tag)
        : document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (name) {
        node.setAttribute(name, String(attrs[name]));
      });
    }
    return node;
  }

  function renderDagGraph(holder, nodes, testid, detailId) {
    if (!holder) return 0;
    holder.replaceChildren();
    const list = Array.isArray(nodes) ? nodes : [];
    if (!list.length) {
      holder.removeAttribute("data-node-count");
      return 0;
    }
    const positions = dagPositions(list.length);
    const size = dagGraphSize(list.length);
    holder.setAttribute("data-node-count", String(list.length));

    const svg = svgNode("svg", {
      class: "dag-edges",
      "data-testid": testid + "-edges",
      width: String(size.width),
      height: String(size.height),
      viewBox: "0 0 " + String(size.width) + " " + String(size.height),
      "aria-hidden": "true",
      focusable: "false",
      role: "presentation",
    });
    const defs = svgNode("defs", null);
    const marker = svgNode("marker", {
      id: testid + "-arrow",
      viewBox: "0 0 10 10",
      refX: "9",
      refY: "5",
      markerWidth: "6",
      markerHeight: "6",
      orient: "auto-start-reverse",
    });
    marker.appendChild(svgNode("path", { d: "M 0 0 L 10 5 L 0 10 z" }));
    defs.appendChild(marker);
    svg.appendChild(defs);
    list.forEach(function (node, index) {
      if (index === 0) return;
      const previous = list[index - 1] && typeof list[index - 1] === "object" ? list[index - 1] : {};
      const current = node && typeof node === "object" ? node : {};
      const points = dagEdgePoints(positions[index - 1], positions[index]);
      svg.appendChild(svgNode("line", {
        class: "dag-edge",
        "data-testid": testid + "-edge",
        "data-from": isMissing(previous.id) ? "" : String(previous.id),
        "data-to": isMissing(current.id) ? "" : String(current.id),
        "data-order": String(index - 1),
        "marker-end": "url(#" + testid + "-arrow)",
        "aria-hidden": "true",
        x1: String(points.x1),
        y1: String(points.y1),
        x2: String(points.x2),
        y2: String(points.y2),
      }));
    });
    holder.appendChild(svg);

    const buttons = [];
    list.forEach(function (raw, index) {
      const node = raw && typeof raw === "object" ? raw : {};
      const status = nodeStatusOf(node);
      const step = ("0" + String(index + 1)).slice(-2);
      const button = el("button", {
        type: "button",
        class: "dag-node dag-state-" + status + " dag-pos-" + String(index),
        "data-testid": testid,
        "data-node-id": isMissing(node.id) ? "" : String(node.id),
        "data-node-state": status,
        "data-step": step,
        "data-pos": "dag-pos-" + String(index),
        "aria-pressed": "false",
      });
      button.appendChild(el("span", { class: "node-step", text: "步骤 " + step }));
      button.appendChild(el("span", { class: "node-label", text: missing(node.label) }));
      button.appendChild(el("span", { class: "node-state", text: nodeStateLabel(status) }));
      buttons.push(button);
      holder.appendChild(button);
    });
    buttons.forEach(function (button, index) {
      const node = list[index] && typeof list[index] === "object" ? list[index] : {};
      button.addEventListener("click", function () {
        buttons.forEach(function (other) {
          other.setAttribute("aria-pressed", other === button ? "true" : "false");
        });
        renderNodeDetail(detailId, node, { nodes: list });
      });
      button.addEventListener("keydown", function (event) {
        const key = event && event.key;
        if (key !== "ArrowRight" && key !== "ArrowLeft") return;
        const target = buttons[key === "ArrowRight" ? index + 1 : index - 1];
        if (!target) return;
        if (typeof event.preventDefault === "function") event.preventDefault();
        if (typeof target.focus === "function") target.focus();
        target.setAttribute("aria-pressed", "true");
        button.setAttribute("aria-pressed", "false");
        renderNodeDetail(detailId, list[key === "ArrowRight" ? index + 1 : index - 1], { nodes: list });
      });
    });
    return list.length;
  }

  function renderNodeDetail(targetId, node, context) {
    const holder = document.getElementById(targetId);
    if (!holder) return;
    const source = node && typeof node === "object" ? node : {};
    holder.replaceChildren();
    holder.setAttribute("data-node-id", isMissing(source.id) ? "" : String(source.id));
    holder.appendChild(el("h4", {
      text: "节点 " + missing(source.id) + " · " + nodeStateLabel(nodeStatusOf(source)),
    }));
    const detail = source.detail;
    if (source.id === "input") {
      renderInputNode(holder, detail);
      return;
    }
    if (isMissing(detail)) {
      holder.appendChild(el("p", {
        class: "muted",
        text: "节点详情：未记录（只有单条 detail 投影才带节点详情）。",
      }));
      return;
    }
    if (typeof detail !== "object" || Array.isArray(detail)) {
      holder.appendChild(el("pre", { class: "copy-text", "data-testid": "dag-node-detail-text", text: String(detail) }));
    } else if (source.id === "decide") {
      renderDecideNode(holder, detail, context || {});
    } else if (source.id === "request") {
      renderCaptureAttempts(holder, detail, "dag", "request");
    } else if (source.id === "response") {
      renderCaptureAttempts(holder, detail, "dag", "response");
    } else if (source.id === "receipt") {
      renderReceiptFacts(holder, detail);
    } else if (source.id === "action") {
      renderActionFacts(holder, detail);
    } else {
      const rows = [];
      const labels = {
        key: [["key", "key"], ["task_key", "task"]],
        role: [["initiator_role", "发起角色"], ["actor_kind", "actor_kind"]],
        dp: [["dp_id", "DP"], ["decision_id", "decision_id"]],
        model: [
          ["transport", "传输"],
          ["model", "模型"],
          ["answer_source", "answer_source"],
          ["confidence_source", "confidence_source"],
          ["confidence", "API confidence"],
        ],
      }[source.id] || [];
      labels.forEach(function (pair) {
        if (!Object.prototype.hasOwnProperty.call(detail, pair[0])) return;
        const value = detail[pair[0]];
        rows.push([pair[1], isMissing(value) ? NOT_RECORDED : typeof value === "object" ? formatFree(value) : String(value)]);
      });
      if (!rows.length) {
        const keys = Object.keys(detail).filter(function (key) { return key !== "basis"; });
        keys.forEach(function (key) {
          const value = detail[key];
          rows.push([key, isMissing(value) ? NOT_RECORDED : typeof value === "object" ? formatFree(value) : String(value)]);
        });
      }
      holder.appendChild(definitionList(rows));
    }
    const basis = Array.isArray(source.basis) ? source.basis : [];
    holder.appendChild(el("p", {
      class: "basis",
      text: "依据：" + (basis.length ? basis.join("; ") : NOT_RECORDED),
    }));
  }

  function renderDag(workbench, isDag) {
    const nodes = isDag && workbench && Array.isArray(workbench.nodes) ? workbench.nodes : [];
    const holder = document.getElementById("dag-graph");
    const rendered = renderDagGraph(holder, nodes, "dag-node", "dag-node-detail");
    setHidden("dag-graph-note", rendered === 0);
    if (!isDag) {
      setText("record-dialog-dag-summary", "旧数据无状态：不展开 DAG。");
    } else if (rendered === 10) {
      setText(
        "record-dialog-dag-summary",
        "节点 10/10 · 顺序与状态来自后端 workbench 投影；未记录节点不补造。箭头是既定处理顺序，不代表该步已经发生。"
      );
    } else {
      setText(
        "record-dialog-dag-summary",
        "节点 " + String(rendered) + "/10 · 投影不完整：只渲染后端给出的节点，缺失节点不补造。"
      );
    }
    const detail = document.getElementById("dag-node-detail");
    if (detail) {
      detail.replaceChildren();
      detail.removeAttribute("data-node-id");
    }
  }

  async function openRecord(opaque, mode) {
    if (!state.token) return;
    if (typeof opaque !== "string" || !opaque) {
      showError(new Error("missing-opaque-id: 详情只接受记录句柄"));
      return;
    }
    clearError();
    try {
      const payload = await getJson("/api/history/" + encodeURIComponent(opaque));
      const record = payload.data && typeof payload.data === "object" ? payload.data : {};
      state.lastDetail = record;
      const workbench = workbenchOf(record);
      const isDag = dagAvailable(record);
      setHidden("record-dialog", false);
      setText("record-dialog-title", "决策详情 · " + missing(record.record_kind) + " · " + opaque);
      setText(
        "record-dialog-meta",
        "处理状态：" + processingLabel(record) +
          " · 发起角色：" + (workbench ? missing(workbench.initiator_role) : NOT_RECORDED) +
          " · DP：" + missing(workbench && workbench.dp_id ? workbench.dp_id : record.dp)
      );
      setDagTabAvailable(isDag);
      renderDag(workbench, isDag);
      setText("detail-title", "日志详情 · " + missing(record.record_kind) + " · " + opaque);
      renderLogDetail(record);
      selectDialogTab(isDag && mode !== "log" ? "dag" : "log");
    } catch (error) {
      showError(error);
    }
  }

  function closeDetail() {
    state.lastDetail = null;
    const body = document.getElementById("detail-body");
    if (body) body.replaceChildren();
    const dag = document.getElementById("dag-graph");
    if (dag) dag.replaceChildren();
    const nodeDetail = document.getElementById("dag-node-detail");
    if (nodeDetail) nodeDetail.replaceChildren();
    setHidden("record-dialog", true);
  }

  // -- DP test playground ---------------------------------------------------

  function pg() {
    return state.playground;
  }

  function setPgStatus(text) {
    setText("playground-status", text);
  }

  function pgOut(id) {
    const node = document.getElementById(id);
    return node || null;
  }

  function pgClear(id) {
    const node = pgOut(id);
    if (node) node.replaceChildren();
  }

  function pgAppend(id, node) {
    const holder = pgOut(id);
    if (holder && node) holder.appendChild(node);
  }

  function pgSection(title, children, testid) {
    const section = el("section", testid ? { class: "detail-section", "data-testid": testid } : { class: "detail-section" });
    section.appendChild(el("h3", { text: title }));
    (children || []).forEach(function (child) {
      if (child) section.appendChild(child);
    });
    return section;
  }

  function flagsText(names) {
    if (!names || !names.length) return "（无）";
    return names.map(function (name) { return String(name); }).join(", ");
  }

  function answerEntries(answer) {
    if (!answer || typeof answer !== "object") return [];
    return Object.keys(answer).map(function (qid) {
      const spec = answer[qid] && typeof answer[qid] === "object" ? answer[qid] : {};
      return { qid: qid, spec: spec };
    });
  }

  function renderAnswerBlock(answer, options) {
    const opts = options || {};
    const entries = answerEntries(answer);
    if (!entries.length) {
      const missingLine = el("p", { class: "muted", text: opts.missingText || "当次答案：" + NOT_RECORDED });
      return missingLine;
    }
    const table = el("table", { "data-testid": "pg-answer" });
    const head = el("tr");
    ["question", "value", "confidence", "probabilities / legend"].forEach(function (title) {
      head.appendChild(el("th", { scope: "col", text: title }));
    });
    table.appendChild(el("thead", null, [head]));
    const body = el("tbody");
    entries.forEach(function (entry) {
      const spec = entry.spec;
      const extra = [];
      if (spec.probabilities) extra.push("probabilities=" + formatFree(spec.probabilities));
      if (spec.legend) extra.push("legend=" + formatFree(spec.legend));
      body.appendChild(el("tr", { "data-testid": "pg-answer-row", "data-question": entry.qid }, [
        el("td", { text: entry.qid }),
        el("td", { text: formatFree(spec.value) }),
        el("td", { text: missing(spec.confidence) }),
        el("td", { text: extra.length ? extra.join(" · ") : NOT_RECORDED }),
      ]));
    });
    table.appendChild(body);
    return table;
  }

  function outcomeBlock(outcome) {
    if (!outcome || typeof outcome !== "object") {
      return el("p", { class: "muted", text: "采纳判定/动作预览：" + NOT_RECORDED });
    }
    const preview = outcome.preview && typeof outcome.preview === "object" ? outcome.preview : null;
    const response = outcome.response && typeof outcome.response === "object" ? outcome.response : null;
    return definitionList([
      ["status（采纳判定）", missing(outcome.status)],
      ["escalated_reason", missing(outcome.escalated_reason)],
      ["mode", missing(outcome.mode)],
      ["confidence_source", missing(outcome.confidence_source)],
      ["latency_ms", missing(outcome.latency_ms)],
      ["truncated", flagsText(outcome.truncated)],
      ["archive_state", missing(outcome.archive_state)],
      ["capture_channel", missing(outcome.capture_channel)],
      ["transport_reason", missing(outcome.transport_reason)],
      ["detail", formatFree(outcome.detail)],
      ["动作预览（preview）", preview ? formatFree(preview) : NOT_RECORDED],
      ["响应元数据（response）", response ? formatFree(response) : NOT_RECORDED],
    ]);
  }

  function renderSubmitResult(data, httpStatus, error) {
    pgClear("pg-submit-out");
    const record = data && typeof data === "object" ? data : {};
    const stateText = missing(record.state);
    const recorded = record.record_status === "recorded";
    const succeeded = record.state === "succeeded" && recorded && record.duplicate !== true;
    const headline = succeeded
      ? "HTTP " + String(httpStatus) + " · state=succeeded · 已记录（真实模型调用成功）"
      : record.duplicate === true
        ? "HTTP " + String(httpStatus) + " · state=" + stateText + " · 重复提交（同 submit_id）：未新增调用，不是一次新的成功"
        : "HTTP " + String(httpStatus) + " · state=" + stateText + " · 未成功（HTTP 200 不等于成功，以 state/record_status 为准）";
    const head = el("p", { class: succeeded ? "status ok" : "status warn", "data-testid": "pg-submit-headline", text: headline });
    pgAppend("pg-submit-out", head);
    pgAppend("pg-submit-out", definitionList([
      ["submission_id", missing(record.submission_id)],
      ["dp", missing(record.dp)],
      ["state", stateText],
      ["accepted", flag(record.accepted)],
      ["duplicate", flag(record.duplicate)],
      ["busy", flag(record.busy)],
      ["observe_only", flag(record.observe_only)],
      ["retry_of", missing(record.retry_of)],
      ["decision_id", missing(record.decision_id)],
      ["decision_ran", flag(record.decision_ran)],
      ["call_id", missing(record.call_id)],
      ["zero_call", flag(record.zero_call)],
      ["http_attempts（实际 HTTP 次数）", missing(record.http_attempts)],
      ["book_ref（决策本快照）", missing(record.book_ref)],
      ["state_digest", missing(record.state_digest)],
      ["capture_status", missing(record.capture_status)],
      ["record_status", missing(record.record_status)],
      ["started_at", missing(record.started_at)],
      ["finished_at", missing(record.finished_at)],
      ["answer_persisted（轮询可读回）", flag(record.answer_persisted)],
      ["projection_status", missing(record.projection_status)],
      ["projection_sha256", missing(record.projection_sha256)],
      ["projection_redactions", missing(record.projection_redactions)],
    ]));
    const issues = Array.isArray(record.issues) ? record.issues : [];
    const issueList = el("ul", { class: "plain", "data-testid": "pg-issues" });
    if (!issues.length) issueList.appendChild(el("li", { text: "拒绝/问题项：无" }));
    issues.forEach(function (issue) {
      if (issue && typeof issue === "object") {
        issueList.appendChild(el("li", { text: missing(issue.code) + " · " + missing(issue.path) + " · " + formatFree(issue.detail) }));
      } else {
        issueList.appendChild(el("li", { text: String(issue) }));
      }
    });
    pgAppend("pg-submit-out", pgSection("拒绝/问题项", [issueList]));
    pgAppend("pg-submit-out", pgSection("采纳判定与动作预览", [outcomeBlock(record.outcome)]));
    const liveAnswer = record.answer && typeof record.answer === "object" ? record.answer : (record.outcome && record.outcome.answer);
    pgAppend("pg-submit-out", pgSection("当次答案（安全展示）", [
      renderAnswerBlock(liveAnswer, { missingText: "当次答案：" + NOT_RECORDED }),
      el("p", { class: "muted", text: "持久化投影只保存经当次冻结脱敏器处理后的安全结果（无原始请求/返回、无凭证）；实际请求/返回正文只存在于 wire/evidence 存储层，可在下方“详情”按 call id 读取。" }),
      el("p", { class: "muted", text: "脱敏命中：" + missing(record.projection_redactions) + " · 截断字段：" + flagsText(record.projection_truncated_fields) }),
    ]));
    if (record.message) pgAppend("pg-submit-out", el("p", { class: "warn", text: String(record.message) }));
    if (error) pgAppend("pg-submit-out", el("p", { class: "error", text: String(error.code || "error") + ": " + String(error.message || error) }));
  }

  function renderBusy(data, error) {
    pgClear("pg-submit-out");
    const record = data && typeof data === "object" ? data : {};
    pgAppend("pg-submit-out", el("p", {
      class: "error",
      "data-testid": "pg-busy",
      text: "HTTP 409 · busy：已有一次提交在运行；本次未排队、未发起模型调用（zero_call=true）。",
    }));
    pgAppend("pg-submit-out", definitionList([
      ["submission_id", missing(record.submission_id)],
      ["dp", missing(record.dp)],
      ["state", missing(record.state)],
      ["accepted", flag(record.accepted)],
      ["busy", flag(record.busy)],
      ["zero_call", flag(record.zero_call)],
      ["record_status", missing(record.record_status)],
      ["message（provider）", formatFree(record.message)],
    ]));
    if (error && error.message) pgAppend("pg-submit-out", el("p", { class: "muted", text: "服务端说明：" + String(error.message) }));
  }

  function renderSubmitFailure(error) {
    pgClear("pg-submit-out");
    pgAppend("pg-submit-out", el("p", {
      class: "error",
      "data-testid": "pg-submit-error",
      text: "提交失败（未伪造成功）：" + String(error && error.code ? error.code : "error") + " · " + String(error && error.message ? error.message : error),
    }));
  }

  function renderValidateResult(data) {
    pgClear("pg-validate-out");
    const report = data && typeof data === "object" ? data : {};
    const ok = report.ok === true;
    pgAppend("pg-validate-out", el("p", {
      class: ok ? "status ok" : "status warn",
      "data-testid": "pg-validate-headline",
      text: "校验结果：" + (ok ? "通过（可提交；本次没有发模型请求）" : "未通过（拒绝项如下；未发模型请求）"),
    }));
    pgAppend("pg-validate-out", definitionList([
      ["dp", missing(report.dp)],
      ["state_bytes / max_state_bytes", missing(report.state_bytes) + " / " + missing(report.max_state_bytes)],
      ["state_digest", missing(report.state_digest)],
      ["context_slots（校验过）", flagsText(report.context_slots)],
      ["context_sent", flag(report.context_sent) + "（context 原文不发送，只校验槽位）"],
      ["observe_only", flag(report.observe_only)],
      ["传输状态", (report.transport && report.transport.state ? String(report.transport.state) : NOT_RECORDED) + " · " + (report.transport && report.transport.detail ? String(report.transport.detail) : NOT_RECORDED)],
    ]));
    if (report.context_note) pgAppend("pg-validate-out", el("p", { class: "muted", text: String(report.context_note) }));
    const preview = report.request_preview && typeof report.request_preview === "object" ? report.request_preview : null;
    const previewSection = pgSection("请求预览（server 实际 preview；0 模型调用）", []);
    previewSection.setAttribute("data-testid", "pg-request-preview");
    if (!preview) {
      previewSection.appendChild(el("p", {
        class: "muted",
        text: "请求预览：未记录（后端未返回 request_preview）。",
      }));
    } else {
      previewSection.appendChild(el("p", {
        class: "muted",
        text: "以下 model/state/questions 是服务端返回的实际 preview 值（与本次发送同源），不是页面另造的副本。",
      }));
      [
        ["model", "pg-preview-model"],
        ["state", "pg-preview-state"],
        ["questions", "pg-preview-questions"],
      ].forEach(function (pair) {
        const value = preview[pair[0]];
        previewSection.appendChild(el("h4", { text: pair[0] }));
        previewSection.appendChild(el("pre", {
          class: "copy-text",
          "data-testid": pair[1],
          text: isMissing(value) ? NOT_RECORDED : JSON.stringify(value, null, 2),
        }));
      });
    }
    pgAppend("pg-validate-out", previewSection);
    const issues = Array.isArray(report.issues) ? report.issues : [];
    const table = el("table", { "data-testid": "pg-validate-issues" });
    table.appendChild(el("thead", null, [el("tr", null, [
      el("th", { scope: "col", text: "code" }),
      el("th", { scope: "col", text: "path" }),
      el("th", { scope: "col", text: "detail" }),
    ])]));
    const body = el("tbody");
    if (!issues.length) {
      body.appendChild(el("tr", null, [el("td", { colspan: "3", class: "empty", text: "无拒绝项" })]));
    }
    issues.forEach(function (issue) {
      body.appendChild(el("tr", null, [
        el("td", { text: missing(issue.code) }),
        el("td", { text: missing(issue.path) }),
        el("td", { text: formatFree(issue.detail) }),
      ]));
    });
    table.appendChild(body);
    pgAppend("pg-validate-out", table);
  }

  function fieldTable(fields, required) {
    const table = el("table", { "data-testid": required ? "pg-field-required" : "pg-field-optional" });
    table.appendChild(el("thead", null, [el("tr", null, [
      el("th", { scope: "col", text: "字段" }),
      el("th", { scope: "col", text: "类型" }),
      el("th", { scope: "col", text: "必填" }),
      el("th", { scope: "col", text: "约束" }),
      el("th", { scope: "col", text: "说明" }),
    ])]));
    const body = el("tbody");
    const rows = Array.isArray(fields) ? fields : [];
    if (!rows.length) {
      body.appendChild(el("tr", null, [el("td", { colspan: "5", class: "empty", text: NOT_RECORDED })]));
    }
    rows.forEach(function (field) {
      const constraints = [];
      if (Array.isArray(field.enum) && field.enum.length) constraints.push("enum=" + field.enum.join("|"));
      if (field.max_items) constraints.push("max_items=" + String(field.max_items));
      if (field.item_type) constraints.push("item_type=" + String(field.item_type));
      if (field.item_max_bytes) constraints.push("item_max_bytes=" + String(field.item_max_bytes));
      if (field.max_bytes) constraints.push("max_bytes=" + String(field.max_bytes));
      body.appendChild(el("tr", { "data-testid": "pg-field-row", "data-field": String(field.name || "") }, [
        el("td", { text: missing(field.name) }),
        el("td", { text: missing(field.type) }),
        el("td", { text: required ? "required" : "optional" }),
        el("td", { text: constraints.length ? constraints.join(" · ") : "-" }),
        el("td", { text: formatFree(field.description) }),
      ]));
    });
    table.appendChild(body);
    return table;
  }

  function renderSelectedDp() {
    pgClear("pg-meta");
    pgClear("pg-fields");
    const point = pg().byId[pg().selected];
    if (!point) {
      pgAppend("pg-meta", el("p", { class: "muted", text: "尚未选择决策点。" }));
      return;
    }
    const budget = pg().budget && typeof pg().budget === "object" ? pg().budget : {};
    const transport = pg().transport && typeof pg().transport === "object" ? pg().transport : {};
    const rows = [
      ["DP", missing(point.id)],
      ["tier（P0 = 生产默认关闭）", missing(point.tier)],
      ["默认启用", flag(point.default_enabled)],
      ["默认模式", missing(point.default_mode)],
      ["当前启用（项目配置）", flag(point.enabled)],
      ["当前模式", missing(point.mode)],
      ["配置来源", missing(point.config_source)],
      ["questions_version", missing(point.questions_version)],
      ["executor（本页从不执行）", missing(point.executor)],
      ["wired", flag(point.wired)],
      ["预算 max_state_bytes", missing(budget.max_state_bytes)],
      ["传输（配置态，不探测）", missing(transport.state) + " · " + missing(transport.detail)],
      ["观察提交契约", pg().observeOnly === true ? "observe_only=true（人工显式提交，仅观察）" : NOT_RECORDED],
    ];
    pgAppend("pg-meta", definitionList(rows));
    if (point.tier === "P0") {
      pgAppend("pg-meta", el("p", { class: "warn", "data-testid": "pg-p0-note", text: "P0：生产默认关闭；测试只能人工仅观察提交，不授权、不执行、不写生产记录。" }));
    }
    if (point.enabled !== true) {
      pgAppend("pg-meta", el("p", { class: "warn", text: "当前关闭：观察提交仍走人工仅观察通道；生产 disabled 行为不变。" }));
    }
    const warnings = pg().config && Array.isArray(pg().config.warnings) ? pg().config.warnings : [];
    pgAppend("pg-meta", el("p", { class: "muted", text: "配置层：" + missing(pg().config && pg().config.layer) + " · 配置告警：" + flagsText(warnings) }));
    const required = Array.isArray(point.required_state_fields) ? point.required_state_fields : [];
    const optional = Array.isArray(point.optional_state_fields) ? point.optional_state_fields : [];
    pgAppend("pg-fields", el("h3", { text: "业务输入契约（required，typed）" }));
    pgAppend("pg-fields", fieldTable(required, true));
    pgAppend("pg-fields", el("h3", { text: "业务输入契约（optional，typed）" }));
    pgAppend("pg-fields", fieldTable(optional, false));
  }

  function renderDpOptions() {
    const select = document.getElementById("dp-select");
    if (!select) return;
    select.replaceChildren();
    pg().points.forEach(function (point) {
      if (!point || typeof point !== "object" || typeof point.id !== "string") return;
      pg().byId[point.id] = point;
      select.appendChild(el("option", {
        value: point.id,
        text: point.id + " · tier=" + missing(point.tier) + " · enabled=" + flag(point.enabled),
      }));
    });
    const ids = Object.keys(pg().byId);
    if (!pg().selected || !pg().byId[pg().selected]) pg().selected = ids.length ? ids[0] : "";
    select.value = pg().selected;
    renderSelectedDp();
  }

  function renderTestHistory(data) {
    const body = document.getElementById("pg-history-rows");
    if (body) body.replaceChildren();
    const records = data && Array.isArray(data.records) ? data.records : [];
    const warnings = data && Array.isArray(data.warnings) ? data.warnings : [];
    records.forEach(function (record) {
      const row = record && typeof record === "object" ? record : {};
      const tr = el("tr", { "data-testid": "pg-history-row", "data-submission-id": String(row.submission_id || "") });
      tr.appendChild(el("td", { text: missing(row.submission_id) }));
      tr.appendChild(el("td", { text: missing(row.dp) }));
      tr.appendChild(el("td", { text: missing(row.state) }));
      tr.appendChild(el("td", { text: missing(row.retry_of) }));
      tr.appendChild(el("td", { text: missing(row.call_id) }));
      tr.appendChild(el("td", { text: missing(row.book_ref) }));
      tr.appendChild(el("td", { text: flag(row.zero_call) }));
      tr.appendChild(el("td", { text: missing(row.http_attempts) }));
      const answerCell = el("td");
      answerCell.appendChild(el("div", { text: row.answer_persisted === true ? formatFree(row.answer) : NOT_RECORDED + "（无持久化投影：" + missing(row.projection_status) + "）" }));
      answerCell.appendChild(el("div", { class: "basis", text: "projection=" + missing(row.projection_status) + " · sha256=" + missing(row.projection_sha256) }));
      tr.appendChild(answerCell);
      const open = el("button", {
        type: "button",
        "data-testid": "pg-history-open",
        "data-submission-id": String(row.submission_id || ""),
      }, ["详情"]);
      open.addEventListener("click", function () {
        openSubmission(row.submission_id);
      });
      const cell = el("td");
      cell.appendChild(open);
      tr.appendChild(cell);
      if (body) body.appendChild(tr);
    });
    if (!records.length && body) {
      body.appendChild(el("tr", null, [el("td", { colspan: "10", class: "empty", text: "暂无独立测试记录。" })]));
    }
    pg().history = data || null;
    setText("pg-history-meta",
      "共 " + missing(data && data.total) + " 条 · limit " + missing(data && data.limit) +
      " · source=" + missing(data && data.source) + " · scope=" + missing(data && data.scope) +
      " · observe_only=" + flag(data && data.observe_only) +
      " · 读取告警：" + flagsText(warnings));
  }

  function captureBlock(label, copy) {
    const block = el("div", { class: "capture", "data-testid": "pg-capture" });
    block.appendChild(el("h5", { text: label }));
    if (!copy || typeof copy !== "object") {
      block.appendChild(line("内容", NOT_RECORDED));
      return block;
    }
    block.appendChild(line(
      "capture 标记",
      "byte_exact=" + flag(copy.byte_exact) +
        " · redactions=" + missing(copy.redactions) +
        " · truncated=" + flag(copy.truncated) +
        " · read_capped=" + flag(copy.read_capped) +
        " · boundary_scrubbed=" + flag(copy.boundary_scrubbed) +
        " · text_omitted=" + flag(copy.text_omitted) +
        " · output_omitted=" + flag(copy.output_omitted)
    ));
    block.appendChild(line("wire_len / stored_len", missing(copy.wire_len) + " / " + missing(copy.stored_len)));
    block.appendChild(line("captured_redacted_sha256", missing(copy.captured_redacted_sha256)));
    if (copy.output_omitted === true) {
      block.appendChild(el("p", { class: "muted", text: "本次列表输出省略正文（打开详情可读；正文仍只存在于 wire 存储层）。" }));
    } else if (typeof copy.text === "string") {
      block.appendChild(el("pre", { class: "copy-text", text: copy.text }));
      if (copy.byte_exact !== true) {
        block.appendChild(el("p", { class: "muted", text: "已脱敏或截断：本次正文不是逐字节原文。" }));
      }
    } else if (copy.text_omitted === true) {
      block.appendChild(el("p", { class: "muted", text: "存储层已省略正文（text_omitted=true）。" }));
    } else {
      block.appendChild(el("p", { class: "muted", text: NOT_RECORDED + "（未采集正文）" }));
    }
    return block;
  }

  function renderAttempts(record) {
    const attempts = Array.isArray(record.attempts) ? record.attempts : [];
    const section = pgSection("实际请求 / 实际返回（本 submission 的调用，存储层原文）", []);
    if (!attempts.length) {
      section.appendChild(el("p", { class: "muted", text: "attempts：" + NOT_RECORDED }));
      return section;
    }
    attempts.forEach(function (attempt) {
      const item = attempt && typeof attempt === "object" ? attempt : {};
      section.appendChild(el("h4", { text: "attempt_index=" + missing(item.attempt_index) }));
      section.appendChild(line(
        "元数据",
        "method=" + missing(item.method) +
          " · url_path=" + missing(item.url_path) +
          " · http_status=" + missing(item.http_status) +
          " · latency_ms=" + missing(item.latency_ms) +
          " · model=" + missing(item.model) +
          " · unfinished=" + flag(item.unfinished)
      ));
      section.appendChild(line("error_class / error_detail", missing(item.error_class) + " · " + formatFree(item.error_detail)));
      section.appendChild(line("usage", usageText(item.usage, { compact: true })));
      section.appendChild(captureBlock("request（实际请求）", item.request));
      section.appendChild(captureBlock("response（实际返回）", item.response));
    });
    return section;
  }

  function renderSubmissionDetail(record) {
    const holder = pgOut("pg-detail");
    if (!holder) return;
    holder.replaceChildren();
    const row = record && typeof record === "object" ? record : {};
    holder.appendChild(el("h3", { text: "测试提交详情 · " + missing(row.submission_id) }));
    holder.appendChild(definitionList([
      ["submission_id", missing(row.submission_id)],
      ["dp", missing(row.dp)],
      ["state", missing(row.state)],
      ["retry_of", missing(row.retry_of)],
      ["decision_id", missing(row.decision_id)],
      ["decision_ran", flag(row.decision_ran)],
      ["call_id", missing(row.call_id)],
      ["book_ref", missing(row.book_ref)],
      ["state_digest", missing(row.state_digest)],
      ["zero_call", flag(row.zero_call)],
      ["http_attempts", missing(row.http_attempts)],
      ["capture_status", missing(row.capture_status)],
      ["started_at", missing(row.started_at)],
      ["finished_at", missing(row.finished_at)],
      ["answer_persisted", flag(row.answer_persisted)],
      ["projection_status", missing(row.projection_status)],
      ["projection_sha256", missing(row.projection_sha256)],
      ["projection_redactions", missing(row.projection_redactions)],
    ]));
    holder.appendChild(el("h4", { text: "当次答案（来自该 submission 的持久化安全投影）" }));
    holder.appendChild(renderAnswerBlock(row.answer, {
      missingText: row.answer_persisted === true ? "当次答案：" + NOT_RECORDED : "当次答案：未持久化（" + missing(row.projection_status) + "）",
    }));
    const issues = Array.isArray(row.issues) ? row.issues : [];
    const list = el("ul", { class: "plain" });
    if (!issues.length) list.appendChild(el("li", { text: "拒绝/问题项：无" }));
    issues.forEach(function (issue) { list.appendChild(el("li", { text: String(issue) })); });
    holder.appendChild(el("h4", { text: "拒绝/问题项" }));
    holder.appendChild(list);
    holder.appendChild(el("h4", { text: "采纳判定与动作预览" }));
    holder.appendChild(outcomeBlock(row.outcome));
    holder.appendChild(el("h4", { text: "测试 DAG（本 submission 已记录事实；观察路径不执行动作）" }));
    const layout = el("div", { class: "dag-layout" });
    const graphWrap = el("div", { class: "dag-graph-wrap" });
    const dagHolder = el("div", {
      id: "pg-dag-graph",
      class: "dag-graph",
      "data-testid": "pg-dag-graph",
      role: "group",
      "aria-label": "测试提交处理顺序（10 个节点）",
    });
    graphWrap.appendChild(dagHolder);
    graphWrap.appendChild(el("p", {
      class: "notes",
      text: "箭头表示既定处理顺序，不代表该步已发生；测试观察路径不执行任何业务动作。",
    }));
    layout.appendChild(graphWrap);
    layout.appendChild(el("aside", {
      id: "pg-dag-node-detail",
      class: "detail-section dag-side",
      "data-testid": "pg-dag-node-detail",
      "aria-live": "polite",
    }));
    holder.appendChild(layout);
    renderDagGraph(dagHolder, submissionDagNodes(row), "pg-dag-node", "pg-dag-node-detail");
    holder.appendChild(renderAttempts(row));
    const close = el("button", { type: "button", id: "pg-detail-close" }, ["清空详情"]);
    close.addEventListener("click", function () { holder.replaceChildren(); });
    holder.appendChild(close);
  }

  function submissionDagNodes(row) {
    // Every node is derived from *this* submission's recorded facts, using the
    // same node ids/labels/status vocabulary as the T06 workbench DAG. Nodes the
    // observation path never writes stay "missing"; the action node is
    // "not-executed" because observe_only never performs a business act.
    const attempts = typeof row.http_attempts === "number" ? row.http_attempts : null;
    const ran = row.decision_ran === true;
    const zero = row.zero_call === true;
    const node = function (id, label, status, basis) {
      return { id: id, label: label, status: status, basis: basis, detail: null };
    };
    return [
      node("key", "key", "missing", ["测试 scope 无 key（不把 run key 猜成记录 key）"]),
      node("role", "角色", "missing", ["本投影未输出 actor 字段"]),
      node("dp", "DP", row.dp ? "observed" : "missing", [
        row.dp ? "submission.dp=" + row.dp : "dp 未记录",
      ]),
      node(
        "input",
        "输入",
        row.book_ref || row.state_digest ? "observed" : "missing",
        [
          row.book_ref ? "book_ref=" + row.book_ref : "book_ref 未记录",
          row.state_digest ? "state_digest=" + row.state_digest : "state_digest 未记录",
        ]
      ),
      node("decide", "decide 处理", ran ? "observed" : "missing", [
        ran ? "decision_id=" + missing(row.decision_id) : "decision 未运行",
      ]),
      node(
        "request",
        "API 请求",
        zero ? "not-executed" : attempts !== null && attempts > 0 ? "observed" : "missing",
        [
          zero
            ? "zero_call=true：本次未发送"
            : "http_attempts=" + missing(row.http_attempts),
        ]
      ),
      node("model", "决策模型", row.call_id ? "observed" : "missing", [
        row.call_id ? "call_id=" + row.call_id : "call_id 未记录",
      ]),
      node("response", "返回结果", row.answer_persisted === true ? "observed" : "missing", [
        row.answer_persisted === true
          ? "answer 已按安全投影持久化"
          : "answer 未持久化（projection=" + missing(row.projection_status) + "）",
      ]),
      node("receipt", "接收签收", "missing", ["观察路径不写接收/签收反馈"]),
      node("action", "行动反馈", "not-executed", ["observe_only：行动模拟，未执行"]),
    ];
  }

  function readBook() {
    pgClear("pg-validate-out");
    pgClear("pg-submit-out");
    const node = document.getElementById("book-editor");
    const text = node && typeof node.value === "string" ? node.value : "";
    if (!text.trim()) {
      pgAppend("pg-validate-out", el("p", { class: "error", text: "决策本为空：请先生成骨架或输入 JSON。" }));
      return null;
    }
    let parsed = null;
    try {
      parsed = JSON.parse(text);
    } catch (error) {
      pgAppend("pg-validate-out", el("p", { class: "error", text: "决策本不是合法 JSON：未发起任何请求。" }));
      return null;
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      pgAppend("pg-validate-out", el("p", { class: "error", text: "决策本必须是 JSON 对象：未发起任何请求。" }));
      return null;
    }
    return parsed;
  }

  async function loadPlayground() {
    if (!state.token) return;
    clearError();
    setPgStatus("正在读取 DP 契约与独立测试记录（只读元数据；不校验、不发模型请求）…");
    try {
      const dps = await getJson("/api/dps");
      const history = await getJson("/api/test/history");
      const data = dps.data && typeof dps.data === "object" ? dps.data : {};
      pg().points = Array.isArray(data.points) ? data.points : [];
      pg().budget = data.budget && typeof data.budget === "object" ? data.budget : null;
      pg().transport = data.transport && typeof data.transport === "object" ? data.transport : null;
      pg().config = data.config && typeof data.config === "object" ? data.config : null;
      pg().observeOnly = data.observe_only === true;
      pg().byId = Object.create(null);
      pg().loaded = true;
      renderDpOptions();
      renderTestHistory(history.data && typeof history.data === "object" ? history.data : {});
      setPgStatus("已加载 " + String(pg().points.length) + " 个注册 DP（元数据与测试记录；未校验、未发现凭证、未发模型请求）。");
    } catch (error) {
      pg().loaded = false;
      setPgStatus("DP 契约加载失败：未显示任何伪造数据。");
      showError(error);
    }
  }

  async function refreshTestHistory() {
    if (!state.token) return;
    try {
      const payload = await getJson("/api/test/history");
      renderTestHistory(payload.data && typeof payload.data === "object" ? payload.data : {});
    } catch (error) {
      setText("pg-history-meta", "测试记录读取失败：未显示任何伪造数据。");
      showError(error);
    }
  }

  async function scaffoldSelected() {
    const dp = pg().selected;
    if (!state.token || !dp) {
      setPgStatus("请先加载并选择一个 DP（加载只读元数据，不发模型请求）。");
      return;
    }
    clearError();
    setPgStatus("正在生成决策本骨架（注册表只读，不发模型请求）…");
    try {
      const payload = await postJsonPage("/api/test/scaffold", { dp: dp });
      const data = payload.data && typeof payload.data === "object" ? payload.data : {};
      const editor = document.getElementById("book-editor");
      if (editor) editor.value = JSON.stringify(data.book || {}, null, 2);
      pg().submitId = null;
      pg().lastDigest = null;
      pg().caseLoaded = null;
      pg().caseQuestions = null;
      renderQuestionsEditor();
      setPgStatus("已生成 " + dp + " 的骨架：占位符必须替换后再校验；生成过程未发模型请求。");
    } catch (error) {
      setPgStatus("骨架生成失败：未伪造决策本。");
      showError(error);
    }
  }

  async function validateSelected() {
    const dp = pg().selected;
    if (!state.token || !dp) return;
    const book = readBook();
    if (!book) return;
    refreshDerivedCriteria();
    const gathered = collectQuestions(dp);
    if (!gathered.ok) {
      pgClear("pg-validate-out");
      pgAppend("pg-validate-out", el("p", {
        class: "error",
        "data-testid": "pg-questions-error",
        text: gathered.error,
      }));
      return;
    }
    clearError();
    const body = { dp: dp, book: book };
    if (gathered.questions) body.questions = gathered.questions;
    try {
      const payload = await postJsonPage("/api/test/validate", body);
      renderValidateResult(payload.data && typeof payload.data === "object" ? payload.data : {});
    } catch (error) {
      pgClear("pg-validate-out");
      pgAppend("pg-validate-out", el("p", { class: "error", text: "校验请求失败：" + String(error && error.code ? error.code : "error") + " · " + String(error && error.message ? error.message : error) }));
      showError(error);
    }
  }

  function newSubmissionId() {
    pg().seq = (pg().seq || 0) + 1;
    return "ui-" + Date.now().toString(36) + "-" + String(pg().seq);
  }

  function digestText(text) {
    let hash = 2166136261;
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = (hash * 16777619) >>> 0;
    }
    return String(hash) + ":" + String(text.length);
  }

  async function sendSubmit(book, submitId, retryOf, questions) {
    const dp = pg().selected;
    pg().inflight = true;
    setDisabled("pg-submit", true);
    setDisabled("pg-retry", true);
    setText("pg-submit-id", "submission id=" + submitId + (retryOf ? " · retry_of=" + retryOf : " (新 id)"));
    clearError();
    try {
      const body = { dp: dp, book: book, submit_id: submitId, observe_only: true };
      if (retryOf) body.retry_of = retryOf;
      if (questions) body.questions = questions;
      const payload = await postJsonPage("/api/test/submit", body);
      pg().lastSubmittedId = submitId;
      renderSubmitResult(payload.data && typeof payload.data === "object" ? payload.data : {}, 200, null);
      await refreshTestHistory();
    } catch (error) {
      if (error && error.code === "busy" && error.data) {
        renderBusy(error.data, error);
      } else {
        if (error && error.data && typeof error.data === "object" && error.data.state) {
          renderSubmitResult(error.data, error.status || 0, error);
        } else {
          renderSubmitFailure(error);
        }
      }
    } finally {
      pg().inflight = false;
      setDisabled("pg-submit", false);
      setDisabled("pg-retry", false);
    }
  }

  async function submitSelected() {
    if (!state.token || !pg().selected) {
      setPgStatus("请先加载并选择一个 DP。");
      return;
    }
    if (pg().inflight) {
      setPgStatus("上一次提交还在进行：未重复发送。");
      return;
    }
    const book = readBook();
    if (!book) return;
    refreshDerivedCriteria();
    const gathered = collectQuestions(pg().selected);
    if (!gathered.ok) {
      pgClear("pg-submit-out");
      pgAppend("pg-submit-out", el("p", { class: "error", "data-testid": "pg-questions-error", text: gathered.error }));
      return;
    }
    const digest = digestText(JSON.stringify(book) + JSON.stringify(gathered.questions || null));
    if (!pg().submitId || pg().lastDigest !== digest) pg().submitId = newSubmissionId();
    pg().lastDigest = digest;
    await sendSubmit(book, pg().submitId, null, gathered.questions);
  }

  async function retrySubmit() {
    if (!state.token || !pg().selected) return;
    if (pg().inflight) {
      setPgStatus("上一次提交还在进行：未重复发送。");
      return;
    }
    const previous = pg().lastSubmittedId;
    if (!previous) {
      pgClear("pg-submit-out");
      pgAppend("pg-submit-out", el("p", { class: "warn", text: "没有可重试的提交：重试必须指向一次已提交的记录（新 id + retry_of）。" }));
      return;
    }
    const book = readBook();
    if (!book) return;
    refreshDerivedCriteria();
    const gathered = collectQuestions(pg().selected);
    if (!gathered.ok) {
      pgClear("pg-submit-out");
      pgAppend("pg-submit-out", el("p", { class: "error", "data-testid": "pg-questions-error", text: gathered.error }));
      return;
    }
    const id = newSubmissionId();
    pg().submitId = id;
    pg().lastDigest = digestText(JSON.stringify(book) + JSON.stringify(gathered.questions || null));
    await sendSubmit(book, id, previous, gathered.questions);
  }

  async function openSubmission(submissionId) {
    if (!state.token || typeof submissionId !== "string" || !submissionId) return;
    clearError();
    try {
      const payload = await getJson("/api/test/submissions/" + encodeURIComponent(submissionId));
      renderSubmissionDetail(payload.data && typeof payload.data === "object" ? payload.data : {});
    } catch (error) {
      showError(error);
    }
  }

  function onDpChange() {
    const select = document.getElementById("dp-select");
    pg().selected = select && typeof select.value === "string" ? select.value : "";
    pg().submitId = null;
    pg().lastDigest = null;
    pg().caseQuestions = null;
    renderQuestionsEditor();
    renderSelectedDp();
    pgClear("pg-validate-out");
    pgClear("pg-submit-out");
    pgClear("pg-detail");
  }

  // -- case questions (complete, editable, observe-only) --------------------

  function cloneJson(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function choicesText(question) {
    if (Array.isArray(question.choices)) {
      const parts = question.choices.map(function (choice) { return String(choice); });
      const labels = question.labels && typeof question.labels === "object" ? question.labels : {};
      return "choices：" + parts.map(function (choice) {
        return labels[choice] ? choice + "（" + String(labels[choice]) + "）" : choice;
      }).join(" / ");
    }
    if (typeof question.dynamic_choices === "string") {
      return "choices：来自 state." + question.dynamic_choices + "（候选只在那里维护一次）";
    }
    return "choices：未记录";
  }

  function editorState() {
    const editor = document.getElementById("book-editor");
    const text = editor && typeof editor.value === "string" ? editor.value : "";
    if (!text.trim()) return null;
    const parsed = parseJson(text);
    if (!parsed.ok) return null;
    const book = parsed.value;
    if (!book || typeof book !== "object" || Array.isArray(book)) return null;
    const state = book.state;
    return state && typeof state === "object" && !Array.isArray(state) ? state : null;
  }

  function deriveDp3Criteria(options) {
    const list = Array.isArray(options) ? options : [];
    const lines = list.map(function (option) {
      const item = option && typeof option === "object" ? option : {};
      const id = isMissing(item.id) ? "?" : String(item.id);
      const label = isMissing(item.label) ? "" : String(item.label);
      const description = isMissing(item.description) ? "" : String(item.description);
      return id + (label ? " · " + label : "") + "：" + description;
    });
    return (
      "只读派生（唯一来源：state.handling_options；不写入 questions，最终以 server 预览为准）\n" +
      (lines.length ? lines.join("\n") : "state.handling_options 未记录或为空")
    );
  }

  function renderQuestionsEditor() {
    const holder = document.getElementById("pg-questions");
    if (!holder) return;
    holder.replaceChildren();
    pg().questionNodes = [];
    const questions = pg().caseQuestions && typeof pg().caseQuestions === "object" && !Array.isArray(pg().caseQuestions)
      ? Object.keys(pg().caseQuestions).map(function (id) {
          return Object.assign({ id: id }, pg().caseQuestions[id]);
        })
      : null;
    if (!questions || !questions.length) {
      setText("pg-questions-status", "未记录（本 case 未提供 questions；后端发布后即可查看/编辑）");
      return;
    }
    const dp = pg().selected;
    const state = editorState();
    setText(
      "pg-questions-status",
      "已载入 " + String(questions.length) +
        " 个原生问题（可编辑；只随本次 observe_only 观察请求发送，不写生产配置、不调用模型）"
    );
    questions.forEach(function (rawQuestion) {
      const question = rawQuestion && typeof rawQuestion === "object" ? rawQuestion : {};
      const id = isMissing(question.id) ? "" : String(question.id);
      const block = el("div", {
        class: "question",
        "data-testid": "pg-question",
        "data-question-id": id,
        "data-kind": isMissing(question.type) ? NOT_RECORDED : String(question.type),
      });
      const head = el("div", { class: "question-head" });
      head.appendChild(el("h4", { text: "问题 " + (id || NOT_RECORDED) }));
      head.appendChild(el("span", { class: "choices", text: choicesText(question) }));
      block.appendChild(head);

      const instructionsLabel = el("label", { class: "question-field" });
      instructionsLabel.appendChild(el("span", { text: "instructions（可编辑；模型看到的问题说明）" }));
      const instructions = el("textarea", {
        "data-testid": "pg-question-instructions",
        rows: "3",
        spellcheck: "false",
        autocomplete: "off",
      });
      instructions.value = isMissing(question.instructions) ? "" : String(question.instructions);
      instructionsLabel.appendChild(instructions);
      block.appendChild(instructionsLabel);

      let criteriaInput = null;
      let derived = null;
      if (dp === "dp3-worker-clarify") {
        block.appendChild(el("p", {
          class: "notes",
          text: "criteria（只读派生：候选只在 state.handling_options 维护一次）",
        }));
        derived = el("div", {
          class: "derived",
          "data-testid": "pg-question-criteria-derived",
          text: deriveDp3Criteria(state ? state.handling_options : null),
        });
        block.appendChild(derived);
      } else if (!isMissing(question.criteria)) {
        const criteriaLabel = el("label", { class: "question-field" });
        criteriaLabel.appendChild(el("span", { text: "criteria（可编辑：JSON 或原文）" }));
        criteriaInput = el("textarea", {
          "data-testid": "pg-question-criteria-input",
          rows: "4",
          spellcheck: "false",
          autocomplete: "off",
        });
        criteriaInput.value =
          typeof question.criteria === "string"
            ? question.criteria
            : JSON.stringify(question.criteria, null, 2);
        criteriaLabel.appendChild(criteriaInput);
        block.appendChild(criteriaLabel);
      }
      holder.appendChild(block);
      pg().questionNodes.push({
        question: question,
        instructions: instructions,
        criteria: criteriaInput,
        derived: derived,
      });
    });
  }

  function refreshDerivedCriteria() {
    const state = editorState();
    pg().questionNodes.forEach(function (entry) {
      if (!entry.derived) return;
      entry.derived.textContent = deriveDp3Criteria(state ? state.handling_options : null);
    });
  }

  function collectQuestions(dp) {
    const questions = pg().caseQuestions;
    if (!questions || !Object.keys(questions).length) return { ok: true, questions: null };
    const collected = {};
    for (let index = 0; index < pg().questionNodes.length; index += 1) {
      const entry = pg().questionNodes[index];
      const next = cloneJson(entry.question);
      const label = next.id ? String(next.id) : String(index + 1);
      const instructions =
        entry.instructions && typeof entry.instructions.value === "string" ? entry.instructions.value : "";
      if (!instructions.trim()) {
        return { ok: false, error: "问题 " + label + " 的 instructions 为空：未发起任何请求。" };
      }
      next.instructions = instructions;
      if (dp === "dp3-worker-clarify") {
        // dp3 candidates and their criteria have exactly one source:
        // state.handling_options. Never duplicate them into questions.
        delete next.criteria;
      } else if (entry.criteria) {
        const text = typeof entry.criteria.value === "string" ? entry.criteria.value.trim() : "";
        if (text) {
          const parsed = parseJson(text);
          if (parsed.ok) {
            next.criteria = parsed.value;
          } else if (text.charAt(0) === "{" || text.charAt(0) === "[") {
            return { ok: false, error: "问题 " + label + " 的 criteria 不是合法 JSON：未发起任何请求。" };
          } else {
            next.criteria = text;
          }
        } else {
          delete next.criteria;
        }
      }
      collected[next.id] = next;
    }
    return { ok: true, questions: collected };
  }

  function openSelectedCaseQuestions(found) {
    if (found && typeof found.dp === "string" && pg().byId[found.dp]) {
      // The questions belong to this dp: render before the editor sees them.
      pg().selected = found.dp;
    }
    pg().caseQuestions = found.questions && typeof found.questions === "object" && !Array.isArray(found.questions)
      ? cloneJson(found.questions) : null;
    renderQuestionsEditor();
  }

  function resetCaseQuestions() {
    const loaded = pg().caseLoaded;
    if (!loaded || !loaded.questions || typeof loaded.questions !== "object" || Array.isArray(loaded.questions)) {
      setText("pg-questions-status", "未记录（没有可恢复的 case questions）");
      return;
    }
    pg().caseQuestions = cloneJson(loaded.questions);
    renderQuestionsEditor();
    setText("pg-questions-status", "已恢复为 case 原问题（0 请求；未改动生产配置）");
  }

  // -- offline cases (read-only list, zero model, zero credential) ----------

  function renderCaseOptions() {
    const select = document.getElementById("case-select");
    if (!select) return;
    select.replaceChildren();
    select.appendChild(el("option", { value: "", text: "（未选择）" }));
    (pg().cases || []).forEach(function (item) {
      if (!item || typeof item.dp !== "string") return;
      select.appendChild(el("option", {
        value: item.dp,
        text: item.dp + " · " + missing(item.title),
      }));
    });
    select.value = "";
  }

  async function loadCaseList() {
    if (!state.token) return;
    clearError();
    setText("pg-case-status", "正在读取离线 case 列表（只读固定文件，0 模型调用，0 凭证读取）…");
    try {
      const payload = await getJson("/api/test/cases");
      const data = payload.data && typeof payload.data === "object" ? payload.data : {};
      pg().cases = Array.isArray(data.cases) ? data.cases : [];
      renderCaseOptions();
      setText(
        "pg-case-status",
        "已读取 " + String(pg().cases.length) + " 个离线 case（case_version=" +
          missing(data.case_version) + " · source=" + missing(data.source) +
          "）；title/note 只在列表上显示，不写入编辑器，也不会发送。"
      );
    } catch (error) {
      pg().cases = [];
      renderCaseOptions();
      setText("pg-case-status", "离线 case 读取失败：未显示任何伪造 case。");
      showError(error);
    }
  }

  function openSelectedCase() {
    const select = document.getElementById("case-select");
    const dp = select && typeof select.value === "string" ? select.value : "";
    const found = (pg().cases || []).filter(function (item) {
      return item && item.dp === dp;
    })[0];
    pgClear("pg-local-out");
    if (!found) {
      setText("pg-case-status", "未选择离线 case：先读取列表并选择一项。");
      return;
    }
    const editor = document.getElementById("book-editor");
    if (editor) editor.value = JSON.stringify(found.book || {}, null, 2);
    pg().caseLoaded = found;
    pg().submitId = null;
    pg().lastDigest = null;
    openSelectedCaseQuestions(found);
    const dpSelect = document.getElementById("dp-select");
    if (dpSelect && pg().byId[found.dp]) {
      pg().selected = found.dp;
      dpSelect.value = found.dp;
      renderSelectedDp();
    }
    setText(
      "pg-case-status",
      "已载入 " + found.dp + " 的 book（case sha256=" + missing(found.sha256) +
        "）；载入本身不发请求、不调用模型。"
    );
  }

  function collectTexts(value, path, out) {
    if (typeof value === "string") {
      out.push({ path: path || "<root>", text: value });
      return out;
    }
    if (Array.isArray(value)) {
      value.forEach(function (item, index) {
        collectTexts(item, (path || "") + "[" + String(index) + "]", out);
      });
      return out;
    }
    if (value && typeof value === "object") {
      Object.keys(value).forEach(function (key) {
        collectTexts(value[key], path ? path + "." + key : key, out);
      });
    }
    return out;
  }

  function localCaseIssues(book, expectedDp) {
    // Offline structural check only: field presence, placeholders, dynamic
    // candidates and the dp25 four-section shape. The registry ``check_book``
    // review stays the server-side authority ("校验决策本").
    const issues = [];
    if (!book || typeof book !== "object" || Array.isArray(book)) {
      return ["决策本必须是 JSON 对象。"];
    }
    const dp = typeof book.decision_point === "string" ? book.decision_point : "";
    if (!dp) issues.push("book.decision_point 缺失。");
    if (expectedDp && dp && dp !== expectedDp) {
      issues.push("book.decision_point 与所选 case 不一致：" + dp);
    }
    const state =
      book.state && typeof book.state === "object" && !Array.isArray(book.state) ? book.state : null;
    if (!state) {
      issues.push("book.state 缺失或不是对象。");
      return issues;
    }
    (DESIGN_FIELDS[dp] || []).forEach(function (field) {
      if (isMissing(state[field])) issues.push("缺少 design 字段 state." + field + "。");
    });
    collectTexts(book, "", []).forEach(function (entry) {
      if (PLACEHOLDER_PATTERN.test(entry.text)) {
        issues.push("字段 " + entry.path + " 仍是占位符或被省略。");
      } else if (!entry.text.trim()) {
        issues.push("字段 " + entry.path + " 为空。");
      }
    });
    if (dp === "dp3-worker-clarify") {
      const options = Array.isArray(state.handling_options) ? state.handling_options : [];
      if (options.length < 2) {
        issues.push("dp3 候选不足：至少需要 2 个可区分候选（当前 " + String(options.length) + "）。");
      }
      const labels = [];
      options.forEach(function (option, index) {
        if (!option || typeof option !== "object" || Array.isArray(option)) {
          issues.push("候选 #" + String(index + 1) + " 不是对象。");
          return;
        }
        ["id", "label", "description"].forEach(function (key) {
          if (isMissing(option[key]) || String(option[key]).trim() === "") {
            issues.push("候选 #" + String(index + 1) + " 缺少 " + key + "。");
          }
        });
        if (typeof option.label === "string") labels.push(option.label);
      });
      if (labels.length !== new Set(labels).size) {
        issues.push("dp3 候选标签不可区分（重复）。");
      }
      const background = state.background && typeof state.background === "object" ? state.background : null;
      if (!background) {
        issues.push("dp3 background 缺失。");
      } else {
        ["task_goal", "current_state", "decision_reason", "constraints_impact"].forEach(function (key) {
          if (isMissing(background[key])) issues.push("dp3 background." + key + " 缺失。");
        });
      }
    }
    if (dp === "dp25-signoff-conclusion") {
      const evidence = state.verification_evidence;
      if (!evidence || typeof evidence !== "object" || Array.isArray(evidence)) {
        issues.push("dp25 verification_evidence 缺失。");
      } else {
        if (!Array.isArray(evidence.verified)) {
          issues.push("dp25 verification_evidence.verified 必须是数组（可为空数组）。");
        }
        if (!Array.isArray(evidence.unverified)) {
          issues.push("dp25 verification_evidence.unverified 必须是数组（可为空数组）。");
        }
      }
      if (!Array.isArray(state.unfinished_impact)) {
        issues.push("dp25 unfinished_impact 必须是数组（可为空数组）。");
      }
    }
    if (dp === "dp2-checkpoint-split" && state.worker_execution !== undefined) {
      const execution = state.worker_execution;
      if (execution === "" || execution === null || (typeof execution === "object" && !Object.keys(execution).length)) {
        issues.push("dp2 worker_execution 为空；没有 worker 时请删除该字段而不是留空。");
      }
    }
    return issues;
  }

  function localValidateBook() {
    pgClear("pg-local-out");
    pgAppend("pg-local-out", el("p", {
      class: "notes",
      text: "本地校验（离线，0 请求，0 模型，0 凭证）：只做结构与占位符检查，不是 registry typed 校验。",
    }));
    const node = document.getElementById("book-editor");
    const text = node && typeof node.value === "string" ? node.value : "";
    if (!text.trim()) {
      pgAppend("pg-local-out", el("p", { class: "error", text: "决策本为空：未做任何校验。" }));
      return;
    }
    let book = null;
    try {
      book = JSON.parse(text);
    } catch (error) {
      pgAppend("pg-local-out", el("p", { class: "error", text: "决策本不是合法 JSON：未做任何校验。" }));
      return;
    }
    const expected =
      pg().caseLoaded && pg().caseLoaded.dp ? pg().caseLoaded.dp : pg().selected;
    const issues = localCaseIssues(book, expected);
    const ok = issues.length === 0;
    pgAppend("pg-local-out", el("p", {
      class: ok ? "status ok" : "status warn",
      "data-testid": "pg-local-headline",
      text: ok
        ? "本地校验通过（结构完整；typed 校验请点“校验决策本”，仍不发模型）"
        : "本地校验未通过（" + String(issues.length) + " 项；未发任何请求）",
    }));
    const list = el("ul", { class: "plain", "data-testid": "pg-local-issues" });
    if (!issues.length) list.appendChild(el("li", { text: "无结构问题。" }));
    issues.forEach(function (message) {
      list.appendChild(el("li", { text: message }));
    });
    pgAppend("pg-local-out", list);
  }

  // -- tabs / filters / boot ------------------------------------------------

  function selectTab(name) {
    const historySelected = name !== "playground";
    const historyTab = document.getElementById("tab-history");
    const playgroundTab = document.getElementById("tab-playground");
    if (historyTab) historyTab.setAttribute("aria-selected", historySelected ? "true" : "false");
    if (playgroundTab) playgroundTab.setAttribute("aria-selected", historySelected ? "false" : "true");
    setHidden("panel-history", !historySelected);
    setHidden("panel-playground", historySelected);
    if (!historySelected && !pg().loaded) {
      // Switching tabs reads nothing: the DP registry and the isolated test
      // records are loaded by an explicit click (metadata + records only).
      setPgStatus("尚未加载 DP 契约：点击“加载”只读取注册表与独立测试记录，不校验、不发现凭证、不发模型请求。");
    }
  }

  function readFilters() {
    state.filters = {
      key: inputValue("filter-key"),
      dp: inputValue("filter-dp"),
      source: selectValue("filter-source", ""),
      status: selectValue("filter-status", ""),
      scope: selectValue("filter-scope", SCOPE_DEFAULT) || SCOPE_DEFAULT,
    };
  }

  function applyFilters() {
    readFilters();
    loadHistory(0);
  }

  function resetFilters() {
    ["filter-key", "filter-dp", "filter-source", "filter-status"].forEach(function (id) {
      const node = document.getElementById(id);
      if (node) node.value = "";
    });
    const scope = document.getElementById("filter-scope");
    if (scope) scope.value = SCOPE_DEFAULT;
    state.filters = { key: "", dp: "", source: "", status: "", scope: SCOPE_DEFAULT };
    loadHistory(0);
  }

  function bootCodeFromFragment() {
    const match = /(?:^#|&)boot=([A-Za-z0-9_-]+)$/.exec(location.hash || "");
    return match ? match[1] : null;
  }

  function clearFragment() {
    if (location.hash) {
      history.replaceState(null, document.title, location.pathname + location.search);
    }
  }

  async function boot() {
    const code = bootCodeFromFragment();
    // Clear the fragment first: the code is single use and must not survive a
    // refresh, a screenshot or a copied URL.
    clearFragment();
    if (!code) {
      setText("boot-status", "未找到一次性引导码：请从 `mw decide monitor` 重新打开窗口。本页不会发起任何模型请求。");
      return;
    }
    setText("boot-status", "正在通过一次性引导码建立会话…");
    try {
      const payload = await postJson("/api/bootstrap", { code: code });
      const data = payload.data && typeof payload.data === "object" ? payload.data : {};
      const token = data.page_token;
      if (typeof token !== "string" || !token) {
        throw new Error("bad-bootstrap: 引导响应缺少 page token");
      }
      // Memory only: no storage, no cookie, no URL.
      state.token = token;
      state.booted = true;
      setText("boot-status", "已通过一次性引导码建立会话：token 仅保存在本页内存，刷新页面需要重新打开窗口。");
      await loadHistory(0);
    } catch (error) {
      state.token = null;
      state.booted = false;
      setText("boot-status", "引导失败：" + (error && error.code ? error.code : "无法兑换 page token"));
      showError(error);
    }
  }

  function init() {
    const historyTab = document.getElementById("tab-history");
    const playgroundTab = document.getElementById("tab-playground");
    if (historyTab) historyTab.addEventListener("click", function () { selectTab("history"); });
    if (playgroundTab) playgroundTab.addEventListener("click", function () { selectTab("playground"); });
    const form = document.getElementById("filter-form");
    if (form) {
      form.addEventListener("submit", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        applyFilters();
      });
    }
    const apply = document.getElementById("filter-apply");
    if (apply) apply.addEventListener("click", applyFilters);
    const reset = document.getElementById("filter-reset");
    if (reset) reset.addEventListener("click", resetFilters);
    const prev = document.getElementById("page-prev");
    if (prev) {
      prev.addEventListener("click", function () {
        loadHistory(Math.max(0, state.offset - state.limit));
      });
    }
    const next = document.getElementById("page-next");
    if (next) {
      next.addEventListener("click", function () {
        loadHistory(state.offset + state.limit);
      });
    }
    const close = document.getElementById("detail-close");
    if (close) close.addEventListener("click", closeDetail);
    const dialogDagTab = document.getElementById("record-dialog-tab-dag");
    if (dialogDagTab) {
      dialogDagTab.addEventListener("click", function () { selectDialogTab("dag"); });
    }
    const dialogLogTab = document.getElementById("record-dialog-tab-log");
    if (dialogLogTab) {
      dialogLogTab.addEventListener("click", function () { selectDialogTab("log"); });
    }
    const pgCasesLoad = document.getElementById("pg-cases-load");
    if (pgCasesLoad) pgCasesLoad.addEventListener("click", loadCaseList);
    const pgCaseOpen = document.getElementById("pg-case-open");
    if (pgCaseOpen) pgCaseOpen.addEventListener("click", openSelectedCase);
    const pgLocalValidate = document.getElementById("pg-local-validate");
    if (pgLocalValidate) pgLocalValidate.addEventListener("click", localValidateBook);
    const pgQuestionsReset = document.getElementById("pg-questions-reset");
    if (pgQuestionsReset) pgQuestionsReset.addEventListener("click", resetCaseQuestions);
    const pgLoad = document.getElementById("pg-load");
    if (pgLoad) pgLoad.addEventListener("click", loadPlayground);
    const pgRefresh = document.getElementById("pg-refresh-history");
    if (pgRefresh) pgRefresh.addEventListener("click", refreshTestHistory);
    const pgScaffold = document.getElementById("pg-scaffold");
    if (pgScaffold) pgScaffold.addEventListener("click", scaffoldSelected);
    const pgValidate = document.getElementById("pg-validate");
    if (pgValidate) pgValidate.addEventListener("click", validateSelected);
    const pgSubmit = document.getElementById("pg-submit");
    if (pgSubmit) pgSubmit.addEventListener("click", submitSelected);
    const pgRetry = document.getElementById("pg-retry");
    if (pgRetry) pgRetry.addEventListener("click", retrySubmit);
    const dpSelect = document.getElementById("dp-select");
    if (dpSelect) dpSelect.addEventListener("change", onDpChange);
    boot();
  }

  init();
})();

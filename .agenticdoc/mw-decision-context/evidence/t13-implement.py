from pathlib import Path
p=Path(__file__).resolve().parents[3]/'packages/multi-workers/decision_dashboard.js'
s=p.read_text(encoding='utf-8')
def replace(old,new):
 global s
 assert s.count(old)==1,(old[:100],s.count(old))
 s=s.replace(old,new)
replace('   DP-test tab reads nothing at all. Only an explicit click loads the DP\n *   registry and the isolated test records (metadata + records), and only an','   DP-test tab reads metadata and isolated test records only. Refresh and\n *   running-submission polling are read-only, and only an')
replace('      inflight: false,\n      seq: 0,','      inflight: false,\n      operations: [],\n      detail: null,\n      pollTimer: null,\n      pollEpoch: 0,\n      seq: 0,')
replace('  function flagsText(names) {','''  function operationFeedback(label, status) {
    setPgStatus(label + "：" + status);
    pg().operations.unshift({label: label, status: status, time: new Date().toLocaleTimeString()});
    pg().operations = pg().operations.slice(0, 20);
    const holder = pgOut("pg-operation-rows");
    if (holder) holder.replaceChildren();
    pg().operations.forEach(function (row) {
      if (holder) holder.appendChild(el("li", {text: row.time + " · " + row.label + " · " + row.status + "（本页反馈，非生产记录）"}));
    });
  }

  function renderLocalTest(label, status, book, preview) {
    renderSubmissionDetail({dp: pg().selected, local_operation: label, local_status: status,
      local_material: book && book.state, request_preview: preview || null,
      observe_only: true, zero_call: true, attempts: []});
  }

  function stopSubmissionPoll() {
    pg().pollEpoch += 1;
    if (pg().pollTimer !== null) clearTimeout(pg().pollTimer);
    pg().pollTimer = null;
  }

  function startSubmissionPoll(submitId) {
    stopSubmissionPoll();
    const epoch = pg().pollEpoch;
    const schedule = function () {
      if (epoch !== pg().pollEpoch) return;
      pg().pollTimer = setTimeout(async function () {
        pg().pollTimer = null;
        try {
          await refreshTestHistory();
          const payload = await getJson("/api/test/submissions/" + encodeURIComponent(submitId));
          if (epoch !== pg().pollEpoch) return;
          const row = payload.data || {};
          renderSubmissionDetail(row);
          setPgStatus("观察提交：" + missing(row.state) + "（每 1 秒只读刷新）");
          if (row.state && row.state !== "running") {
            stopSubmissionPoll();
            return;
          }
        } catch (error) {
          if (epoch !== pg().pollEpoch) return;
          setPgStatus("观察提交进行中：状态读取失败，稍后重读；未重发提交。");
          showError(error);
        }
        schedule();
      }, 1000);
    };
    schedule();
  }

  function flagsText(names) {''')
replace('    } else if (source.id === "request") {\n      renderCaptureAttempts(holder, detail, "dag", "request");','''    } else if (source.id === "request" && detail.request_preview) {
      holder.appendChild(el("p", {class: "notes", text: "请求预览：未发送（0 模型调用），不是实际请求捕获。"}));
      holder.appendChild(el("pre", {class: "copy-text", text: JSON.stringify(detail.request_preview, null, 2)}));
    } else if (source.id === "request") {
      renderCaptureAttempts(holder, detail, "dag", "request");''')
replace('''    holder.replaceChildren();
    const row = record && typeof record === "object" ? record : {};
    holder.appendChild(el("h3", { text: "测试提交详情 · " + missing(row.submission_id) }));''','''    const previous = pgOut("pg-dag-node-detail");
    const selectedNode = previous && previous.getAttribute("data-node-id");
    holder.replaceChildren();
    const row = record && typeof record === "object" ? record : {};
    pg().detail = row;
    holder.appendChild(el("h3", { text: row.local_operation
      ? "本页测试 DAG · " + row.local_operation + " · " + row.local_status + "（非后端决策记录）"
      : "测试提交详情 · " + missing(row.submission_id) }));''')
replace('    renderDagGraph(dagHolder, submissionDagNodes(row), "pg-dag-node", "pg-dag-node-detail");','''    const nodes = submissionDagNodes(row);
    renderDagGraph(dagHolder, nodes, "pg-dag-node", "pg-dag-node-detail");
    const selected = nodes.filter(function (node) { return node.id === selectedNode; })[0];
    if (selected) renderNodeDetail("pg-dag-node-detail", selected, {nodes: nodes});''')
replace('    close.addEventListener("click", function () { holder.replaceChildren(); });','    close.addEventListener("click", function () { pg().detail = null; holder.replaceChildren(); });')
replace('    let material = null;\n    captured.forEach','    let material = row.local_operation ? row.local_material || null : null;\n    captured.forEach')
replace('      request: { attempts: captured },','      request: { attempts: captured, request_preview: row.request_preview || null },')
replace('      renderTestHistory(history.data && typeof history.data === "object" ? history.data : {});\n      setPgStatus','''      renderTestHistory(history.data && typeof history.data === "object" ? history.data : {});
      if (!pg().inflight) {
        if (pg().detail && !pg().detail.local_operation && pg().detail.submission_id) {
          await openSubmission(pg().detail.submission_id);
        } else if (!pg().detail) {
          const records = pg().history && pg().history.records || [];
          if (records.length) await openSubmission(records[records.length - 1].submission_id);
          else renderLocalTest("尚未发起测试", "未调用模型", null, null);
        }
      }
      setPgStatus''')
replace('    setPgStatus("正在生成决策本骨架（注册表只读，不发模型请求）…");','''    operationFeedback("生成骨架", "进行中（不发模型请求）");
    renderLocalTest("生成骨架", "进行中", null, null);''')
replace('      setPgStatus("已生成 " + dp + " 的骨架：占位符必须替换后再校验；生成过程未发模型请求。");','''      operationFeedback("生成骨架", "已生成 " + dp + "；占位符须替换，未调用模型");
      renderLocalTest("生成骨架", "完成，未调用模型", data.book, null);''')
replace('      setPgStatus("骨架生成失败：未伪造决策本。");','''      operationFeedback("生成骨架", "失败，未调用模型");
      renderLocalTest("生成骨架", "失败", null, null);''')
replace('''    const body = { dp: dp, book: book };
    if (gathered.questions) body.questions = gathered.questions;
    try {
      const payload = await postJsonPage("/api/test/validate", body);
      renderValidateResult(payload.data && typeof payload.data === "object" ? payload.data : {});''','''    const body = { dp: dp, book: book };
    if (gathered.questions) body.questions = gathered.questions;
    operationFeedback("校验并预览", "进行中（不调用模型）");
    renderLocalTest("校验并预览", "进行中", book, null);
    try {
      const payload = await postJsonPage("/api/test/validate", body);
      const report = payload.data && typeof payload.data === "object" ? payload.data : {};
      renderValidateResult(report);
      operationFeedback("校验并预览", report.ok === true ? "通过，未调用模型" : "拒绝，未调用模型");
      renderLocalTest("校验并预览", report.ok === true ? "通过" : "拒绝", book, report.request_preview);''')
replace('      pgAppend("pg-validate-out", el("p", { class: "error", text: "校验请求失败："','''      operationFeedback("校验并预览", "失败，未调用模型");
      renderLocalTest("校验并预览", "失败", book, null);
      pgAppend("pg-validate-out", el("p", { class: "error", text: "校验请求失败："''')
replace('''    clearError();
    try {
      const body = { dp: dp, book: book, submit_id: submitId, observe_only: true };''','''    clearError();
    operationFeedback(retryOf ? "新 id 重试" : "观察提交", "进行中；每 1 秒只读刷新，未自动重发");
    renderSubmissionDetail({submission_id: submitId, dp: dp, state: "running", retry_of: retryOf, observe_only: true, attempts: []});
    startSubmissionPoll(submitId);
    try {
      const body = { dp: dp, book: book, submit_id: submitId, observe_only: true };''')
replace('''      renderSubmitResult(payload.data && typeof payload.data === "object" ? payload.data : {}, 200, null);
      await refreshTestHistory();''','''      const row = payload.data && typeof payload.data === "object" ? payload.data : {};
      renderSubmitResult(row, 200, null);
      stopSubmissionPoll();
      operationFeedback(retryOf ? "新 id 重试" : "观察提交", missing(row.state) + (row.duplicate ? "（重复 id，未新增调用）" : ""));
      renderSubmissionDetail(row);
      await refreshTestHistory();
      await openSubmission(submitId);''')
replace('''    } catch (error) {
      if (error && error.code === "busy" && error.data) {''','''    } catch (error) {
      operationFeedback(retryOf ? "新 id 重试" : "观察提交", "失败/拒绝；未自动重试");
      if (error && error.data) renderSubmissionDetail(error.data);
      if (error && error.code === "busy" && error.data) {''')
replace('    } finally {\n      pg().inflight = false;','    } finally {\n      stopSubmissionPoll();\n      pg().inflight = false;')
replace('''    pgClear("pg-validate-out");
    pgClear("pg-submit-out");
    if (pg().materialInvalid) {''','''    pgClear("pg-validate-out");
    pgClear("pg-submit-out");
    if (pg().materialInvalid) {
      operationFeedback("测试材料", "拒绝：业务 JSON 无效，未发起请求");
      renderLocalTest("测试材料", "拒绝", null, null);''')
replace('''    if (!text.trim()) {
      pgAppend("pg-validate-out",''','''    if (!text.trim()) {
      operationFeedback("测试材料", "拒绝：决策本为空，未发起请求");
      renderLocalTest("测试材料", "拒绝", null, null);
      pgAppend("pg-validate-out",''')
replace('      pgAppend("pg-validate-out", el("p", { class: "error", text: "决策本不是合法 JSON：未发起任何请求。" }));','''      operationFeedback("测试材料", "拒绝：决策本 JSON 无效，未发起请求");
      renderLocalTest("测试材料", "拒绝", null, null);
      pgAppend("pg-validate-out", el("p", { class: "error", text: "决策本不是合法 JSON：未发起任何请求。" }));''')
replace('''    if (!historySelected && !pg().loaded) {
      // Switching tabs reads nothing: the DP registry and the isolated test
      // records are loaded by an explicit click (metadata + records only).
      setPgStatus("尚未加载 DP 契约：点击“加载”只读取注册表与独立测试记录，不校验、不发现凭证、不发模型请求。");
    }''','''    if (!historySelected) {
      closeDetail();
      loadPlayground();
    }''')
replace('''    const pgRefresh = document.getElementById("pg-refresh-history");
    if (pgRefresh) pgRefresh.addEventListener("click", refreshTestHistory);''','''    const refreshCurrent = function () {
      const tab = document.getElementById("tab-playground");
      if (tab && tab.getAttribute("aria-selected") === "true") loadPlayground();
      else loadHistory(state.offset);
    };
    const refresh = document.getElementById("dashboard-refresh");
    if (refresh) refresh.addEventListener("click", refreshCurrent);
    const pgRefresh = document.getElementById("pg-refresh-history");
    if (pgRefresh) pgRefresh.addEventListener("click", loadPlayground);''')
p.write_text(s,encoding='utf-8',newline='\n')

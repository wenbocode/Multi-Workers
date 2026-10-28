from pathlib import Path
p=Path(__file__).resolve().parents[3]/'packages/multi-workers/decision_dashboard.js'
s=p.read_text(encoding='utf-8')
a=s.index('  function renderSubmitResult(');b=s.index('  function validationGuidance(',a)
s=s[:a]+'''  function submissionFeedback(record) {
    const outcome = record.outcome && typeof record.outcome === "object" ? record.outcome : {};
    const response = outcome.response && typeof outcome.response === "object" ? outcome.response : {};
    if (record.busy === true) return {kind: "warn", text: "已有观察提交进行中：本次未排队、未发起模型调用。请等待当前提交结束。"};
    if (record.duplicate === true) return {kind: "warn", text: "重复提交：未新增调用，不是一次新的成功。请查看原提交结果；如需重新调用，请显式点击重试。"};
    if (record.state === "succeeded" && record.record_status === "recorded") return {kind: "ok", text: "观察调用成功，结果已记录"};
    if (outcome.escalated_reason === "low-confidence") {
      // Only the decision's recorded policy detail supplies these numbers.
      // Never substitute the current config threshold or guess a missing value.
      const numbers = typeof outcome.detail === "string"
        ? /confidence=([0-9]+(?:\\.[0-9]+)?)\\s*<\\s*min_confidence=([0-9]+(?:\\.[0-9]+)?)/.exec(outcome.detail) : null;
      const explanation = numbers
        ? "置信度 " + numbers[1] + "，低于本次阈值 " + numbers[2] + "。"
        : "本次置信度或阈值未记录，不按当前配置推断。";
      return {kind: "warn", text: "模型已返回，结果未采纳：" + explanation + "请人工判断；未自动重试。"};
    }
    if (record.state === "rejected" || record.accepted === false) return {kind: "error", text: "提交被拒绝：请按下方问题修正材料后重新校验；未自动重试。"};
    if (outcome.status === "unavailable" || response.available === false) return {kind: "error", text: "决策服务不可用：请检查服务配置与连接，未自动重试；具体原因可在详情中查看。"};
    if (outcome.status === "escalated" || outcome.status === "not-adopted") return {kind: "warn", text: "结果未采纳，需要人工判断。请在详情查看本次策略原因；未自动重试。"};
    if (record.state === "running") return {kind: "warn", text: "观察提交仍在进行，请等待结果；未自动重试。"};
    if (!record.state || record.state === "unknown") return {kind: "error", text: "提交响应不可读，调用是否完成未知。请先查看测试记录确认结果；未自动重试。"};
    if (record.state === "succeeded") return {kind: "warn", text: "调用返回，但结果记录未确认。请检查测试记录与详情；未自动重试。"};
    return {kind: "error", text: "观察提交未成功。请查看下方问题与详情确认原因；未自动重试。"};
  }

  function renderSubmitResult(data, httpStatus, error) {
    pgClear("pg-submit-out");
    const record = data && typeof data === "object" ? data : {};
    const feedback = submissionFeedback(record);
    pgAppend("pg-submit-out", el("p", {class: "status " + feedback.kind, "data-testid": "pg-submit-headline", text: feedback.text}));
    pgAppend("pg-submit-out", el("p", {class: "notes", text: "仅观察：未执行任何业务动作；答案与请求/返回可在测试 DAG 和按需展开的技术详情中查看。"}));
    (Array.isArray(record.issues) ? record.issues : []).forEach(function (issue) {
      const structured = issue && typeof issue === "object";
      const text = structured
        ? missing(issue.path) + "：" + formatFree(issue.detail) + " · " + validationGuidance(issue).text
        : String(issue);
      pgAppend("pg-submit-out", el("p", {class: "error", text: "问题提示：" + text}));
    });
    if (record.message) pgAppend("pg-submit-out", el("p", {class: "warn", text: String(record.message)}));
    if (error && error.code && record.state && record.state !== "unknown" && record.busy !== true) {
      pgAppend("pg-submit-out", el("p", {class: "error", text: "错误原因：" + String(error.code) + "；请在详情中核对，未自动重试。"}));
    }
  }

  function renderBusy(data, error) {
    renderSubmitResult(Object.assign({}, data || {}, {busy: true}), 0, error);
  }

  function renderSubmitFailure(error) {
    renderSubmitResult({state: "unknown"}, 0, error);
  }

'''+s[b:]
s=s.replace('setText("pg-submit-id", "submission id=" + submitId + (retryOf ? " · retry_of=" + retryOf : " (新 id)"));','setText("pg-submit-id", retryOf ? "本次为显式重试（使用新提交编号）" : "本次为新的观察提交");')
s=s.replace('missing(row.state) + (row.duplicate ? "（重复 id，未新增调用）" : "")','submissionFeedback(row).text')
p.write_text(s,encoding='utf-8',newline='')

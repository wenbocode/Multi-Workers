from pathlib import Path
p=Path(__file__).resolve().parents[3]/'packages/multi-workers/decision_dashboard.js'
s=p.read_text(encoding='utf-8')
a=s.index('  function renderFiltersNotes(data) {');b=s.index('  function renderFacetOptions(data) {',a)
s=s[:a]+'''  function renderFiltersNotes(data) {
    const warnings = data && Array.isArray(data.warnings) ? data.warnings : [];
    const withheld = data && Array.isArray(data.filters_withheld) ? data.filters_withheld : [];
    setText("history-safety", withheld.length || warnings.some(function (warning) {
      return String(warning).indexOf("withheld") !== -1;
    }) ? "部分详情因安全限制未显示" : "");
  }

'''+s[b:]
a=s.index('    if (keys && dps) {');b=s.index('\n  function renderSelectOptions',a)
s=s[:a]+'  }\n'+s[b:]
s=s.replace('    limit: 50,','    limit: 5,',1).replace('    renderHistoryStats(data);','')
s=s.replace('''      "共 " + missing(data && data.total) +
        " 条 · 本页 " + String(records.length) + " 条 · offset " +
        missing(data && data.offset) +
        " · limit " + missing(data && data.limit)''','''      "共 " + missing(data && data.total) + " 条 · 本页 " + String(records.length) + " 条"''')
s=s.replace('''      pg().caseQuestions = null;
      renderQuestionsEditor();
      setPgStatus("已生成''','''      syncMaterialEditor();
      pg().caseQuestions = data.questions && typeof data.questions === "object" ? cloneJson(data.questions) : null;
      renderQuestionsEditor();
      setPgStatus("已生成''')
s=s.replace('''      } else if (!isMissing(question.criteria)) {''','''      } else if (!isMissing(question.criteria) || question.labels) {''')
s=s.replace('''            : JSON.stringify(question.criteria, null, 2);''','''            : JSON.stringify(question.criteria || question.labels, null, 2);''')
s=s.replace('''    pg().caseLoaded = found;
''','''    syncMaterialEditor();
    pg().caseLoaded = found;
''')
a=s.index('  function readBook() {')
s=s[:a]+'''  function syncMaterialEditor() {
    const material = document.getElementById("material-editor");
    const value = editorState();
    if (material) material.value = value ? JSON.stringify(value, null, 2) : "";
  }

  function updateBookMaterial() {
    const editor = document.getElementById("book-editor");
    const material = document.getElementById("material-editor");
    if (!editor || !material) return;
    const book = parseJson(editor.value);
    const value = parseJson(material.value);
    if (!book.ok || !value.ok || !value.value || typeof value.value !== "object" || Array.isArray(value.value)) {
      pgClear("pg-validate-out");
      pgAppend("pg-validate-out", el("p", {class: "error", text: "业务材料必须是合法 JSON 对象：未发起请求。"}));
      return;
    }
    book.value.state = value.value;
    editor.value = JSON.stringify(book.value, null, 2);
    refreshDerivedCriteria();
  }

'''+s[a:]
s=s.replace('''  function init() {
''','''  function init() {
    setText("monitor-port", "端口：" + (location.port || "未记录"));
    const materialEditor = document.getElementById("material-editor");
    if (materialEditor) materialEditor.addEventListener("input", updateBookMaterial);
    const advancedEditor = document.getElementById("book-editor");
    if (advancedEditor) advancedEditor.addEventListener("input", function () {
      syncMaterialEditor();
      refreshDerivedCriteria();
    });
''')
p.write_text(s,encoding='utf-8',newline='\n')

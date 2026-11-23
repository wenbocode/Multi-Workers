(() => {
  const host = document.getElementById("receipt-explorer");
  const data = JSON.parse(document.getElementById("receipt-data").textContent);
  const create = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const style = create("style");
  style.textContent = `
    #receipt-explorer { margin: 1.2rem 0 1.8rem; }
    .receipt-filters, .receipt-charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 195px), 1fr)); gap: .8rem; }
    .receipt-filters label { display: flex; flex-direction: column; gap: .25rem; font-size: .86rem; font-weight: 600; }
    .receipt-filters input, .receipt-filters select { padding: .5rem .65rem; border: 1px solid #9badb8; border-radius: .45rem; min-width: 0; font: inherit; background: #fff; color: #112c41; }
    .receipt-charts > section { min-width: 0; padding: .85rem; border: 1px solid #c5d1d9; border-radius: .65rem; background: #f5f9fb; }
    .receipt-charts h3 { margin: 0 0 .6rem; font-size: 1rem; }
    .receipt-bar { display: grid; grid-template-columns: minmax(0, 1fr) 3ch; gap: .2rem .55rem; width: 100%; border: 0; padding: .3rem .25rem; background: transparent; text-align: left; color: #112c41; cursor: pointer; }
    .receipt-bar:hover, .receipt-bar[aria-pressed="true"] { background: #dcecf3; border-radius: .25rem; }
    .receipt-bar span { overflow-wrap: anywhere; font-size: .79rem; }
    .receipt-bar b { font-size: .82rem; text-align: right; font-variant-numeric: tabular-nums; }
    .receipt-bar i { grid-column: span 2; height: 4px; border-radius: 10px; background: #dee8ed; }
    .receipt-bar i::before { display: block; content: ""; width: var(--width); height: 100%; background: #137c8e; border-radius: 10px; }
    .receipt-results { margin-top: 1.2rem; }
    .receipt-results details { border-bottom: 1px solid #d2dee6; padding: .7rem .2rem; overflow-wrap: anywhere; scroll-margin-top: 5rem; }
    .receipt-results summary { cursor: pointer; font-size: .9rem; font-weight: 600; }
    .receipt-results p { margin: .25rem 0; font-size: .84rem; line-height: 1.55; }
    .receipt-results pre { white-space: pre-wrap; }
    .receipt-results details[hidden] { display: none; }
    .receipt-count { margin: .85rem 0; font-weight: 650; }
    .receipt-reset { width: fit-content; padding: .4rem .7rem; }
    @media print { .receipt-results { display: none; } }
  `;
  document.head.append(style);
  const filters = create("div", "", "receipt-filters");
  const chart = create("div", "", "receipt-charts");
  const count = create("p", "", "receipt-count");
  count.setAttribute("aria-live", "polite");
  const list = create("div", "", "receipt-results");
  const controls = {};
  const facets = [
    ["project", "按项目", data.projects],
    ["dp", "按 DP", data.dps],
    ["reason", "按合并原因", data.reasons],
  ];
  for (const [field, caption, options] of facets) {
    const label = create("label", caption);
    const select = create("select");
    for (const value of ["", ...options]) {
      const option = create("option", value || "全部");
      option.value = value;
      select.append(option);
    }
    select.addEventListener("change", update);
    controls[field] = select;
    label.append(select);
    filters.append(label);
  }
  const search = create("input");
  search.type = "search";
  search.placeholder = "事件 ID、key、诊断";
  search.addEventListener("input", update);
  const label = create("label", "搜索");
  label.append(search);
  filters.append(label);
  const diagnosticLabel = create("label", "文件诊断");
  const diagnostic = create("select");
  for (const value of ["", ...new Set(data.rows.flatMap((row) => row.diagnostics))]) {
    const option = create("option", value || "全部");
    option.value = value;
    diagnostic.append(option);
  }
  diagnostic.addEventListener("change", update);
  diagnosticLabel.append(diagnostic);
  filters.append(diagnosticLabel);
  const reset = create("button", "清除筛选", "receipt-reset");
  reset.type = "button";
  reset.addEventListener("click", () => clearFilters());
  host.append(filters, count, chart, reset, list);

  const entries = data.rows.slice().reverse().map((row) => {
    const panel = create("details");
    panel.id = "event-" + row.id;
    const timestamp = new Date(row.ts).toLocaleString("zh-CN", {
      timeZone: "Asia/Shanghai", hour12: false,
    });
    panel.append(
      create("summary", [row.project, row.dp, row.reason, timestamp].join(" · ")),
      create("p", row.id),
      create("p", [row.key, row.stage, row.code, row.transport].filter(Boolean).join(" · ")),
    );
    for (const line of [row.detail, ...row.fields, ...new Set(row.diagnostics)]) {
      if (line) panel.append(create("p", line));
    }
    if (row.kind !== "recorded-block") panel.append(create("p", row.kind));
    const source = create("a", "查看原回执");
    source.href = "file:///" + row.file.split("/").map((piece, i) => i ? encodeURIComponent(piece) : piece).join("/");
    panel.append(source);
    list.append(panel);
    const searchText = Object.values(row).flat().join(" ").toLowerCase();
    return { row, panel, searchText };
  });
  function clearFilters() {
    for (const control of Object.values(controls)) control.value = "";
    search.value = "";
    diagnostic.value = "";
    update();
  }
  function update() {
    const term = search.value.trim().toLowerCase();
    const selected = entries.filter(({row, searchText, panel}) => {
      const visible = (!term || searchText.includes(term)) &&
        (!diagnostic.value || row.diagnostics.includes(diagnostic.value)) &&
        facets.every(([field]) => !controls[field].value || row[field] === controls[field].value);
      panel.hidden = !visible;
      return visible;
    });
    count.textContent = `${selected.length} / ${entries.length} 条回执`;
    chart.replaceChildren();
    for (const [field, caption, options] of facets) {
      const section = create("section");
      section.append(create("h3", caption));
      const volumes = new Map(options.map((option) => [option, 0]));
      for (const {row} of selected) volumes.set(row[field], volumes.get(row[field]) + 1);
      const max = Math.max(1, ...volumes.values());
      for (const [value, volume] of volumes) {
        const bar = create("button", "", "receipt-bar");
        bar.type = "button";
        bar.setAttribute("aria-pressed", String(controls[field].value === value));
        bar.style.setProperty("--width", Math.round(volume / max * 100) + "%");
        bar.append(create("span", value), create("b", String(volume)), create("i"));
        bar.addEventListener("click", () => {
          controls[field].value = controls[field].value === value ? "" : value;
          update();
          controls[field].focus();
        });
        section.append(bar);
      }
      chart.append(section);
    }
  }
  function reveal(hash) {
    if (!hash.startsWith("#event-")) return;
    const entry = entries.find(({panel}) => "#" + panel.id === hash);
    if (!entry) return;
    clearFilters();
    entry.panel.open = true;
  }
  document.addEventListener("click", (event) => {
    const link = event.target.closest('a[href^="#event-"]');
    if (link) reveal(link.hash);
  }, true);
  window.addEventListener("hashchange", () => reveal(location.hash), true);
  update();
  if (location.hash.startsWith("#event-")) {
    reveal(location.hash);
    window.dispatchEvent(new Event("hashchange"));
  }
})();

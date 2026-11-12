/* Model Lab frontend. It depends only on the /ui HTTP contract. */
(function () {
  "use strict";

  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));
  const state = {
    page: "overview",
    apiBase: localStorage.getItem("model-lab-api") || "",
    connected: false,
    model: "Muse Spark 1.3",
    modelSettings: null,
    reasoningEffort: "auto",
    categories: [],
    levels: [],
    tests: [],
    runs: [],
    currentRun: null,
    currentRunEvents: [],
    activeStream: null,
    chatController: null,
    conversationId: null,
    selectedTest: null,
    chatMode: "free",
    messages: [],
    tools: [],
    conversations: [],
    metrics: [],
    traces: [],
    settings: null,
    runFilters: {status:"",category:"",test_id:"",passed:""},
    compareIds: new Set(),
    refreshTimer: null,
    requestQueue: Promise.resolve(),
    streamQueue: Promise.resolve()
  };

  const labels = {
    overview:"Overview", builder:"Test Builder", runs:"Test Runs",
    agent:"Harness Agent", conversations:"Conversations", tools:"Tools",
    metrics:"Metrics", traces:"Traces & Logs", settings:"Settings"
  };

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, ch => ({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
    })[ch]);
  }
  function pretty(value) {
    try { return JSON.stringify(value, null, 2); } catch (_) { return String(value); }
  }
  function base() {
    return state.apiBase.replace(/\/+$/, "");
  }
  function url(path) {
    return base() + path;
  }
  function withQueueSlot(queueName, task) {
    const queued = state[queueName].then(task, task);
    state[queueName] = queued.then(() => undefined, () => undefined);
    return queued;
  }
  function withRequestSlot(task) {
    return withQueueSlot("requestQueue", task);
  }
  function withStreamSlot(task) {
    return withQueueSlot("streamQueue", task);
  }
  async function api(path, options) {
    if (!base()) throw new Error("Add your Deplexo backend URL in Settings first.");
    const config = Object.assign({method:"GET",headers:{}}, options || {});
    if (config.body && typeof config.body !== "string") {
      config.headers["Content-Type"] = "application/json";
      config.body = JSON.stringify(config.body);
    }
    return withRequestSlot(async () => {
      const response = await fetch(url(path), config);
      const type = response.headers.get("content-type") || "";
      let payload;
      if (type.includes("application/json")) payload = await response.json();
      else payload = await response.text();
      if (!response.ok) {
        const message = payload && payload.detail ? payload.detail :
          payload && payload.error && payload.error.message ? payload.error.message :
          (typeof payload === "string" ? payload : "Request failed (" + response.status + ")");
        throw new Error(message);
      }
      return payload;
    });
  }
  function toast(message, isError) {
    const node = document.createElement("div");
    node.className = "toast" + (isError ? " error" : "");
    node.textContent = message;
    $("#toast-region").appendChild(node);
    setTimeout(() => node.remove(), 4200);
  }
  function statusBadge(status, passed) {
    if (passed === true) return '<span class="badge pass">Passed</span>';
    if (passed === false) return '<span class="badge fail">Failed</span>';
    const value = String(status || "unknown").toLowerCase();
    return '<span class="badge ' + esc(value) + '">' + esc(value) + '</span>';
  }
  function statCard(title, value, foot, icon) {
    return '<div class="stat-card"><div class="stat-top"><span>' + esc(title) +
      '</span><span class="stat-icon">' + esc(icon) + '</span></div><div class="stat-value">' +
      esc(value) + '</div><div class="stat-foot">' + esc(foot || "") + '</div></div>';
  }
  function heading(title, description, actions) {
    return '<div class="page-heading"><div><div class="eyebrow">MODEL LAB / WORKSPACE</div><h1>' +
      esc(title) + '</h1><p class="page-description">' + esc(description) +
      '</p></div><div class="heading-actions">' + (actions || "") + '</div></div>';
  }
  function panel(title, subtitle, content, action) {
    return '<section class="panel"><div class="panel-header"><div><div class="panel-title">' +
      esc(title) + '</div>' + (subtitle ? '<div class="panel-subtitle">' + esc(subtitle) + '</div>' : '') +
      '</div>' + (action || '') + '</div>' + content + '</section>';
  }
  function empty(title, message, icon) {
    return '<div class="empty-state"><div class="empty-icon">' + esc(icon || "◌") +
      '</div><strong>' + esc(title) + '</strong><div style="margin-top:4px">' +
      esc(message) + '</div></div>';
  }
  function field(label, name, value, type) {
    return '<div class="field"><label for="' + esc(name) + '">' + esc(label) + '</label>' +
      '<input class="input" id="' + esc(name) + '" name="' + esc(name) + '" type="' +
      esc(type || "text") + '" value="' + esc(value) + '"></div>';
  }
  function selectField(label, name, options, selected) {
    return '<div class="field"><label for="' + esc(name) + '">' + esc(label) + '</label><select class="select" id="' +
      esc(name) + '" name="' + esc(name) + '">' + options.map(o =>
        '<option value="' + esc(o.value) + '"' + (String(o.value) === String(selected) ? " selected" : "") +
        '>' + esc(o.label) + '</option>').join("") + '</select></div>';
  }
  function textareaField(label, name, value, rows, hint) {
    return '<div class="field full"><label for="' + esc(name) + '">' + esc(label) + '</label>' +
      '<textarea class="textarea" id="' + esc(name) + '" name="' + esc(name) + '" rows="' +
      (rows || 4) + '">' + esc(value) + '</textarea>' +
      (hint ? '<div class="hint">' + esc(hint) + '</div>' : '') + '</div>';
  }
  function formatTime(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? esc(value) : date.toLocaleString();
  }
  function formatDuration(value) {
    if (value == null) return "—";
    return Number(value) < 1000 ? Math.round(Number(value)) + " ms" :
      (Number(value) / 1000).toFixed(2) + " s";
  }
  function setConnected(yes, detail) {
    state.connected = yes;
    const dot = $("#sidebar-status");
    if (dot) dot.classList.toggle("online", yes);
    $("#connection-label").textContent = yes ? "Backend connected" : "Not connected";
    $("#connection-sub").textContent = detail || (yes ? state.model : "Set API URL in Settings");
    $("#top-model").textContent = state.model;
  }
  function navigate(page) {
    if (!labels[page]) return;
    state.page = page;
    $$(".nav-item[data-page]").forEach(button => button.classList.toggle("active", button.dataset.page === page));
    $("#page-breadcrumb").textContent = labels[page];
    $("#sidebar").classList.remove("open");
    renderPage();
  }
  function renderPage() {
    const content = $("#page-content");
    content.innerHTML = '<div class="loading-state"><span class="spinner"></span>Loading…</div>';
    const renderers = {
      overview:renderOverview,builder:renderBuilder,runs:renderRuns,agent:renderAgent,
      conversations:renderConversations,tools:renderTools,metrics:renderMetrics,
      traces:renderTraces,settings:renderSettings
    };
    Promise.resolve(renderers[state.page]()).catch(error => {
      content.innerHTML = heading(labels[state.page], "Unable to load this workspace section.") +
        panel("Request error", "", '<div class="empty-state">' + esc(error.message) + '</div>');
      toast(error.message, true);
    });
  }
  async function getDashboard() {
    try {
      const result = await api("/ui/dashboard");
      state.model = result.model || state.model;
      setConnected(true, state.model);
      return result;
    } catch (error) {
      setConnected(false, "Check API URL and CORS");
      throw error;
    }
  }
  async function renderOverview() {
    const content = $("#page-content");
    const results = await Promise.all([getDashboard(),api("/ui/system"),api("/ui/metrics?limit=500")]);
    const data = results[0], system = results[1], metricsData = results[2];
    const runs = data.recent_runs || [];
    const passed = data.runs_passed == null ? "—" : data.runs_passed;
    const rate = data.pass_rate == null ? "—" : Math.round(data.pass_rate * 100) + "%";
    const active = data.active_runs || [];
    const rows = runs.length ? '<div class="table-wrap"><table><thead><tr><th>TEST</th><th>STATUS</th><th>RESULT</th><th>LATENCY</th><th>CREATED</th><th></th></tr></thead><tbody>' +
      runs.map(run => '<tr><td><strong>' + esc(run.test_name || run.test_id) + '</strong><div class="muted">' +
        esc(run.category || "") + ' · ' + esc(run.difficulty || "") + '</div></td><td>' +
        statusBadge(run.status) + '</td><td>' + statusBadge(run.status, run.passed) +
        '</td><td>' + formatDuration(run.latency_ms) + '</td><td>' + formatTime(run.created_at) +
        '</td><td><button class="btn small" data-action="view-run" data-id="' + esc(run.id) + '">Open</button></td></tr>').join("") +
      '</tbody></table></div>' : empty("No test runs yet","Choose a built-in scenario in Test Builder and run it.","▷");
    const activity = active.length ? '<div class="activity-list">' + active.map(run =>
      '<div class="activity-item"><span class="activity-marker"></span><div><div class="activity-text">' +
      esc(run.test_name || run.test_id) + '</div><div class="activity-meta">' + esc(run.status) +
      ' · ' + esc(run.id) + '</div></div><span style="margin-left:auto">' + statusBadge(run.status) +
      '</span></div>').join("") + '</div>' : empty("No active runs","Live execution activity will appear here.","◉");
    const ram = system.memory_rss_mb == null ? "—" : system.memory_rss_mb + " MB";
    const cpuLoad = system.load_average && system.load_average.length ? Number(system.load_average[0]).toFixed(2) + " / " + (system.cpu_count || "—") + " cores" : "—";
    const metricRows = metricsData.metrics || [];
    const latencyValues = metricRows.filter(x=>x.metric==="latency_ms").map(x=>Number(x.value)).filter(Number.isFinite);
    const averageLatency = latencyValues.length ? formatDuration(latencyValues.reduce((a,b)=>a+b,0)/latencyValues.length) : "—";
    const tokenTotal = metricRows.filter(x=>x.metric==="total_tokens").reduce((sum,x)=>sum+Number(x.value||0),0);
    content.innerHTML = heading("Overview","Your model testing workspace at a glance.",
      '<button class="btn" data-action="refresh">↻ Refresh</button><button class="btn primary" data-page="builder">＋ New test</button>') +
      '<div class="grid stats-grid">' +
      statCard("Total runs",data.runs_total || 0,"Recent run history","▷") +
      statCard("Pass rate",rate,(data.runs_completed || 0) + " completed runs","✓") +
      statCard("Average latency",averageLatency,"Recent response samples","◷") +
      statCard("Token usage",tokenTotal || "—","Recorded model tokens","▤") +
      statCard("Built-in tests",data.built_in_tests || 0,"Across 11 capability categories","✳") +
      statCard("Memory usage",ram,"Current backend RSS snapshot","▦") +
      statCard("CPU load",cpuLoad,"1-minute load average / CPU cores","⌁") +
      statCard("Backend",system.status || "—","Runtime status","●") + '</div>' +
      '<div class="grid two-col">' +
      panel("Recent test runs","Latest saved executions",rows,'<button class="text-link" data-page="runs">View all →</button>') +
      panel("Live activity","Currently executing tests",activity,'<span class="badge info">' + active.length + ' active</span>') +
      '</div><div class="grid two-col">' +
      panel("Model connection","Provider status",'<div class="info-row"><span>Model</span><strong>' + esc(data.model) +
        '</strong></div><div class="info-row"><span>Provider</span><strong>' + (data.provider_configured ? '<span class="badge pass">Configured</span>' : '<span class="badge fail">Missing key</span>') +
        '</strong></div><div class="info-row"><span>Database</span><strong>' + (data.d1_configured ? '<span class="badge pass">Connected config</span>' : '<span class="badge">Memory fallback</span>') +
        '</strong></div>') +
      panel("Workspace shortcuts","Jump into a workflow",'<div class="activity-list">' +
        '<div class="activity-item"><span class="activity-marker"></span><div><button class="text-link" data-page="builder">Build a manual test →</button><div class="activity-meta">Create and save your own prompt and assertions.</div></div></div>' +
        '<div class="activity-item"><span class="activity-marker green"></span><div><button class="text-link" data-page="agent">Open Harness Agent →</button><div class="activity-meta">Chat with GLM and watch its tool usage live.</div></div></div>' +
        '<div class="activity-item"><span class="activity-marker"></span><div><button class="text-link" data-page="metrics">Inspect model metrics →</button><div class="activity-meta">Review latency and token usage.</div></div></div></div>') +
      '</div>';
  }

  async function loadModelSettings(force) {
    if (state.modelSettings && !force) return state.modelSettings;
    const result = await api("/ui/settings");
    state.modelSettings = result;
    state.model = result.model_name || result.model || state.model;
    state.reasoningEffort = result.reasoning_effort || "auto";
    const top = $("#top-model");
    if (top) top.textContent = state.model;
    return result;
  }
  function reasoningOptions(settings) {
    const options = [{value:"auto",label:"Meta default (" + (settings.meta_default_reasoning_effort || "model default") + ")"}];
    (settings.reasoning_efforts || []).forEach(value => options.push({value,label:value.toUpperCase()}));
    return options;
  }
  function difficultyLabel(test) {
    return test.difficulty_label || ({easy:"Easy",mid:"Mid",hard:"Hard",expert:"Expert",adversarial:"Adversarial"}[test.difficulty]) || test.difficulty || "Custom";
  }
  async function loadTestCatalog() {
    const [categories,tests] = await Promise.all([api("/ui/tests/categories"),api("/ui/tests")]);
    state.categories = categories.categories || [];
    state.levels = categories.levels || [];
    state.tests = tests.tests || [];
  }
  function testCard(test) {
    return '<article class="test-card"><div class="test-card-top"><span class="badge info">' +
      esc(test.category.replace(/_/g," ")) + '</span><span class="badge">' + esc(difficultyLabel(test)) +
      '</span></div><h3>' + esc(test.name) + '</h3><p>' + esc(test.description || test.user_prompt || "") +
      '</p><div class="tags">' + (test.is_builtin ? '<span class="tag">Built-in</span>' : '<span class="tag">Custom</span>') +
      (test.tool_names || []).map(name => '<span class="tag">' + esc(name) + '</span>').join("") +
      '</div><div class="heading-actions"><button class="btn small primary" data-action="run-test" data-id="' +
      esc(test.id) + '">▷ Run test</button><button class="btn small" data-action="inspect-test" data-id="' +
      esc(test.id) + '">Details</button>' + (!test.is_builtin ?
        '<button class="btn small" data-action="edit-test" data-id="' + esc(test.id) + '">Edit</button><button class="btn small danger" data-action="delete-test" data-id="' + esc(test.id) + '">Delete</button>' : '') +
      '</div></article>';
  }
  async function renderBuilder() {
    const content = $("#page-content");
    await Promise.all([loadTestCatalog(),loadModelSettings()]);
    const categoryOptions = [{value:"",label:"All categories"}].concat(state.categories.map(x=>({value:x.id,label:x.name})));
    const levelOptions = [{value:"",label:"All levels"}].concat(state.levels.map(x=>({value:x,label:({easy:"Easy",mid:"Mid",hard:"Hard",expert:"Expert",adversarial:"Adversarial"})[x] || x})));
    content.innerHTML = heading("Test Builder","Browse the preloaded test library or create your own custom test.",
      '<button class="btn primary" data-action="new-test">＋ Create custom test</button>') +
      '<div class="toolbar"><input class="input" id="test-search" placeholder="Search tests…" /><select class="select" id="test-category">' +
      categoryOptions.map(x=>'<option value="' + esc(x.value) + '">' + esc(x.label) + '</option>').join("") +
      '</select><select class="select" id="test-level">' + levelOptions.map(x=>'<option value="' + esc(x.value) + '">' +
      esc(x.label) + '</option>').join("") + '</select><span class="muted" id="test-count">' +
      state.tests.length + ' tests</span></div>' +
      '<div class="grid stats-grid">' + statCard("Built-in tests",state.tests.filter(x=>x.is_builtin).length,"Ready to run","✳") +
      statCard("Custom tests",state.tests.filter(x=>!x.is_builtin).length,"Created by you","＋") +
      statCard("Categories",state.categories.length,"Capability areas","▤") +
      statCard("Difficulty levels",state.levels.length,"Easy to adversarial","↗") + '</div>' +
      '<div class="test-list" id="test-list">' + state.tests.map(testCard).join("") + '</div>';
    $("#test-search").addEventListener("input",filterTests);
    $("#test-category").addEventListener("change",filterTests);
    $("#test-level").addEventListener("change",filterTests);
  }
  function filterTests() {
    const query = ($("#test-search").value || "").toLowerCase();
    const category = $("#test-category").value;
    const level = $("#test-level").value;
    const items = state.tests.filter(test =>
      (!category || test.category === category) &&
      (!level || test.difficulty === level) &&
      (!query || (test.name + " " + test.description + " " + test.category).toLowerCase().includes(query)));
    $("#test-list").innerHTML = items.map(testCard).join("") || empty("No matching tests","Try another search or filter.");
    $("#test-count").textContent = items.length + " tests";
  }
  function defaultAssertions(category) {
    const map = {
      json_output:[{type:"json_valid"}],
      instruction_following:[{type:"response_nonempty"}],
      reasoning:[{type:"response_nonempty"}],
      tool_calling:[{type:"response_nonempty"}],
      custom_prompts:[{type:"response_nonempty"}]
    };
    return map[category] || [{type:"response_nonempty"}];
  }
  function openTestEditor(test) {
    const editing = !!test;
    const data = test || {
      name:"",category:"reasoning",difficulty:"custom",description:"",
      system_prompt:"",user_prompt:"",expected_output:"",
      assertions:[{type:"response_nonempty"}],tags:[],parameters:{temperature:0.2,max_tokens:512}
    };
    const categoryOptions = state.categories.map(x=>({value:x.id,label:x.name}));
    const params = Object.assign({temperature:0.2,top_p:1,max_tokens:512,presence_penalty:0,frequency_penalty:0},data.parameters || {});
    const modal = '<div class="modal-backdrop" id="editor-backdrop"><div class="modal"><div class="modal-header"><div><div class="eyebrow">' +
      (editing ? "CUSTOM TEST" : "NEW CUSTOM TEST") + '</div><h2>' + (editing ? "Edit test" : "Create a test") +
      '</h2></div><button class="btn small" data-action="close-modal">✕</button></div>' +
      '<form id="test-editor" class="form-grid">' +
      field("Name","test-name",data.name) +
      selectField("Category","test-category-edit",categoryOptions,data.category) +
      field("Description","test-description",data.description) +
      field("Tags (comma separated)","test-tags",(data.tags || []).join(", ")) +
      textareaField("System prompt","test-system",data.system_prompt || "",3,"This is sent to the tested model, not the evaluator.") +
      textareaField("User prompt","test-prompt",data.user_prompt || "",5) +
      textareaField("Expected output / goal","test-expected",data.expected_output || "",3,"Private evaluation reference. It is never sent to the tested agent.") +
      textareaField("Assertions (JSON array)","test-assertions",pretty(data.assertions || defaultAssertions(data.category)),6,"Supported types: contains, exact, max_words, numbered_items, bullet_items, json_valid, json_keys, json_array_length, json_path_exists, tool_called, response_nonempty, headings_in_order, lines_word_range.") +
      '<div class="field"><label for="test-temperature">Temperature</label><input class="input" id="test-temperature" type="number" min="0" max="2" step="0.1" value="' + esc(params.temperature) + '"></div>' +
      '<div class="field"><label for="test-top-p">Top P</label><input class="input" id="test-top-p" type="number" min="0" max="1" step="0.05" value="' + esc(params.top_p == null ? 1 : params.top_p) + '"></div>' +
      '<div class="field"><label for="test-max-tokens">Maximum output tokens</label><input class="input" id="test-max-tokens" type="number" min="1" max="8192" value="' + esc(params.max_tokens) + '"></div>' +
      '<div class="field"><label for="test-presence">Presence penalty</label><input class="input" id="test-presence" type="number" min="-2" max="2" step="0.1" value="' + esc(params.presence_penalty || 0) + '"></div>' +
      '<div class="field"><label for="test-frequency">Frequency penalty</label><input class="input" id="test-frequency" type="number" min="-2" max="2" step="0.1" value="' + esc(params.frequency_penalty || 0) + '"></div>' +

      textareaField("Additional model parameters (JSON)","test-extra-params",pretty(Object.fromEntries(Object.entries(params).filter(([key])=>!["temperature","top_p","max_tokens","presence_penalty","frequency_penalty"].includes(key)))),4,"Optional provider-specific parameters, such as stop, response_format, seed, logit_bias, or user.") +
      '<div class="field full"><div class="info-row"><span>Tool assignment</span><strong>Automatic from test prompt unless explicitly supplied</strong></div><div class="hint">The model sees only ordinary tool definitions selected for this scenario. Evaluation rules stay hidden.</div></div>' +
      '<div class="field full"><div class="heading-actions"><button type="button" class="btn" data-action="close-modal">Cancel</button><button type="submit" class="btn primary">' +
      (editing ? "Save changes" : "Save custom test") + '</button></div></div></form></div></div>';
    $("#modal-root").innerHTML = modal;
    $("#test-category-edit").addEventListener("change",event => {
      const current = $("#test-assertions").value;
      if (!current.trim() || current.trim() === "[]") $("#test-assertions").value = pretty(defaultAssertions(event.target.value));
    });
    $("#test-editor").addEventListener("submit", async event => {
      event.preventDefault();
      let assertions;
      try { assertions = JSON.parse($("#test-assertions").value || "[]"); }
      catch (_) { toast("Assertions must be valid JSON.",true); return; }
      if (!Array.isArray(assertions)) { toast("Assertions must be a JSON array.",true); return; }
      let extraParameters;
      try { extraParameters = JSON.parse($("#test-extra-params").value || "{}"); }
      catch (_) { toast("Additional model parameters must be valid JSON.",true); return; }
      if (!extraParameters || Array.isArray(extraParameters) || typeof extraParameters !== "object") {
        toast("Additional model parameters must be a JSON object.",true); return;
      }
      const parameters = Object.assign({},extraParameters,{
        temperature:Number($("#test-temperature").value),
        top_p:Number($("#test-top-p").value),
        max_tokens:Number($("#test-max-tokens").value),
        presence_penalty:Number($("#test-presence").value),
        frequency_penalty:Number($("#test-frequency").value)
      });
      const body = {
        name:$("#test-name").value,
        category:$("#test-category-edit").value,
        description:$("#test-description").value,
        tags:$("#test-tags").value.split(",").map(x=>x.trim()).filter(Boolean),
        system_prompt:$("#test-system").value,
        user_prompt:$("#test-prompt").value,
        expected_output:$("#test-expected").value,
        assertions:assertions,
        judge_rubric:$("#test-expected").value,
        parameters:parameters,
        tool_names:[]
      };
      try {
        if (editing) await api("/ui/tests/" + encodeURIComponent(data.id),{method:"PUT",body:body});
        else await api("/ui/tests",{method:"POST",body:body});
        $("#modal-root").innerHTML = "";
        toast(editing ? "Custom test updated." : "Custom test saved.");
        await renderBuilder();
      } catch (error) { toast(error.message,true); }
    });
  }
  async function inspectTest(id) {
    try {
      const result = await api("/ui/tests/" + encodeURIComponent(id));
      state.selectedTest = result;
      const safeView = {
        name:result.name,category:result.category,difficulty:result.difficulty,
        description:result.description,user_prompt:result.user_prompt,
        expected_output:result.expected_output,assertions:result.assertions,
        tools:result.tool_names,parameters:result.parameters,
        evaluation_rubric:result.judge_rubric
      };
      $("#modal-root").innerHTML = '<div class="modal-backdrop"><div class="modal"><div class="modal-header"><h2>' +
        esc(result.name) + '</h2><button class="btn small" data-action="close-modal">✕</button></div>' +
        '<div class="code-note">Evaluation details are shown here for you, but are never included in the agent prompt.</div>' +
        '<pre class="result-block">' + esc(pretty(safeView)) + '</pre><div class="heading-actions" style="margin-top:14px">' +
        '<button class="btn primary" data-action="run-test" data-id="' + esc(id) + '">▷ Run this test</button>' +
        '</div></div></div>';
    } catch (error) { toast(error.message,true); }
  }

  async function previewRun(id) {
    try {
      const test=await api("/ui/tests/"+encodeURIComponent(id));
      state.pendingRunTest=test;
      const summary={
        name:test.name,category:test.category,difficulty:test.difficulty,
        description:test.description,user_prompt:test.user_prompt,
        tools:test.tool_names,parameters:test.parameters,
        expected_output:test.expected_output,
        assertions:test.assertions,
        judge_rubric:test.judge_rubric
      };
      $("#modal-root").innerHTML='<div class="modal-backdrop"><div class="modal"><div class="modal-header"><div><div class="eyebrow">EXECUTION PREVIEW</div><h2>'+esc(test.name)+'</h2></div><button class="btn small" data-action="close-modal">✕</button></div>'+
        '<div class="code-note">Review the exact task setup. Expected output and evaluation rules remain outside the tested model context.</div>'+
        '<div class="grid two-col" style="margin-top:12px"><div><div class="panel-title">Agent receives</div><pre class="result-block">'+esc(pretty({system_prompt:test.system_prompt,user_prompt:test.user_prompt,tools:test.tool_names,parameters:test.parameters}))+'</pre></div>'+
        '<div><div class="panel-title">Evaluator keeps private</div><pre class="result-block">'+esc(pretty({expected_output:test.expected_output,assertions:test.assertions,judge_rubric:test.judge_rubric}))+'</pre></div></div>'+

        '<div class="heading-actions" style="margin-top:15px"><button class="btn" data-action="close-modal">Back</button><button class="btn primary" data-action="confirm-run" data-id="'+esc(id)+'">Confirm and run →</button></div></div></div>';
    } catch(error){toast(error.message,true);}
  }

  async function startRun(id) {
    try {
      if (state.activeStream) state.activeStream.abort();
      const result = await api("/ui/runs",{method:"POST",body:{test_id:id}});
      const run = result.run;
      state.currentRun = run;
      state.currentRunEvents = [];
      state.page = "runs";
      await renderRuns();
      watchRun(run.id);
      toast("Test run started.");
    } catch (error) { toast(error.message,true); }
  }
  async function renderRuns() {
    const content = $("#page-content");
    const query = new URLSearchParams();
    if (state.runFilters.status) query.set("status",state.runFilters.status);
    if (state.runFilters.category) query.set("category",state.runFilters.category);
    if (state.runFilters.test_id) query.set("test_id",state.runFilters.test_id);
    if (state.runFilters.passed) query.set("passed",state.runFilters.passed);
    const [result,categories] = await Promise.all([api("/ui/runs?" + query.toString()),api("/ui/tests/categories")]);
    state.runs = result.runs || [];
    const options = [{value:"",label:"All categories"}].concat((categories.categories || []).map(x=>({value:x.id,label:x.name})));
    const rows = state.runs.length ? '<div class="table-wrap"><table><thead><tr><th><input type="checkbox" id="compare-all" aria-label="Select all"></th><th>TEST</th><th>STATUS</th><th>ASSERTIONS</th><th>JUDGE</th><th>LATENCY</th><th>CREATED</th><th></th></tr></thead><tbody>' +
      state.runs.map(run => '<tr><td><input type="checkbox" class="compare-check" data-id="' + esc(run.id) + '"' +
        (state.compareIds.has(run.id) ? " checked" : "") + '></td><td><strong>' + esc(run.test_name || run.test_id) +
        '</strong><div class="muted">' + esc(run.category || "") + ' · ' + esc(run.difficulty || "") +
        '</div></td><td>' + statusBadge(run.status) + ' ' + statusBadge(run.status,run.passed) +
        '</td><td>' + (run.assertions_passed == null ? "—" : run.assertions_passed + "/" + run.assertions_total) +
        '</td><td>' + (run.judge_score == null ? "—" : run.judge_score + "/100") +
        '</td><td>' + formatDuration(run.latency_ms) + '</td><td>' + formatTime(run.created_at) +
        '</td><td><button class="btn small" data-action="view-run" data-id="' + esc(run.id) + '">Open</button></td></tr>').join("") +
      '</tbody></table></div>' : empty("No runs found","Run an individual test from Test Builder.");
    content.innerHTML = heading("Test Runs","Inspect live executions, results, traces, and compare runs.",
      '<button class="btn" data-action="refresh">↻ Refresh</button><button class="btn primary" data-page="builder">＋ Select test</button>') +
      '<div class="toolbar"><select class="select" id="run-status"><option value="">All statuses</option>' +
      ["queued","running","completed","failed","cancelled"].map(x=>'<option value="' + x + '"' +
        (state.runFilters.status === x ? " selected" : "") + '>' + x + '</option>').join("") +
      '</select><select class="select" id="run-category">' + options.map(x=>'<option value="' + esc(x.value) + '"' +
        (state.runFilters.category === x.value ? " selected" : "") + '>' + esc(x.label) + '</option>').join("") +
      '</select><select class="select" id="run-passed"><option value="">Any result</option><option value="true" '+(state.runFilters.passed==="true"?"selected":"")+'>Passed</option><option value="false" '+(state.runFilters.passed==="false"?"selected":"")+'>Failed</option></select><button class="btn" data-action="compare-runs" ' + (state.compareIds.size < 2 ? "disabled" : "") +
      '>⇄ Compare (' + state.compareIds.size + ')</button></div>' +
      panel("Run history",state.runs.length + " records",rows) +
      (state.currentRun ? renderRunDetail(state.currentRun) : '');
    $("#run-status").addEventListener("change",e=>{state.runFilters.status=e.target.value;renderRuns();});
    $("#run-category").addEventListener("change",e=>{state.runFilters.category=e.target.value;renderRuns();});
    $("#run-passed").addEventListener("change",e=>{state.runFilters.passed=e.target.value;renderRuns();});
    $("#compare-all").addEventListener("change",e=>{
      if (e.target.checked) state.runs.slice(0,10).forEach(x=>state.compareIds.add(x.id));
      else state.runs.forEach(x=>state.compareIds.delete(x.id));
      renderRuns();
    });
    $$(".compare-check").forEach(input=>input.addEventListener("change",e=>{
      if(e.target.checked) state.compareIds.add(e.target.dataset.id);
      else state.compareIds.delete(e.target.dataset.id);
      const button=$('[data-action="compare-runs"]');
      if(button){button.disabled=state.compareIds.size<2;button.textContent="⇄ Compare ("+state.compareIds.size+")";}
    }));
    if (state.currentRun && ["running","queued"].includes(state.currentRun.status)) watchRun(state.currentRun.id,false);
  }
  function renderRunDetail(run) {
    const result = run.result || {};
    const assertion = result.assertion_results || {};
    const events = state.currentRunEvents;
    return '<section class="panel" id="run-detail"><div class="panel-header"><div><div class="panel-title">Run detail · ' +
      esc(run.id) + '</div><div class="panel-subtitle">' + esc(run.test_name || run.test_id) +
      '</div></div><div class="heading-actions">' + statusBadge(run.status,run.passed) +
      (["running","queued"].includes(run.status) ? '<button class="btn danger small" data-action="cancel-run" data-id="' + esc(run.id) + '">■ Cancel</button>' : '') +
      '<button class="btn small" data-action="export-run" data-id="' + esc(run.id) + '" data-format="json">JSON</button>' +
      '<button class="btn small" data-action="export-run" data-id="' + esc(run.id) + '" data-format="markdown">Markdown</button></div></div>' +
      '<div class="grid stats-grid">' +
      statCard("Latency",formatDuration(run.latency_ms),"End-to-end","◷") +
      statCard("Assertions",assertion.total == null ? "—" : (assertion.passed_count || 0) + "/" + assertion.total,"Deterministic checks","✓") +
      statCard("Judge score",result.model_evaluation && result.model_evaluation.score != null ? result.model_evaluation.score + "/100" : "—","Separate evaluator","◎") +
      statCard("Total tokens",(result.usage || {}).total_tokens || "—","Provider usage","▤") + '</div>' +
      panel("Live activity","Token stream, agent activity, tools, metrics and evaluation",'<div class="event-stream" id="run-events">' +
        events.slice(-180).map(renderEvent).join("") + (events.length ? "" : '<div class="muted">Waiting for run events…</div>') + '</div>') +
      (run.result ? '<div class="grid two-col">' +
        panel("Model response","Full response",'<pre class="result-block">' + esc(result.full_response || "") + '</pre>') +
        panel("Assertions","Hidden rules evaluated externally",(assertion.assertions || []).map(item =>
          '<div class="check-row"><span>' + (item.passed ? '<span class="badge pass">Pass</span>' : '<span class="badge fail">Fail</span>') +
          '</span><div><strong>' + esc(item.type) + '</strong><div class="muted">' + esc(item.detail) + '</div></div></div>').join("") || empty("No assertions","No deterministic checks configured.")) +
        panel("Model evaluation","Independent judge result",'<pre class="result-block">' + esc(pretty(result.model_evaluation || {})) + '</pre>') +
        panel("Tool input / output","Complete local tool trace",'<pre class="result-block">' + esc(pretty(result.tool_events || [])) + '</pre>') +
        panel("Prompt and errors","Full input and errors",'<pre class="result-block">' + esc(pretty({prompt:result.full_prompt,system_prompt:result.system_prompt,errors:result.errors})) + '</pre>') +
        '</div>' : '');
  }
  function renderEvent(event) {
    const type = event.type || "event";
    let detail = event.message || event.text || "";
    if (type === "tool_call") detail = "Calling " + event.tool_name + " · " + pretty(event.arguments || {});
    if (type === "tool_result") detail = event.tool_name + " → " + pretty(event.output || {});
    if (type === "metrics") detail = "Usage: " + pretty(event.usage || {});
    if (type === "token") detail = event.text || "";
    if (type === "evaluation") detail = event.stage + ": " + (event.score == null ? (event.passed ? "pass" : "failed") : event.score);
    if (type === "done") detail = "Run " + event.status + (event.passed ? " · passed" : "");
    return '<div class="event-row"><span class="tag">' + esc(type) + '</span> ' + esc(detail) +
      (event.timestamp ? '<span class="muted"> · ' + esc(new Date(event.timestamp).toLocaleTimeString()) + '</span>' : '') + '</div>';
  }
  async function watchRun(id, force) {
    if (!force && state.watchingRun === id) return;
    if (state.activeStream) state.activeStream.abort();
    const controller = new AbortController();
    state.activeStream = controller;
    state.watchingRun = id;
    try {
      await withStreamSlot(async () => {
        const response = await fetch(url("/ui/runs/" + encodeURIComponent(id) + "/stream"),{signal:controller.signal});
        if (!response.ok) throw new Error("Unable to open run event stream (" + response.status + ")");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const chunk = await reader.read();
          if (chunk.done) break;
          buffer += decoder.decode(chunk.value,{stream:true});
          let split;
          while ((split=buffer.indexOf("\n\n")) >= 0) {
            const frame=buffer.slice(0,split); buffer=buffer.slice(split+2);
            const eventName=(frame.match(/^event:\s*(.+)$/m) || [,"message"])[1].trim();
            const data=(frame.match(/^data:\s*(.*)$/m) || [,""])[1];
            if (data === "[DONE]") continue;
            try {
              const event=JSON.parse(data);
              if (event.type === "token") {
                // Token deltas are kept in the active response buffer, not the long-term trace list.
                state.currentRunEvents.push(event);
              } else state.currentRunEvents.push(event);
              if (state.currentRunEvents.length > 1200) state.currentRunEvents.shift();
              appendRunEvent(event);
            } catch (_) {
              if (eventName === "error") toast(data,true);
            }
          }
        }
      });
      const latest=await api("/ui/runs/" + encodeURIComponent(id));
      state.currentRun=latest.run;
      if (state.page === "runs") renderRuns();
    } catch (error) {
      if (error.name !== "AbortError") toast(error.message,true);
    } finally {
      if (state.activeStream === controller) {
        state.activeStream=null;
        state.watchingRun=null;
      }
    }
  }
  function appendRunEvent(event) {
    if (state.page !== "runs") return;
    const node=$("#run-events");
    if (node) {
      const placeholder=node.querySelector(".muted");
      if (placeholder) placeholder.remove();
      node.insertAdjacentHTML("beforeend",renderEvent(event));
      node.scrollTop=node.scrollHeight;
      // Keep rendering small while preserving the full server trace.
      while(node.children.length>180) node.firstElementChild.remove();
    }
  }
  async function cancelRun(id) {
    try {
      const result=await api("/ui/runs/"+encodeURIComponent(id)+"/cancel",{method:"POST"});
      state.currentRun=result.run;
      toast("Cancellation requested.");
      await renderRuns();
    } catch(error){toast(error.message,true);}
  }
  async function compareRuns() {
    try {
      const result=await api("/ui/runs/compare",{method:"POST",body:{run_ids:Array.from(state.compareIds).slice(0,10)}});
      const rows=result.comparison || [];
      $("#modal-root").innerHTML='<div class="modal-backdrop"><div class="modal"><div class="modal-header"><h2>Compare test runs</h2><button class="btn small" data-action="close-modal">✕</button></div>' +
        '<div class="table-wrap"><table><thead><tr><th>RUN</th><th>PASS</th><th>ASSERTION</th><th>JUDGE</th><th>LATENCY</th><th>TOKENS</th></tr></thead><tbody>' +
        rows.map(x=>'<tr><td>'+esc(x.run_id)+'</td><td>'+esc(x.passed)+'</td><td>'+esc(x.assertion_score==null?"—":Math.round(x.assertion_score*100)+"%")+'</td><td>'+esc(x.judge_score==null?"—":x.judge_score)+'</td><td>'+formatDuration(x.latency_ms)+'</td><td>'+esc((x.usage||{}).total_tokens||"—")+'</td></tr>').join("")+
        '</tbody></table></div></div></div>';
    } catch(error){toast(error.message,true);}
  }
  async function exportRun(id,format) {
    try {
      const blob=await withRequestSlot(async () => {
        const response=await fetch(url("/ui/runs/"+encodeURIComponent(id)+"/export?format="+encodeURIComponent(format)));
        if(!response.ok) throw new Error("Export failed ("+response.status+")");
        return response.blob();
      });
      const anchor=document.createElement("a");
      anchor.href=URL.createObjectURL(blob);
      anchor.download=id+"."+ (format==="markdown"?"md":"json");
      anchor.click();
      URL.revokeObjectURL(anchor.href);
    } catch(error){toast(error.message,true);}
  }

  async function renderAgent() {
    const content=$("#page-content");
    let testOptions=[];
    try {
      if (!state.tests.length) await loadTestCatalog();
      testOptions=state.tests;
    } catch (_) {}
    const selected=state.selectedTest;
    content.innerHTML=heading("Harness Agent","Chat directly with the same GLM agent. Watch its tokens and tool calls as they happen.",
      '<button class="btn" data-action="new-chat">＋ New conversation</button>') +
      '<div class="split-layout">' +
      '<section class="panel chat-panel"><div class="panel-header"><div><div class="panel-title">Agent playground</div><div class="panel-subtitle">Live streaming · automatic tool selection · conversation history</div></div><span class="badge pass">Autonomous</span></div>' +
      '<div class="toolbar"><select class="select" id="chat-mode"><option value="free">Free chat · auto tools</option><option value="test">Test-backed chat · selected tools</option></select>' +
      '<select class="select" id="chat-test"><option value="">Choose a test…</option>' + testOptions.map(x=>'<option value="'+esc(x.id)+'" '+(selected&&selected.id===x.id?"selected":"")+'>'+esc(x.name)+'</option>').join("")+'</select></div>' +
      '<div id="chat-messages" class="chat-messages">' + (state.messages.length ? state.messages.map(renderChatMessage).join("") :
        '<div class="chat-empty"><div class="empty-icon">◉</div><strong>Start a conversation with GLM</strong><p>Send a task. Relevant tools are selected automatically, or choose a test scenario to load its toolset.</p></div>') + '</div>' +
      '<form id="chat-form" class="chat-composer"><div class="composer-row"><textarea class="textarea" id="chat-input" rows="2" placeholder="Send a message to the agent…" required></textarea><button class="btn primary" type="submit" id="chat-send">Send ↑</button></div><div class="hint" id="chat-hint">Free chat · toolset selected automatically from task intent</div></form></section>' +
      '<aside class="side-stack">' +
      panel("Agent context","What the tested model receives",'<div class="info-row"><span>Model</span><strong>'+esc(state.model)+'</strong></div><div class="info-row"><span>Mode</span><strong id="context-mode">Free chat</strong></div><div class="info-row"><span>Tools</span><strong id="context-tools">Automatic</strong></div><div class="info-row"><span>Evaluator</span><strong>Hidden</strong></div>') +
      panel("Live tool activity","Calls and results from this conversation",'<div id="chat-tool-events" class="event-stream">'+empty("No tool calls yet","Tool activity appears here as the agent works.")+'</div>') +
      panel("Response metrics","Latest model response",'<div class="info-row"><span>Latency</span><strong id="chat-latency">—</strong></div><div class="info-row"><span>Prompt tokens</span><strong id="chat-prompt-tokens">—</strong></div><div class="info-row"><span>Completion tokens</span><strong id="chat-completion-tokens">—</strong></div><div class="info-row"><span>Total tokens</span><strong id="chat-total-tokens">—</strong></div>') +
      '</aside></div>';
    $("#chat-mode").value=state.chatMode;
    $("#chat-test").disabled=state.chatMode!=="test";
    $("#chat-mode").addEventListener("change",e=>{
      state.chatMode=e.target.value;
      $("#chat-test").disabled=state.chatMode!=="test";
      $("#context-mode").textContent=state.chatMode==="test"?"Test-backed":"Free chat";
      $("#chat-hint").textContent=state.chatMode==="test"?"The selected scenario supplies its normal toolset. Evaluation remains private.":"Free chat · toolset selected automatically from task intent";
    });
    $("#chat-test").addEventListener("change",e=>{
      const item=state.tests.find(x=>x.id===e.target.value);
      state.selectedTest=item || null;
      $("#context-tools").textContent=item?(item.tool_names||[]).join(", ")||"Automatic":"Automatic";
      if(item && state.chatMode==="test") $("#chat-input").value=item.user_prompt || "";
    });
    $("#chat-form").addEventListener("submit",sendChat);
    scrollChat();
  }
  function renderChatMessage(message) {
    const role=message.role==="user"?"user":"assistant";
    return '<div class="message '+role+'"><div class="message-label">'+(role==="user"?"You":"GLM")+'</div>'+esc(message.content||"")+'</div>';
  }
  function scrollChat() {
    const node=$("#chat-messages"); if(node) node.scrollTop=node.scrollHeight;
  }
  function appendChatNode(html) {
    const node=$("#chat-messages");
    if(!node) return null;
    const emptyNode=node.querySelector(".chat-empty"); if(emptyNode) emptyNode.remove();
    node.insertAdjacentHTML("beforeend",html);
    scrollChat();
    return node.lastElementChild;
  }
  async function sendChat(event) {
    event.preventDefault();
    const input=$("#chat-input");
    const text=input.value.trim();
    if(!text) return;
    const testId=state.chatMode==="test" && state.selectedTest ? state.selectedTest.id : null;
    if(state.chatMode==="test" && !testId) {
      toast("Choose a test scenario first.",true); return;
    }
    if(state.chatController) state.chatController.abort();
    const controller=new AbortController();
    state.chatController=controller;
    input.value="";
    state.messages.push({role:"user",content:text});
    appendChatNode(renderChatMessage({role:"user",content:text}));
    const assistant=appendChatNode('<div class="message assistant"><div class="message-label">GLM</div><span class="streaming-text"></span><span class="typing-cursor"> ▍</span></div>');
    const toolPanel=$("#chat-tool-events");
    if(toolPanel) toolPanel.innerHTML="";
    $("#chat-send").disabled=true;
    $("#chat-latency").textContent="Running…";
    let fullText="",doneEvent=null;
    try {
      await withStreamSlot(async () => {
        const response=await fetch(url("/ui/agent/chat"),{
          method:"POST",headers:{"Content-Type":"application/json"},
          body:JSON.stringify({message:text,test_id:testId,conversation_id:state.conversationId}),
          signal:controller.signal
        });
        if(!response.ok) {
          const body=await response.json().catch(()=>({}));
          throw new Error(body.detail || "Chat failed ("+response.status+")");
        }
        state.conversationId=response.headers.get("X-Conversation-ID") || state.conversationId;
        const reader=response.body.getReader(),decoder=new TextDecoder();
        let buffer="";
        while(true) {
          const item=await reader.read(); if(item.done) break;
          buffer+=decoder.decode(item.value,{stream:true});
          let split;
          while((split=buffer.indexOf("\n\n"))>=0) {
            const frame=buffer.slice(0,split); buffer=buffer.slice(split+2);
            const data=(frame.match(/^data:\s*(.*)$/m)||[,""])[1];
            if(!data || data==="[DONE]") continue;
            const event=JSON.parse(data);
            if(event.type==="token") {
              fullText+=event.text||"";
              const span=assistant.querySelector(".streaming-text"); if(span) span.textContent=fullText;
              scrollChat();
            } else if(event.type==="tool_call" || event.type==="tool_result") {
              if(toolPanel) {
                const placeholder=toolPanel.querySelector(".empty-state"); if(placeholder) placeholder.remove();
                toolPanel.insertAdjacentHTML("beforeend",'<div class="event-row">'+renderEvent(event)+'</div>');
                toolPanel.scrollTop=toolPanel.scrollHeight;
              }
            } else if(event.type==="metrics") {
              const usage=event.usage||{};
              $("#chat-prompt-tokens").textContent=usage.prompt_tokens||"—";
              $("#chat-completion-tokens").textContent=usage.completion_tokens||"—";
              $("#chat-total-tokens").textContent=usage.total_tokens||"—";
            } else if(event.type==="done") {
              doneEvent=event;
              if(event.content) fullText=event.content;
            } else if(event.type==="error") {
              throw new Error(event.message||"Model error");
            }
          }
        }
      });
      if(assistant) {
        const span=assistant.querySelector(".streaming-text");
        if(span) span.textContent=fullText;
        const cursor=assistant.querySelector(".typing-cursor"); if(cursor) cursor.remove();
      }
      state.messages.push({role:"assistant",content:fullText});
      if(doneEvent) {
        $("#chat-latency").textContent=formatDuration(doneEvent.latency_ms);
        const usage=doneEvent.usage||{};
        $("#chat-prompt-tokens").textContent=usage.prompt_tokens||"—";
        $("#chat-completion-tokens").textContent=usage.completion_tokens||"—";
        $("#chat-total-tokens").textContent=usage.total_tokens||"—";
        $("#context-tools").textContent=(doneEvent.tool_names||[]).join(", ")||"None selected";
      }
    } catch(error) {
      if(error.name!=="AbortError") {
        if(assistant) {
          const span=assistant.querySelector(".streaming-text"); if(span) span.textContent="Error: "+error.message;
          assistant.classList.add("error");
        }
        toast(error.message,true);
      }
    } finally {
      if(state.chatController===controller) state.chatController=null;
      $("#chat-send").disabled=false;
      scrollChat();
    }
  }
  function newChat() {
    if(state.chatController) state.chatController.abort();
    state.conversationId=null;state.messages=[];state.selectedTest=null;
    state.chatMode="free";
    renderAgent();
  }

  async function renderConversations() {
    const content=$("#page-content");
    const result=await api("/ui/conversations");
    state.conversations=result.conversations||[];
    content.innerHTML=heading("Conversations","Browse saved playground conversations and inspect their messages.",
      '<button class="btn primary" data-page="agent">＋ New conversation</button>') +
      panel("Conversation history",state.conversations.length+" sessions",
        state.conversations.length?'<div class="table-wrap"><table><thead><tr><th>SESSION</th><th>MESSAGES</th><th>CREATED</th><th></th></tr></thead><tbody>'+
        state.conversations.map(x=>'<tr><td><strong>'+esc(x.id)+'</strong></td><td>'+esc(x.message_count||0)+'</td><td>'+formatTime(x.created_at)+'</td><td><button class="btn small" data-action="open-conversation" data-id="'+esc(x.id)+'">Open</button></td></tr>').join("")+
        '</tbody></table></div>':empty("No conversations yet","Start chatting in Harness Agent."));
  }
  async function openConversation(id) {
    try {
      const result=await api("/ui/conversations/"+encodeURIComponent(id));
      state.conversationId=id;
      state.messages=(result.messages||[]).filter(x=>x.role==="user"||x.role==="assistant");
      state.chatMode="free";state.selectedTest=null;
      navigate("agent");
    } catch(error){toast(error.message,true);}
  }
  async function renderTools() {
    const content=$("#page-content");
    const result=await api("/ui/tools");
    state.tools=result.tools||[];
    content.innerHTML=heading("Tools","The tested agent receives ordinary local tools selected for each task.",
      '<button class="btn" data-action="refresh">↻ Refresh</button>') +
      '<div class="grid stats-grid">'+statCard("Available tools",state.tools.length,"Local and bounded","⌘")+
      statCard("Selection","Automatic","Task intent or test scenario","✳")+
      statCard("External actions","Disabled","No real-world side effects","⛨")+
      statCard("Memory","Session scoped","Bounded temporary notes","▤")+'</div>'+
      panel("Tool registry","Definitions exposed to the tested model",'<div class="test-list">'+state.tools.map(item=>
        '<article class="test-card"><div class="test-card-top"><span class="badge info">Function tool</span><span class="tag">Local</span></div><h3>'+esc(item.name)+'</h3><p>'+esc(item.description)+'</p><div class="code-note">Parameters</div><pre class="result-block">'+esc(pretty(item.parameters||{}))+'</pre></article>'
      ).join("")+'</div>');
  }
  async function renderMetrics() {
    const content=$("#page-content");
    const result=await api("/ui/metrics?limit=500");
    state.metrics=result.metrics||[];
    const values=state.metrics.filter(x=>x.metric==="latency_ms").map(x=>Number(x.value)).filter(Number.isFinite);
    const usage=state.metrics.filter(x=>x.metric==="total_tokens").reduce((sum,x)=>sum+Number(x.value||0),0);
    const avg=result.summary.average_latency_ms;
    const max=result.summary.max_latency_ms;
    const rows=state.metrics.slice(0,100).map(item=>'<tr><td>'+esc(item.metric)+'</td><td>'+esc(item.value)+'</td><td>'+esc(item.session_id)+'</td><td>'+formatTime(item.created_at)+'</td></tr>').join("");
    const bars=values.slice(-30);
    const maxValue=Math.max(1,...bars);
    const chart=bars.length?'<div style="height:160px;display:flex;align-items:flex-end;gap:5px;padding:14px 4px 3px">'+bars.map(value=>
      '<div title="'+esc(value.toFixed(1)+' ms')+'" style="flex:1;min-width:4px;height:'+Math.max(3,value/maxValue*100)+'%;background:linear-gradient(180deg,#b29bff,#7565d1);border-radius:4px 4px 1px 1px"></div>'
    ).join("")+'</div><div class="hint">Recent latency samples · milliseconds</div>':empty("No metrics yet","Run a test or chat with the agent to collect metrics.");
    content.innerHTML=heading("Metrics","Token usage, response latency, and model execution measurements.",
      '<button class="btn" data-action="refresh">↻ Refresh</button>')+
      '<div class="grid stats-grid">'+statCard("Average latency",avg==null?"—":formatDuration(avg),"Recorded responses","◷")+
      statCard("Maximum latency",max==null?"—":formatDuration(max),"Recorded responses","↗")+
      statCard("Token samples",usage||"—","Sum of total-token samples","▤")+
      statCard("Metric records",state.metrics.length,"Stored measurement points","▥")+'</div>'+
      '<div class="grid two-col">'+panel("Latency trend","Recent response latency",chart)+
      panel("Metric availability","Collected metric names",'<div class="activity-list">'+Array.from(new Set(state.metrics.map(x=>x.metric))).map(name=>
        '<div class="info-row"><span>'+esc(name)+'</span><strong>'+state.metrics.filter(x=>x.metric===name).length+' samples</strong></div>'
      ).join("")+'</div>')+'</div>'+
      panel("Raw metrics","Latest 100 records",rows?'<div class="table-wrap"><table><thead><tr><th>METRIC</th><th>VALUE</th><th>SESSION</th><th>TIME</th></tr></thead><tbody>'+rows+'</tbody></table></div>':empty("No metric records","Data appears after model calls."));
  }
  async function renderTraces() {
    const content=$("#page-content");
    const [result,logs]=await Promise.all([api("/ui/traces?limit=100"),api("/ui/logs?limit=100")]);
    state.traces=result.tool_events||[];
    const toolRows=state.traces.map(item=>'<tr><td>'+esc(item.tool_name)+'</td><td>'+statusBadge(item.status)+'</td><td><code>'+esc(pretty(item.input))+'</code></td><td><code>'+esc(pretty(item.output))+'</code></td><td>'+formatTime(item.created_at)+'</td></tr>').join("");
    const errors=logs.errors||[];
    content.innerHTML=heading("Traces & Logs","Inspect tool calls, run traces, errors, and execution history.",
      '<button class="btn" data-action="refresh">↻ Refresh</button>')+
      '<div class="grid stats-grid">'+statCard("Tool events",state.traces.length,"Captured calls and results","⌘")+
      statCard("Failed tool calls",(logs.tool_errors||[]).length,"Local tool errors","!")+
      statCard("Run errors",errors.length,"Recent failed runs","⚠")+
      statCard("Tracked runs",(result.runs||[]).length,"Recent executions","▷")+'</div>'+
      panel("Tool events","Inputs and outputs are recorded separately from the agent's messages.",
        toolRows?'<div class="table-wrap"><table><thead><tr><th>TOOL</th><th>STATUS</th><th>INPUT</th><th>OUTPUT</th><th>TIME</th></tr></thead><tbody>'+toolRows+'</tbody></table></div>':empty("No tool events","Tool traces appear when the model calls a local tool."))+
      panel("Errors and stack traces","Recent run errors",errors.length?'<div class="activity-list">'+errors.map(item=>
        '<div class="activity-item"><span class="activity-marker red"></span><div><div class="activity-text">'+esc(item.error||"Run failed")+'</div><div class="activity-meta">'+esc(item.run_id)+' · '+formatTime(item.created_at)+'</div></div></div>'
      ).join("")+'</div>':empty("No errors","No recent run errors."));
  }
  async function renderSettings() {
    const content=$("#page-content");
    let settings={};
    try { settings=await api("/ui/settings");state.settings=settings; }
    catch(error) { setConnected(false,"Unable to read backend settings"); }
    content.innerHTML=heading("Settings","Connect the workspace to your Deplexo backend and inspect runtime configuration.")+
      '<div class="grid two-col"><section class="panel"><div class="panel-header"><div><div class="panel-title">Backend connection</div><div class="panel-subtitle">The frontend calls only the /ui endpoint contract.</div></div></div>'+
      '<form id="settings-form" class="form-grid"><div class="field full"><label for="api-base">Backend base URL</label><input class="input" id="api-base" placeholder="https://your-service.example.com" value="'+esc(state.apiBase)+'"><div class="hint">Enter the deployed Deplexo service URL, without /ui at the end. Saved in this browser only.</div></div>'+
      '<div class="field full"><div class="heading-actions"><button class="btn primary" type="submit">Save connection</button><button class="btn" type="button" data-action="test-connection">Test connection</button></div></div></form>'+
      '<div id="connection-result" class="hint" style="margin-top:12px"></div></section>'+
      panel("Backend configuration","Read-only environment details",'<div class="info-row"><span>Model</span><strong>'+esc(settings.model||"—")+'</strong></div><div class="info-row"><span>Provider key</span><strong>'+ (settings.provider_configured?'<span class="badge pass">Configured</span>':'<span class="badge fail">Missing</span>')+'</strong></div><div class="info-row"><span>Cloudflare D1</span><strong>'+ (settings.d1_configured?'<span class="badge pass">Configured</span>':'<span class="badge">Memory fallback</span>')+'</strong></div><div class="info-row"><span>Max agent steps</span><strong>'+(Number(settings.max_agent_steps)===0?"Unlimited":esc(settings.max_agent_steps))+'</strong></div><div class="info-row"><span>Request timeout</span><strong>'+esc(settings.request_timeout_seconds||"—")+' s</strong></div>')+'</div>'+
      panel("Runtime policy","Current safeguards",'<div class="info-row"><span>Worker model</span><strong>Single worker</strong></div><div class="info-row"><span>Test concurrency</span><strong>1 active test run</strong></div><div class="info-row"><span>Agent permissions</span><strong>Local tools only</strong></div><div class="info-row"><span>Evaluation visibility</span><strong>Hidden from tested agent</strong></div><div class="info-row"><span>Authentication</span><strong><span class="badge fail">Disabled</span></strong></div><p class="hint">The backend has no application authentication, as configured. Restrict public ingress before sharing this URL; any reachable caller can consume model quota.</p>');
    $("#settings-form").addEventListener("submit",e=>{
      e.preventDefault();
      state.apiBase=$("#api-base").value.trim().replace(/\/+$/,"");
      localStorage.setItem("model-lab-api",state.apiBase);
      toast("Backend URL saved in this browser.");
      testConnection();
    });
  }
  async function testConnection() {
    const result=$("#connection-result");
    try {
      const data=await api("/ui/model/status");
      state.model=data.model||state.model;
      setConnected(true,state.model);
      if(result) result.textContent="Connected to "+state.model+" · Streaming enabled";
      toast("Backend connection successful.");
    } catch(error) {
      setConnected(false,"Check URL or service status");
      if(result) result.textContent=error.message;
      toast(error.message,true);
    }
  }
  async function refreshCurrent() {
    try {
      if(state.page==="runs" && state.currentRun && ["running","queued"].includes(state.currentRun.status)) {
        const x=await api("/ui/runs/"+encodeURIComponent(state.currentRun.id));
        state.currentRun=x.run;
      }
      await renderPage();
    } catch(error){toast(error.message,true);}
  }
  function closeModal() { $("#modal-root").innerHTML=""; }
  function handleClick(event) {
    const pageButton=event.target.closest("[data-page]");
    if(pageButton){navigate(pageButton.dataset.page);return;}
    const button=event.target.closest("[data-action]");
    if(!button)return;
    const action=button.dataset.action,id=button.dataset.id;
    if(action==="refresh") refreshCurrent();
    else if(action==="new-test") openTestEditor();
    else if(action==="close-modal") closeModal();
    else if(action==="run-test") previewRun(id);
    else if(action==="confirm-run") {closeModal();startRun(id);}
    else if(action==="inspect-test") inspectTest(id);
    else if(action==="edit-test") {
      api("/ui/tests/"+encodeURIComponent(id)).then(openTestEditor).catch(e=>toast(e.message,true));
    }
    else if(action==="delete-test") {
      if(!window.confirm("Delete this custom test? This cannot be undone.")) return;
      api("/ui/tests/"+encodeURIComponent(id),{method:"DELETE"}).then(()=>{
        toast("Custom test deleted.");
        renderBuilder();
      }).catch(e=>toast(e.message,true));
    }
    else if(action==="view-run") {
      Promise.all([api("/ui/runs/"+encodeURIComponent(id)),api("/ui/runs/"+encodeURIComponent(id)+"/events")]).then(values=>{
        state.currentRun=values[0].run;
        state.currentRunEvents=values[1].events || [];
        navigate("runs");
      }).catch(e=>toast(e.message,true));
    }
    else if(action==="cancel-run") cancelRun(id);
    else if(action==="compare-runs") compareRuns();
    else if(action==="export-run") exportRun(id,button.dataset.format);
    else if(action==="new-chat") newChat();
    else if(action==="test-connection") testConnection();
    else if(action==="open-conversation") openConversation(id);
  }
  function setup() {
    $("#sidebar").addEventListener("click",handleClick);
    $(".topbar").addEventListener("click",handleClick);
    $("#page-content").addEventListener("click",handleClick);
    $("#modal-root").addEventListener("click",handleClick);
    $("#refresh-button").addEventListener("click",refreshCurrent);
    $("#mobile-menu").addEventListener("click",()=>$("#sidebar").classList.toggle("open"));
    $("#page-content").addEventListener("submit",event=>{
      if(event.target.id!=="chat-form" && event.target.id!=="settings-form" && event.target.id!=="test-editor") return;
    });
    navigate("overview");
    state.refreshTimer=setInterval(()=>{
      if(state.page==="overview" && !document.hidden) renderOverview().catch(()=>{});
    },30000);
  }
  document.addEventListener("DOMContentLoaded",setup);
})();
const $ = (selector) => document.querySelector(selector);
const state = {
  config: null,
  reviewer: null,
  records: [],
  filtered: [],
  currentId: null,
  current: null,
  saveTimer: null,
  comparison: null,
};

const labelNames = {
  source_authority: "来源权威性",
  claim_type: "主张类型",
  event_type: "事件类型",
  direction: "方向",
  materiality: "重要性",
  evidence_relation: "证据关系",
  label_confidence: "标签置信度",
  gold_action: "后续动作",
};

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const body = response.headers.get("content-type")?.includes("json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error(body.error || body.detail || body || `HTTP ${response.status}`);
  return body;
}

function notice(message, error = false) {
  const node = $("#notice");
  node.textContent = message;
  node.classList.toggle("error", error);
  node.classList.remove("hidden");
  clearTimeout(node.timer);
  node.timer = setTimeout(() => node.classList.add("hidden"), 4200);
}

function setSaveStatus(text, kind = "") {
  const node = $("#saveStatus");
  node.textContent = text;
  node.className = `save-status ${kind}`;
}

function option(value, label = value) {
  const node = document.createElement("option");
  node.value = value;
  node.textContent = label;
  return node;
}

function renderConfigFields() {
  const reviewerSelect = $("#reviewerSelect");
  reviewerSelect.replaceChildren(...state.config.reviewers.map((id) => option(id)));
  state.reviewer = localStorage.getItem("finjevReviewer") || state.config.reviewers[0];
  if (!state.config.reviewers.includes(state.reviewer)) state.reviewer = state.config.reviewers[0];
  reviewerSelect.value = state.reviewer;

  const fields = $("#labelFields");
  fields.innerHTML = "";
  Object.entries(labelNames).forEach(([field, title]) => {
    const label = document.createElement("label");
    label.textContent = title;
    const select = document.createElement("select");
    select.id = `label-${field}`;
    select.dataset.labelField = field;
    select.append(option("", "请选择"));
    state.config.enums[field].forEach((value) => select.append(option(value)));
    label.append(select);
    fields.append(label);
  });

  const riskFlags = $("#riskFlags");
  riskFlags.innerHTML = "";
  state.config.risk_flags.forEach((flag) => {
    const label = document.createElement("label");
    label.className = "risk-chip";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = flag;
    input.dataset.riskFlag = flag;
    const span = document.createElement("span");
    span.textContent = flag;
    label.append(input, span);
    riskFlags.append(label);
  });
}

async function loadRecords(preferredId = null) {
  const data = await api(`/api/reviewers/${encodeURIComponent(state.reviewer)}/records`);
  state.records = data.items;
  $("#progressText").textContent = `${data.completed} / ${data.total}`;
  $("#progressBar").style.width = `${data.total ? (data.completed / data.total) * 100 : 0}%`;
  $("#completeReview").disabled = data.completed !== data.total || data.locked;
  $("#completeReview").classList.toggle("hidden", data.locked);
  $("#unlockReview").classList.toggle("hidden", !data.locked);
  $("#reviewForm").querySelectorAll("input, select, textarea").forEach((node) => { node.disabled = data.locked; });
  $("#saveRecord").disabled = data.locked;
  $("#downloadReview").href = `/api/reviewers/${encodeURIComponent(state.reviewer)}/export`;
  applyRecordFilter();
  const savedId = localStorage.getItem(`finjevCurrent:${state.reviewer}`);
  const target = preferredId || savedId || state.filtered[0]?.record_id || state.records[0]?.record_id;
  if (target) await loadRecord(target);
}

function applyRecordFilter() {
  const filter = $("#recordFilter").value;
  state.filtered = state.records.filter((record) => filter === "all" || (filter === "pending" ? !record.complete : record.complete));
  renderRecordList();
}

function renderRecordList() {
  const list = $("#recordList");
  list.innerHTML = "";
  state.filtered.forEach((record, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `record-item ${record.record_id === state.currentId ? "active" : ""}`;
    button.innerHTML = `<div class="record-top"><strong>${index + 1}. ${escapeHtml(record.issuer || record.record_id)}</strong><span class="status-dot ${record.complete ? "complete" : ""}"></span></div><small>${escapeHtml(record.section || "未分类")} · P${record.pdf_page}</small>`;
    button.addEventListener("click", () => navigateTo(record.record_id));
    list.append(button);
  });
}

async function navigateTo(recordId) {
  if (state.current && !$("#saveRecord").disabled) await saveCurrent(false);
  await loadRecord(recordId);
}

async function loadRecord(recordId) {
  state.currentId = recordId;
  state.current = await api(`/api/reviewers/${encodeURIComponent(state.reviewer)}/records/${encodeURIComponent(recordId)}`);
  localStorage.setItem(`finjevCurrent:${state.reviewer}`, recordId);
  renderRecordList();
  renderRecord(state.current);
}

function renderRecord(record) {
  $("#recordTitle").textContent = record.issuer || record.record_id;
  $("#recordMeta").textContent = `${record.report_period || "—"} · P${record.pdf_page}`;
  const pdfUrl = `/api/pdfs/${encodeURIComponent(record.source_document)}#page=${record.pdf_page}&zoom=page-width`;
  $("#pdfFrame").src = pdfUrl;
  $("#openPdf").href = pdfUrl;
  $("#claimText").textContent = record.proposed_claim;
  $("#excerptList").innerHTML = record.source_excerpts.map((text) => `<div class="excerpt">${escapeHtml(text)}</div>`).join("");
  $("#claimReview").value = record.claim_review || "";
  $("#correctedClaim").value = record.corrected_claim || "";
  toggleConditionalFields();
  renderNumericFacts(record.proposed_numeric_facts);
  $("#numericReview").value = record.numeric_facts_review || "";
  $("#correctedNumeric").value = record.corrected_numeric_facts ? JSON.stringify(record.corrected_numeric_facts, null, 2) : JSON.stringify(record.proposed_numeric_facts, null, 2);
  document.querySelectorAll("[data-label-field]").forEach((select) => { select.value = record.labels[select.dataset.labelField] || ""; });
  document.querySelectorAll("[data-risk-flag]").forEach((checkbox) => { checkbox.checked = (record.labels.risk_flags || []).includes(checkbox.value); });
  $("#materialityBasis").value = record.materiality_basis || "";
  $("#followUps").value = (record.follow_up_questions || []).join("\n");
  $("#reviewerNotes").value = record.reviewer_notes || "";
  setSaveStatus(record.validation_errors.length ? `还缺 ${record.validation_errors.length} 项` : "已完整保存", record.validation_errors.length ? "" : "saved");
}

function renderNumericFacts(facts) {
  const node = $("#numericFacts");
  if (!facts?.length) {
    node.innerHTML = `<div class="empty-data">本条没有结构化数值事实</div>`;
    return;
  }
  const columns = ["metric", "raw_value", "unit", "period", "comparison_value", "change_pct"];
  node.innerHTML = `<table><thead><tr>${columns.map((key) => `<th>${key}</th>`).join("")}</tr></thead><tbody>${facts.map((fact) => `<tr>${columns.map((key) => `<td>${escapeHtml(fact[key] ?? "—")}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function toggleConditionalFields() {
  $("#correctedClaimWrap").classList.toggle("hidden", $("#claimReview").value !== "EDIT");
  $("#correctedNumericWrap").classList.toggle("hidden", $("#numericReview").value !== "EDIT");
}

function collectPayload() {
  let correctedNumeric = null;
  if ($("#numericReview").value === "EDIT") {
    correctedNumeric = JSON.parse($("#correctedNumeric").value || "[]");
    if (!Array.isArray(correctedNumeric)) throw new Error("修正后的数值事实必须是 JSON 数组");
  }
  const labels = {};
  document.querySelectorAll("[data-label-field]").forEach((select) => { labels[select.dataset.labelField] = select.value || null; });
  labels.risk_flags = [...document.querySelectorAll("[data-risk-flag]:checked")].map((input) => input.value);
  return {
    claim_review: $("#claimReview").value || null,
    corrected_claim: $("#correctedClaim").value.trim() || null,
    numeric_facts_review: $("#numericReview").value || null,
    corrected_numeric_facts: correctedNumeric,
    labels,
    materiality_basis: $("#materialityBasis").value.trim() || null,
    follow_up_questions: $("#followUps").value.split("\n").map((line) => line.trim()).filter(Boolean),
    reviewer_notes: $("#reviewerNotes").value.trim() || null,
  };
}

async function saveCurrent(showNotice = true) {
  if (!state.currentId || $("#saveRecord").disabled) return;
  clearTimeout(state.saveTimer);
  setSaveStatus("正在保存…", "saving");
  try {
    const saved = await api(`/api/reviewers/${encodeURIComponent(state.reviewer)}/records/${encodeURIComponent(state.currentId)}`, { method: "PUT", body: JSON.stringify(collectPayload()) });
    state.current = saved;
    const item = state.records.find((record) => record.record_id === state.currentId);
    if (item) item.complete = !saved.validation_errors.length;
    const completed = state.records.filter((record) => record.complete).length;
    $("#progressText").textContent = `${completed} / ${state.records.length}`;
    $("#progressBar").style.width = `${(completed / state.records.length) * 100}%`;
    $("#completeReview").disabled = completed !== state.records.length;
    setSaveStatus(saved.validation_errors.length ? `已保存，还缺 ${saved.validation_errors.length} 项` : "已完整保存", saved.validation_errors.length ? "" : "saved");
    renderRecordList();
    if (showNotice) notice("当前记录已保存");
  } catch (error) {
    setSaveStatus("保存失败", "failed");
    notice(error.message, true);
    throw error;
  }
}

function scheduleSave() {
  setSaveStatus("等待自动保存…", "saving");
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(() => saveCurrent(false).catch(() => {}), 750);
}

async function move(delta) {
  await saveCurrent(false);
  const index = state.filtered.findIndex((record) => record.record_id === state.currentId);
  const target = state.filtered[index + delta];
  if (target) await loadRecord(target.record_id);
}

async function completeReview() {
  if (!confirm(`确认提交 ${state.reviewer} 的全部 49 条记录并锁定？锁定后才能进入双人比较。`)) return;
  try {
    await saveCurrent(false);
    await api(`/api/reviewers/${encodeURIComponent(state.reviewer)}/complete`, { method: "POST" });
    notice(`${state.reviewer} 已完成并锁定`);
    state.config = await api("/api/config");
    await loadRecords(state.currentId);
  } catch (error) { notice(error.message, true); }
}

async function unlockReview() {
  if (!confirm("解除锁定会使双人比较暂时不可用。确定继续？")) return;
  await api(`/api/reviewers/${encodeURIComponent(state.reviewer)}/unlock`, { method: "POST" });
  notice(`${state.reviewer} 已解除锁定`);
  await loadRecords(state.currentId);
}

function switchMode(mode) {
  document.querySelectorAll(".mode-tab").forEach((button) => button.classList.toggle("active", button.dataset.mode === mode));
  $("#reviewView").classList.toggle("hidden", mode !== "review");
  $("#compareView").classList.toggle("hidden", mode !== "compare");
  $("#reviewerSelect").disabled = mode !== "review";
  if (mode === "compare") loadComparison();
}

async function loadComparison() {
  try {
    state.comparison = await api("/api/comparison");
    $("#exportGold").disabled = false;
    renderMetrics();
    renderConflictList();
  } catch (error) {
    state.comparison = null;
    $("#exportGold").disabled = true;
    const message = error.message.includes("Both reviewers") ? "两位复核者都完成并锁定后才可比较" : error.message;
    $("#metricCards").innerHTML = `<div class="metric-card"><span>暂不可比较</span><strong>—</strong><small>${escapeHtml(message)}</small></div>`;
    $("#conflictList").innerHTML = "";
    $("#conflictCount").textContent = "等待双人完成";
  }
}

function renderMetrics() {
  const priority = ["event_type", "direction", "materiality", "evidence_relation", "gold_action"];
  $("#metricCards").innerHTML = priority.map((field) => {
    const metric = state.comparison.metrics[field];
    return `<article class="metric-card"><span>${labelNames[field] || field}</span><strong>${(metric.agreement * 100).toFixed(1)}%</strong><small>κ ${metric.cohen_kappa ?? "不可计算"}</small></article>`;
  }).join("");
  $("#conflictCount").textContent = `冲突 ${state.comparison.conflicts} · 已仲裁 ${state.comparison.adjudicated_conflicts}`;
}

function filteredConflicts() {
  if (!state.comparison) return [];
  const filter = $("#conflictFilter").value;
  return state.comparison.items.filter((item) => filter === "all" || (filter === "conflict" ? !item.agreed : !item.agreed && !item.adjudicated));
}

function renderConflictList() {
  const list = $("#conflictList");
  list.innerHTML = "";
  filteredConflicts().forEach((item) => {
    const button = document.createElement("button");
    button.className = "record-item";
    button.innerHTML = `<div class="record-top"><strong>${escapeHtml(item.issuer)}</strong><span class="status-dot ${item.adjudicated || item.agreed ? "complete" : ""}"></span></div><small>P${item.pdf_page} · ${item.conflict_fields.length ? item.conflict_fields.join(", ") : "完全一致"}</small>`;
    button.addEventListener("click", () => renderAdjudication(item));
    list.append(button);
  });
}

function decisionRows(decision, conflicts) {
  return Object.entries(decision).map(([key, value]) => `<div class="decision-row"><span>${escapeHtml(labelNames[key] || key)}${conflicts.includes(key) ? ' <b class="conflict-tag">冲突</b>' : ""}</span><code>${escapeHtml(typeof value === "string" ? value : JSON.stringify(value, null, 2))}</code></div>`).join("");
}

function renderAdjudication(item) {
  const [left, right] = state.comparison.reviewers;
  const panel = $("#adjudicationPanel");
  panel.className = "adjudication-panel";
  panel.innerHTML = `
    <div class="adjudication-heading"><div><span class="eyebrow">P${item.pdf_page} · ${escapeHtml(item.source_document)}</span><h2>${escapeHtml(item.claim)}</h2></div><div>${item.conflict_fields.map((field) => `<span class="conflict-tag">${escapeHtml(field)}</span>`).join("")}</div></div>
    <div class="reviewer-columns">
      <article class="reviewer-card"><h3>${escapeHtml(left)}</h3>${decisionRows(item.reviewer_values[left], item.conflict_fields)}</article>
      <article class="reviewer-card"><h3>${escapeHtml(right)}</h3>${decisionRows(item.reviewer_values[right], item.conflict_fields)}</article>
    </div>
    <form id="adjudicationForm" class="adjudication-form">
      <div class="field-grid two">
        <label>最终采用
          <select id="resolution"><option value="${escapeHtml(left)}">采用 ${escapeHtml(left)}</option><option value="${escapeHtml(right)}">采用 ${escapeHtml(right)}</option><option value="custom">自定义最终结果</option></select>
        </label>
        <label>仲裁者 ID<input id="adjudicatorId" type="text" placeholder="例如 chief_reviewer" /></label>
      </div>
      <label>冲突处理说明<textarea id="resolutionNote" rows="3" placeholder="说明采用该结果的证据和理由"></textarea></label>
      <label id="customFinalWrap" class="hidden">自定义最终结果（JSON）<textarea id="customFinal" class="code-input" rows="16">${escapeHtml(JSON.stringify(item.reviewer_values[left], null, 2))}</textarea></label>
      <button class="button primary" type="submit">保存仲裁结果</button>
    </form>`;
  $("#resolution").addEventListener("change", () => $("#customFinalWrap").classList.toggle("hidden", $("#resolution").value !== "custom"));
  $("#adjudicationForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const resolution = $("#resolution").value;
      await api(`/api/adjudications/${encodeURIComponent(item.record_id)}`, {
        method: "PUT",
        body: JSON.stringify({
          resolution,
          adjudicator_id: $("#adjudicatorId").value.trim(),
          conflict_resolution: $("#resolutionNote").value.trim(),
          final: resolution === "custom" ? JSON.parse($("#customFinal").value) : null,
        }),
      });
      notice("仲裁结果已保存");
      await loadComparison();
    } catch (error) { notice(error.message, true); }
  });
}

async function exportGold() {
  if (!confirm("确认所有冲突已经完成仲裁，并生成不可覆盖的 v0.3-gold 数据集？")) return;
  try {
    const result = await api("/api/gold/export", { method: "POST" });
    notice(`Gold 数据集已生成：${result.output}`);
  } catch (error) { notice(error.message, true); }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

async function init() {
  try {
    state.config = await api("/api/config");
    renderConfigFields();
    $("#exportGold").disabled = !state.config.all_completed;
    await loadRecords();
    $("#reviewerSelect").addEventListener("change", async (event) => {
      state.reviewer = event.target.value;
      localStorage.setItem("finjevReviewer", state.reviewer);
      state.current = null;
      await loadRecords();
    });
    $("#recordFilter").addEventListener("change", applyRecordFilter);
    $("#reviewForm").addEventListener("input", scheduleSave);
    $("#reviewForm").addEventListener("change", () => { toggleConditionalFields(); scheduleSave(); });
    $("#saveRecord").addEventListener("click", () => saveCurrent(true));
    $("#previousRecord").addEventListener("click", () => move(-1));
    $("#nextRecord").addEventListener("click", () => move(1));
    $("#completeReview").addEventListener("click", completeReview);
    $("#unlockReview").addEventListener("click", unlockReview);
    document.querySelectorAll(".mode-tab").forEach((button) => button.addEventListener("click", () => switchMode(button.dataset.mode)));
    $("#refreshComparison").addEventListener("click", loadComparison);
    $("#conflictFilter").addEventListener("change", renderConflictList);
    $("#exportGold").addEventListener("click", exportGold);
  } catch (error) {
    notice(`应用初始化失败：${error.message}`, true);
  }
}

init();

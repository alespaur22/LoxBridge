/*
 * Vanilla JS GUI nad LoxBridge Config HTTP API.
 *
 * Žádný frontend framework, žádná business logika: veškeré
 * rozhodování (matching, validace, override diffing) dělá backend.
 * JS tady jen posílá formulářová data na server a vykresluje, co
 * dostane zpátky. Editace capabilities v NEW konfiguraci mění jen
 * lokální kopii instance dictu (obyčejný přiřazení hodnoty do pole),
 * bez jakéhokoliv přepočtu - ten dělá až server při Preview/Validate.
 */

const root = document.getElementById("app");

const state = {
  readOnly: false,
  view: "list",
  homeyId: null,
  detail: null,
  form: null, // { templateId, instanceName, loxoneNameBase, keyBase }
  previewInstance: null, // aktuální (klientem editovaná) kandidátní instance
  templateLabel: null,
  validateResult: null,
  lastValidatedInstanceJson: null,
  assignment: null,
};

async function api(method, path, body) {
  const options = { method };
  if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }
  const res = await fetch(path, options);
  let data = {};
  try {
    data = await res.json();
  } catch (e) {
    data = {};
  }
  if (!res.ok) {
    const err = new Error(data.message || res.statusText);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

function esc(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function statusBadge(status) {
  const label = { configured: "CONFIGURED", new: "NEW", missing: "MISSING" }[status] || status;
  return `<span class="status-badge status-${esc(status)}">${esc(label)}</span>`;
}

function boolCell(value) {
  if (value === null || value === undefined) {
    return `<span class="bool-unknown">–</span>`;
  }
  return value
    ? `<span class="bool-yes">ano</span>`
    : `<span class="bool-no">ne</span>`;
}

function render(html) {
  root.innerHTML = html;
}

// ---------------------------------------------------------------------
// List view
// ---------------------------------------------------------------------

async function showList() {
  state.view = "list";
  render("Načítám seznam zařízení…");
  const devices = await api("GET", "/api/devices");
  state.devices = devices;
  renderList();
}

function renderList() {
  const main = state.devices.filter(
    (d) => !(d.status === "new" && d.bridgeable === false)
  );
  const hidden = state.devices.filter(
    (d) => d.status === "new" && d.bridgeable === false
  );

  const row = (d) => `
    <tr class="device-row" data-id="${esc(d.homey_id)}">
      <td>${esc(d.instance_name || d.homey_name || d.homey_id)}</td>
      <td>${esc(d.zone_name || "")}</td>
      <td>${statusBadge(d.status)}</td>
      <td>${boolCell(d.bridgeable)}</td>
      <td>${esc(d.template_id || "")}</td>
    </tr>`;

  render(`
    <table>
      <thead>
        <tr><th>Name</th><th>Zone</th><th>Status</th><th>Bridgeable</th><th>Template</th></tr>
      </thead>
      <tbody>
        ${main.map(row).join("")}
      </tbody>
    </table>
    ${
      hidden.length
        ? `<details class="diagnostics">
             <summary>Diagnostics / unsupported (${hidden.length})</summary>
             <table>
               <thead><tr><th>Name</th><th>Zone</th><th>Status</th><th>Bridgeable</th><th>Template</th></tr></thead>
               <tbody>${hidden.map(row).join("")}</tbody>
             </table>
           </details>`
        : ""
    }
  `);

  root.querySelectorAll("tr.device-row").forEach((tr) => {
    tr.addEventListener("click", () => showDetail(tr.dataset.id));
  });
}

// ---------------------------------------------------------------------
// Detail view - dispatch podle statusu
// ---------------------------------------------------------------------

async function showDetail(homeyId) {
  state.view = "detail";
  state.homeyId = homeyId;
  render("Načítám detail…");
  const detail = await api("GET", `/api/devices/${encodeURIComponent(homeyId)}`);
  state.detail = detail;
  state.form = {
    templateId:
      detail.template_match_kind === "exact" ? detail.matching_template_ids[0] : "",
    instanceName: detail.homey_name || "",
    loxoneNameBase: detail.homey_name || "",
    keyBase: "",
  };
  state.previewInstance = null;
  state.validateResult = null;
  state.lastValidatedInstanceJson = null;
  state.assignment = null;
  renderDetail();
}

function backLink() {
  return `<a class="back-link" id="back-to-list">&larr; zpět na seznam</a>`;
}

function bindBackLink() {
  document.getElementById("back-to-list").addEventListener("click", showList);
}

function renderDetail() {
  const d = state.detail;
  if (d.status === "missing") return renderMissingDetail();
  if (d.status === "configured") return renderConfiguredDetail();
  return renderNewDetail();
}

// ---------------------------------------------------------------------
// MISSING
// ---------------------------------------------------------------------

function renderMissingDetail() {
  const d = state.detail;
  render(`
    ${backLink()}
    <div class="notice notice-error">Device is not present in current Homey export.</div>
    <h2>${esc(d.instance ? d.instance.instance_name : d.homey_id)}</h2>
    ${d.instance ? instanceSummaryHtml(d.instance) : "<p>Žádná uložená instance.</p>"}
  `);
  bindBackLink();
}

// ---------------------------------------------------------------------
// CONFIGURED (read-only + volitelný assignment preview)
// ---------------------------------------------------------------------

function instanceSummaryHtml(instance) {
  return `
    <div class="card">
      <p><strong>Instance name:</strong> ${esc(instance.instance_name)}</p>
      <p><strong>Loxone name base:</strong> ${esc(instance.loxone_name_base)}</p>
      <p><strong>Key base:</strong> ${esc(instance.key_base)}</p>
      <p><strong>Enabled:</strong> ${boolCell(instance.enabled)}</p>
      <p><strong>Template:</strong> ${esc(instance.template_id || "–")}
         ${instance.template_version ? `(v${esc(instance.template_version)})` : ""}</p>
    </div>
    <div class="card">
      <h3>Role bindings</h3>
      <pre>${esc(JSON.stringify(instance.role_bindings, null, 2))}</pre>
      <h3>Keys</h3>
      <pre>${esc(JSON.stringify(instance.keys, null, 2))}</pre>
      <h3>Display names</h3>
      <pre>${esc(JSON.stringify(instance.display_names, null, 2))}</pre>
      <h3>Overrides</h3>
      <pre>${esc(JSON.stringify(instance.overrides, null, 2))}</pre>
    </div>
  `;
}

function renderConfiguredDetail() {
  const d = state.detail;
  const canOfferAssignment =
    !d.instance.template_id && d.matching_template_ids.length > 0;

  render(`
    ${backLink()}
    <h2>${esc(d.instance.instance_name)}</h2>
    <p>${esc(d.homey_name)} &middot; ${esc(d.zone_name || "")} &middot; ${esc(d.driver_id || "")}</p>
    ${instanceSummaryHtml(d.instance)}
    ${
      canOfferAssignment
        ? `<div class="card">
             <p>Instance nemá přiřazený template. Nalezené kandidáty:
               <strong>${d.matching_template_ids.map(esc).join(", ")}</strong>
               (${esc(d.template_match_kind)})</p>
             <select id="assign-template-select">
               ${d.matching_template_ids
                 .map((t) => `<option value="${esc(t)}">${esc(t)}</option>`)
                 .join("")}
             </select>
             <button id="btn-preview-assignment">Preview template assignment</button>
           </div>
           <div id="assignment-result"></div>`
        : ""
    }
  `);

  bindBackLink();

  const btn = document.getElementById("btn-preview-assignment");
  if (btn) {
    btn.addEventListener("click", async () => {
      const templateId = document.getElementById("assign-template-select").value;
      const assignment = await api(
        "POST",
        `/api/devices/${encodeURIComponent(state.homeyId)}/template-assignment/preview`,
        { template_id: templateId }
      );
      state.assignment = assignment;
      renderAssignmentResult();
    });
  }
}

function renderAssignmentResult() {
  const a = state.assignment.assignment;
  document.getElementById("assignment-result").innerHTML = `
    <div class="card">
      <h3>Preview: přiřazení template ${esc(state.assignment.template_id)}</h3>
      <p><strong>Template odpovídá zařízení:</strong> ${boolCell(a.template_matches_device)}</p>
      <p><strong>Missing instance capabilities</strong> (template zná, instance nemá):
        ${a.missing_instance_capabilities.length ? a.missing_instance_capabilities.map(esc).join(", ") : "žádné"}</p>
      <p><strong>Unmatched instance capabilities</strong> (instance má, template nezná):
        ${a.unmatched_instance_capabilities.length ? a.unmatched_instance_capabilities.map(esc).join(", ") : "žádné"}</p>
      <p><strong>Conflicts</strong> (existující role se liší od template - nikdy se tiše nepřepíše):</p>
      <pre>${esc(JSON.stringify(a.conflicts, null, 2))}</pre>
      <p><strong>Výsledné role_bindings po přiřazení:</strong></p>
      <pre>${esc(JSON.stringify(a.instance.role_bindings, null, 2))}</pre>
      <p><strong>Overrides proti template defaultům:</strong></p>
      <pre>${esc(JSON.stringify(a.instance.overrides, null, 2))}</pre>
      <p><em>Toto je jen náhled - nic se zatím neuložilo.</em></p>
    </div>
  `;
}

// ---------------------------------------------------------------------
// NEW
// ---------------------------------------------------------------------

function renderNewDetail() {
  const d = state.detail;

  const capRows = (d.raw_capabilities || [])
    .map(
      (c) => `
      <tr>
        <td>${esc(c.id)}</td>
        <td>${esc(c.type)}</td>
        <td>${boolCell(c.getable)}</td>
        <td>${boolCell(c.setable)}</td>
        <td>${boolCell(c.bridgeable)}</td>
      </tr>`
    )
    .join("");

  const templateField =
    d.matching_template_ids.length > 0
      ? `<select id="template-select">
           ${d.matching_template_ids
             .map(
               (t) =>
                 `<option value="${esc(t)}" ${t === state.form.templateId ? "selected" : ""}>${esc(t)}</option>`
             )
             .join("")}
         </select>`
      : `<input type="text" id="template-select" placeholder="template_id (žádný automatický kandidát)" />`;

  render(`
    ${backLink()}
    <h2>${esc(d.homey_name)}</h2>
    <p>Zone: ${esc(d.zone_name || "")} &middot; Class: ${esc(d.homey_class || "")} &middot; Driver: ${esc(d.driver_id || "")}</p>

    <div class="card">
      <h3>Homey capabilities</h3>
      <table>
        <thead><tr><th>id</th><th>type</th><th>getable</th><th>setable</th><th>bridgeable</th></tr></thead>
        <tbody>${capRows}</tbody>
      </table>
    </div>

    <div class="card">
      <h3>Matching templates</h3>
      <p>${
        d.matching_template_ids.length
          ? `${d.matching_template_ids.map(esc).join(", ")} (${esc(d.template_match_kind)})`
          : "žádný automatický kandidát nenalezen"
      }</p>

      <label for="instance-name">Instance name</label>
      <input type="text" id="instance-name" value="${esc(state.form.instanceName)}" />

      <label for="loxone-name-base">Loxone name base</label>
      <input type="text" id="loxone-name-base" value="${esc(state.form.loxoneNameBase)}" />

      <label for="key-base">Key base (volitelné)</label>
      <input type="text" id="key-base" value="${esc(state.form.keyBase)}" placeholder="odvodí se ze jména" />

      <label for="template-select">Template</label>
      ${templateField}

      <div>
        <button id="btn-preview">Preview</button>
      </div>
    </div>

    <div id="preview-area"></div>
  `);

  bindBackLink();

  document.getElementById("btn-preview").addEventListener("click", async () => {
    state.form.instanceName = document.getElementById("instance-name").value;
    state.form.loxoneNameBase = document.getElementById("loxone-name-base").value;
    state.form.keyBase = document.getElementById("key-base").value;
    state.form.templateId = document.getElementById("template-select").value;

    try {
      const preview = await api(
        "POST",
        `/api/devices/${encodeURIComponent(state.homeyId)}/preview`,
        {
          template_id: state.form.templateId,
          instance_name: state.form.instanceName,
          loxone_name_base: state.form.loxoneNameBase,
          key_base: state.form.keyBase || null,
        }
      );
      state.templateLabel = preview.template_label;
      state.previewInstance = preview.preview.instance;
      state.validateResult = null;
      state.lastValidatedInstanceJson = null;
      renderPreviewArea(preview.preview.unmapped_template_capabilities);
    } catch (err) {
      document.getElementById("preview-area").innerHTML =
        `<div class="notice notice-error">Preview selhal: ${esc(err.message)}</div>`;
    }
  });
}

function renderPreviewArea(unmapped) {
  const instance = state.previewInstance;
  const capIds = Object.keys(instance.keys.capabilities);

  const rows = capIds
    .map((capId) => {
      const role = instance.role_bindings.capabilities[capId] || "";
      const key = instance.keys.capabilities[capId] || "";
      const name = instance.display_names.capabilities[capId] || "";
      return `
        <tr data-cap="${esc(capId)}">
          <td>${esc(capId)}</td>
          <td><input type="text" class="edit-role" value="${esc(role)}" /></td>
          <td><input type="text" class="edit-key" value="${esc(key)}" /></td>
          <td><input type="text" class="edit-name" value="${esc(name)}" /></td>
        </tr>`;
    })
    .join("");

  document.getElementById("preview-area").innerHTML = `
    <div class="card">
      <h3>Preview (template: ${esc(state.templateLabel || state.form.templateId)})</h3>
      ${
        unmapped && unmapped.length
          ? `<p><em>Template navíc zná i: ${unmapped.map(esc).join(", ")} - na tomhle zařízení nedostupné.</em></p>`
          : ""
      }
      <table>
        <thead><tr><th>Homey capability</th><th>Role</th><th>Technical key</th><th>Loxone display name</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <button id="btn-validate">Validate</button>
      <button id="btn-save" disabled title="${state.readOnly ? "Zakázáno v read-only režimu" : "Nejdřív spusť Validate"}">Save</button>
      <div id="validate-result"></div>
      <div id="save-result"></div>
    </div>
  `;

  root.querySelectorAll("#preview-area tbody tr").forEach((tr) => {
    const capId = tr.dataset.cap;
    tr.querySelector(".edit-role").addEventListener("input", (e) => {
      instance.role_bindings.capabilities[capId] = e.target.value;
      invalidateValidation();
    });
    tr.querySelector(".edit-key").addEventListener("input", (e) => {
      instance.keys.capabilities[capId] = e.target.value;
      invalidateValidation();
    });
    tr.querySelector(".edit-name").addEventListener("input", (e) => {
      instance.display_names.capabilities[capId] = e.target.value;
      invalidateValidation();
    });
  });

  document.getElementById("btn-validate").addEventListener("click", onValidate);
  document.getElementById("btn-save").addEventListener("click", onSave);
}

function invalidateValidation() {
  state.validateResult = null;
  const saveBtn = document.getElementById("btn-save");
  if (saveBtn) saveBtn.disabled = true;
}

async function onValidate() {
  const resultDiv = document.getElementById("validate-result");
  resultDiv.innerHTML = "Validuji…";
  try {
    const result = await api(
      "POST",
      `/api/devices/${encodeURIComponent(state.homeyId)}/validate`,
      { instance: state.previewInstance, template_id: state.form.templateId }
    );
    state.validateResult = result;
    state.lastValidatedInstanceJson = JSON.stringify(state.previewInstance);

    const problemsHtml = result.problems
      .map(
        (p) =>
          `<li class="problem-${esc(p.severity)}">[${esc(p.severity)}] ${esc(p.code)}: ${esc(p.message)}</li>`
      )
      .join("");

    resultDiv.innerHTML = result.is_valid
      ? `<div class="notice notice-success">Validace OK.</div>${problemsHtml ? `<ul>${problemsHtml}</ul>` : ""}`
      : `<div class="notice notice-error">Validace selhala.</div><ul>${problemsHtml}</ul>`;

    // Save je povolený jen pokud validace právě teď prošla, od té
    // doby nedošlo k žádné další editaci (viz invalidateValidation),
    // a server neběží v read-only režimu. GUI stav ale není
    // bezpečnostní hranice - backend se stejně sám znovu ověří.
    document.getElementById("btn-save").disabled =
      state.readOnly || !result.is_valid;
  } catch (err) {
    resultDiv.innerHTML = `<div class="notice notice-error">Chyba validace: ${esc(err.message)}</div>`;
  }
}

async function onSave() {
  const resultDiv = document.getElementById("save-result");

  if (state.readOnly) {
    resultDiv.innerHTML = `<div class="notice notice-error">Server běží v read-only režimu - Save je zakázán.</div>`;
    return;
  }

  resultDiv.innerHTML = "Ukládám…";
  try {
    const result = await api(
      "POST",
      `/api/devices/${encodeURIComponent(state.homeyId)}/save`,
      { instance: state.previewInstance, template_id: state.form.templateId }
    );
    resultDiv.innerHTML = `<div class="notice notice-success">Uloženo: ${esc(result.saved_path)}</div>`;
    document.getElementById("btn-save").disabled = true;
    setTimeout(showList, 800);
  } catch (err) {
    const problems = (err.data && err.data.problems) || [];
    const problemsHtml = problems
      .map((p) => `<li class="problem-error">${esc(p.code)}: ${esc(p.message)}</li>`)
      .join("");
    resultDiv.innerHTML = `<div class="notice notice-error">Save selhal: ${esc(err.message)}</div><ul>${problemsHtml}</ul>`;
  }
}

// ---------------------------------------------------------------------

async function init() {
  try {
    const status = await api("GET", "/api/status");
    state.readOnly = !!status.read_only;
  } catch (err) {
    state.readOnly = false;
  }

  const banner = document.getElementById("readonly-banner");
  banner.hidden = !state.readOnly;

  showList();
}

init();

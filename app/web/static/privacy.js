(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  // innerHTML use pannala, textContent mattum
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function setStatus(text, kind) {
    $("status").textContent = text;
    $("status").className = "pill " + (kind || "");
  }

  async function api(path, options = {}) {
    const headers = { "X-Nova-Request": "1", ...(options.headers || {}) };
    const token = localStorage.getItem("nova.token") || "";
    if (token) headers["Authorization"] = "Bearer " + token;

    const response = await fetch(path, { ...options, headers });
    if (!response.ok) {
      let detail = response.statusText;
      try { detail = (await response.json()).detail || detail; } catch (error) { /* json illa */ }
      const hint = response.status === 401 ? " (Nova main page la ⚙ la token set pannu)" : "";
      throw new Error(`${response.status}: ${detail}${hint}`);
    }
    return response;
  }

  // ---------- Inventory + security ----------
  function protectionClass(value) {
    if (value === "encrypted") return "ok";
    if (value === "plaintext") return "bad";
    return value.startsWith("plain") ? "warn" : "";
  }

  function renderInventory(data) {
    const body = $("inventory").querySelector("tbody");
    body.replaceChildren();
    for (const row of data.stored) {
      const tr = el("tr");
      tr.appendChild(el("td", "", row.label));
      tr.appendChild(el("td", "", String(row.count)));
      tr.appendChild(el("td", "", row.where));
      tr.appendChild(el("td", protectionClass(row.protection), row.protection));
      body.appendChild(tr);
    }

    const sec = data.security;
    const list = $("security");
    list.replaceChildren();
    const key = sec.key.available
      ? `key: ${sec.key.source} (${sec.key.fingerprint})`
      : `KEY PROBLEM: ${sec.key.error}`;
    const lines = [
      `Encryption at rest: ${sec.encrypt_at_rest ? "ON" : "OFF"}`,
      key,
      `API token: ${sec.token_required ? "required" : "NOT set (localhost mattum)"}`,
      `Disabled skills: ${sec.disabled_skills.length ? sec.disabled_skills.join(", ") : "none"}`,
      `MLflow user text log: ${sec.mlflow_logs_text ? "ON" : "off"}`,
      `Audit log entries: ${data.audit.entries} (user text log: ${data.audit.logs_text ? "ON" : "off"})`,
    ];
    for (const line of lines) list.appendChild(el("li", "", line));
    $("offline").checked = sec.offline_mode;
  }

  async function loadInventory() {
    try {
      renderInventory(await (await api("/api/privacy/inventory")).json());
      setStatus("loaded", "ok");
    } catch (error) {
      setStatus(error.message, "bad");
    }
  }

  // ---------- Audit ----------
  async function loadAudit() {
    try {
      const data = await (await api("/api/security/audit?limit=40")).json();
      const lines = data.entries.map((e) => {
        const detail = Object.entries(e.detail || {}).map(([k, v]) => `${k}=${v}`).join(" ");
        return `#${e.seq} ${e.ts} ${e.event} [${e.actor}] ${detail}`;
      });
      $("audit").textContent = lines.join("\n") || "(Audit entries illa)";
    } catch (error) {
      $("audit").textContent = error.message;
    }
  }

  $("verify").addEventListener("click", async () => {
    $("verify-result").textContent = "checking...";
    try {
      const result = await (await api("/api/security/audit/verify")).json();
      $("verify-result").textContent = result.ok
        ? `OK: ${result.entries} entries, chain sariyaa irukku`
        : `BROKEN at line ${result.bad_line}: ${result.reason}`;
    } catch (error) {
      $("verify-result").textContent = error.message;
    }
  });
  $("refresh").addEventListener("click", () => { loadInventory(); loadAudit(); });

  // ---------- Offline toggle ----------
  $("offline").addEventListener("change", async (event) => {
    try {
      await api("/api/privacy/offline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: event.target.checked }),
      });
      loadAudit();
    } catch (error) {
      setStatus(error.message, "bad");
      event.target.checked = !event.target.checked;
    }
  });

  // ---------- Export ----------
  $("export").addEventListener("click", async () => {
    try {
      const blob = await (await api("/api/privacy/export")).blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "nova-export.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      loadAudit();
    } catch (error) {
      setStatus(error.message, "bad");
    }
  });

  // ---------- Delete ----------
  $("delete").addEventListener("click", async () => {
    const scopes = [...document.querySelectorAll("#scopes input:checked")].map((box) => box.value);
    const result = $("delete-result");
    if (!scopes.length) { result.textContent = "Edhavadhu onnu select pannu."; return; }
    if ($("confirm").value !== "DELETE") { result.textContent = "Confirm la DELETE nu type pannu."; return; }

    try {
      const data = await (await api("/api/privacy/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scopes, confirm: $("confirm").value }),
      })).json();
      result.textContent = "Deleted: " + Object.entries(data.deleted).map(([k, v]) => `${k}=${v}`).join(", ");
      $("confirm").value = "";
      document.querySelectorAll("#scopes input").forEach((box) => { box.checked = false; });
      loadInventory();
      loadAudit();
    } catch (error) {
      result.textContent = error.message;
    }
  });

  loadInventory();
  loadAudit();
})();
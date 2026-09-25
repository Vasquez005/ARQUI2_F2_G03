function toText(value) {
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

function escapeHtml(value) {
  return toText(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function fmtDate(value) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return toText(value);
  return d.toLocaleString();
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, options);
  let data = {};
  try {
    data = await res.json();
  } catch (_) {
    data = {};
  }
  if (!res.ok) {
    const detail = (data && data.detail) ? data.detail : `HTTP ${res.status}`;
    throw new Error(detail);
  }
  return data;
}

function setResult(el, payload) {
  if (!el) return;
  if (typeof payload === "string") {
    el.textContent = payload;
  } else {
    el.textContent = JSON.stringify(payload, null, 2);
  }
}

function initNaviera() {
  const root = document.getElementById("naviera-root");
  if (!root) return;

  const form = document.getElementById("naviera-form-manifiesto");
  const contenedor = document.getElementById("naviera-contenedor");
  const operacion = document.getElementById("naviera-operacion");
  const peso = document.getElementById("naviera-peso");
  const tolerancia = document.getElementById("naviera-tolerancia");
  const transportista = document.getElementById("naviera-transportista");
  const observaciones = document.getElementById("naviera-observaciones");
  const refreshBtn = document.getElementById("naviera-refresh");
  const result = document.getElementById("naviera-result");
  const tbodyManifiestos = document.querySelector("#naviera-table-manifiestos tbody");
  const tbodyContenedores = document.querySelector("#naviera-table-contenedores tbody");

  async function loadTransportistas() {
    const items = await apiFetch("/api/naviera/transportistas");
    transportista.innerHTML = "";
    (items || []).forEach((t) => {
      const opt = document.createElement("option");
      opt.value = t.id;
      opt.textContent = `${t.id} - ${t.nombre}`;
      transportista.appendChild(opt);
    });
  }

  function renderManifiestos(items) {
    tbodyManifiestos.innerHTML = "";
    if (!items.length) {
      tbodyManifiestos.innerHTML = "<tr><td colspan='8'>Sin manifiestos.</td></tr>";
      return;
    }
    items.forEach((m) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(m.id)}</td>
        <td>${escapeHtml(m.contenedorId)}</td>
        <td>${escapeHtml(m.tipoOperacion)}</td>
        <td>${escapeHtml(m.estadoDocumental)}</td>
        <td>${escapeHtml(m.canal)}</td>
        <td>${m.anulado ? "SI" : "NO"}</td>
        <td>${escapeHtml(fmtDate(m.createdAt))}</td>
        <td><button type="button" data-anular="${m.id}" ${m.anulado ? "disabled" : ""}>Anular</button></td>
      `;
      tbodyManifiestos.appendChild(tr);
    });
  }

  function renderContenedores(items) {
    tbodyContenedores.innerHTML = "";
    const map = new Map();
    items.forEach((m) => map.set(m.contenedorId, m));
    const values = Array.from(map.values());
    if (!values.length) {
      tbodyContenedores.innerHTML = "<tr><td colspan='5'>Sin contenedores.</td></tr>";
      return;
    }
    values.forEach((m) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(m.contenedorId)}</td>
        <td>${escapeHtml(m.tipoOperacion)}</td>
        <td>${escapeHtml(m.estadoDocumental)}</td>
        <td>${escapeHtml(m.canal)}</td>
        <td>#${escapeHtml(m.id)}</td>
      `;
      tbodyContenedores.appendChild(tr);
    });
  }

  async function loadManifiestos() {
    const items = await apiFetch("/api/naviera/manifiestos");
    renderManifiestos(items);
    renderContenedores(items);
  }

  tbodyManifiestos.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("button[data-anular]");
    if (!btn) return;
    const id = Number(btn.dataset.anular);
    if (!window.confirm(`Anular manifiesto #${id}?`)) return;
    try {
      const data = await apiFetch(`/api/naviera/manifiestos/${id}/anular`, { method: "POST" });
      setResult(result, data);
      await loadManifiestos();
    } catch (err) {
      setResult(result, `Error: ${err.message}`);
    }
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const payload = {
      contenedor_id: contenedor.value.trim(),
      tipo_operacion: operacion.value,
      peso_declarado_g: Number(peso.value),
      tolerancia_pct: Number(tolerancia.value),
      transportista_id: Number(transportista.value),
      observaciones: observaciones.value.trim() || null,
    };
    try {
      const data = await apiFetch("/api/naviera/manifiestos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setResult(result, data);
      form.reset();
      operacion.value = "DEPOSITO";
      peso.value = "1000";
      tolerancia.value = "5.0";
      await loadManifiestos();
    } catch (err) {
      setResult(result, `Error: ${err.message}`);
    }
  });

  refreshBtn.addEventListener("click", async () => {
    try {
      await loadManifiestos();
    } catch (err) {
      setResult(result, `Error: ${err.message}`);
    }
  });

  (async () => {
    try {
      await loadTransportistas();
      await loadManifiestos();
    } catch (err) {
      setResult(result, `Error inicial: ${err.message}`);
    }
  })();
}

function initAgente() {
  const root = document.getElementById("agente-root");
  if (!root) return;

  const form = document.getElementById("agente-form-declaracion");
  const manifiestoSel = document.getElementById("agente-manifiesto");
  const numero = document.getElementById("agente-numero");
  const regimen = document.getElementById("agente-regimen");
  const valor = document.getElementById("agente-valor");
  const descripcion = document.getElementById("agente-descripcion");
  const refreshBtn = document.getElementById("agente-refresh");
  const result = document.getElementById("agente-result");
  const seguimiento = document.getElementById("agente-seguimiento");
  const tbody = document.querySelector("#agente-table-pendientes tbody");
  let pendientes = [];

  function renderPendientes(items) {
    tbody.innerHTML = "";
    manifiestoSel.innerHTML = "";
    if (!items.length) {
      tbody.innerHTML = "<tr><td colspan='6'>Sin pendientes para agente.</td></tr>";
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "Sin pendientes";
      manifiestoSel.appendChild(opt);
      return;
    }
    items.forEach((m) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(m.id)}</td>
        <td>${escapeHtml(m.contenedorId)}</td>
        <td>${escapeHtml(m.tipoOperacion)}</td>
        <td>${escapeHtml(m.estadoDocumental)}</td>
        <td>${escapeHtml(m.canal)}</td>
        <td><button type="button" data-levante="${m.id}">Solicitar levante</button></td>
      `;
      tbody.appendChild(tr);

      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = `#${m.id} - ${m.contenedorId} (${m.estadoDocumental})`;
      manifiestoSel.appendChild(opt);
    });
  }

  async function loadPendientes() {
    pendientes = await apiFetch("/api/agente/declaraciones");
    renderPendientes(pendientes);
    setResult(seguimiento, pendientes);
  }

  tbody.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("button[data-levante]");
    if (!btn) return;
    const id = Number(btn.dataset.levante);
    try {
      const data = await apiFetch(`/api/agente/manifiestos/${id}/solicitar-levante`, { method: "POST" });
      setResult(result, data);
      await loadPendientes();
    } catch (err) {
      setResult(result, `Error: ${err.message}`);
    }
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const payload = {
      manifiesto_id: Number(manifiestoSel.value),
      numero_declaracion: numero.value.trim(),
      regimen: regimen.value,
      descripcion: descripcion.value.trim(),
      valor_declarado: Number(valor.value),
    };
    try {
      const data = await apiFetch("/api/agente/declaraciones", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setResult(result, data);
      form.reset();
      regimen.value = "importacion_definitiva";
      valor.value = "1000.00";
      await loadPendientes();
    } catch (err) {
      setResult(result, `Error: ${err.message}`);
    }
  });

  refreshBtn.addEventListener("click", async () => {
    try {
      await loadPendientes();
    } catch (err) {
      setResult(result, `Error: ${err.message}`);
    }
  });

  (async () => {
    try {
      await loadPendientes();
    } catch (err) {
      setResult(result, `Error inicial: ${err.message}`);
    }
  })();
}

function initAutoridad() {
  const root = document.getElementById("autoridad-root");
  if (!root) return;

  const refreshSolicitudes = document.getElementById("autoridad-refresh-solicitudes");
  const refreshRetenciones = document.getElementById("autoridad-refresh-retenciones");
  const refreshCarga = document.getElementById("autoridad-refresh-carga");
  const solicitudesResult = document.getElementById("autoridad-solicitudes-result");
  const retencionesResult = document.getElementById("autoridad-retenciones-result");
  const tbodySolicitudes = document.querySelector("#autoridad-table-solicitudes tbody");
  const tbodyRetenciones = document.querySelector("#autoridad-table-retenciones tbody");
  const tbodyCarga = document.querySelector("#autoridad-table-carga tbody");

  function renderSolicitudes(items) {
    tbodySolicitudes.innerHTML = "";
    if (!items.length) {
      tbodySolicitudes.innerHTML = "<tr><td colspan='6'>Sin solicitudes de levante.</td></tr>";
      return;
    }
    items.forEach((m) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(m.id)}</td>
        <td>${escapeHtml(m.contenedorId)}</td>
        <td>${escapeHtml(m.tipoOperacion)}</td>
        <td>${escapeHtml(m.estadoDocumental)}</td>
        <td>
          <select data-canal="${m.id}">
            <option value="verde">verde</option>
            <option value="rojo">rojo</option>
          </select>
        </td>
        <td>
          <button type="button" data-otorgar="${m.id}">Otorgar</button>
          <button type="button" data-retener="${m.id}">Retener</button>
        </td>
      `;
      tbodySolicitudes.appendChild(tr);
    });
  }

  function renderRetenciones(items) {
    tbodyRetenciones.innerHTML = "";
    if (!items.length) {
      tbodyRetenciones.innerHTML = "<tr><td colspan='6'>Sin retenciones RT03/RT05.</td></tr>";
      return;
    }
    items.forEach((r) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(r.id)}</td>
        <td>${escapeHtml(r.turnoId)}</td>
        <td>${escapeHtml(r.causa)}</td>
        <td>${escapeHtml(r.estado)}</td>
        <td>${escapeHtml(fmtDate(r.createdAt))}</td>
        <td>
          <button type="button" data-aclarar="${r.id}" ${r.estado !== "abierta" ? "disabled" : ""}>Aclarar</button>
          <button type="button" data-rechazar="${r.id}" ${r.estado !== "abierta" ? "disabled" : ""}>Rechazar</button>
        </td>
      `;
      tbodyRetenciones.appendChild(tr);
    });
  }

  function renderCarga(items) {
    tbodyCarga.innerHTML = "";
    if (!items.length) {
      tbodyCarga.innerHTML = "<tr><td colspan='6'>Sin carga registrada.</td></tr>";
      return;
    }
    items.forEach((m) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(m.id)}</td>
        <td>${escapeHtml(m.contenedorId)}</td>
        <td>${escapeHtml(m.tipoOperacion)}</td>
        <td>${escapeHtml(m.estadoDocumental)}</td>
        <td>${escapeHtml(m.canal)}</td>
        <td>${m.anulado ? "SI" : "NO"}</td>
      `;
      tbodyCarga.appendChild(tr);
    });
  }

  async function loadSolicitudes() {
    const data = await apiFetch("/api/autoridad/solicitudes");
    renderSolicitudes(data);
  }

  async function loadRetenciones() {
    const data = await apiFetch("/api/autoridad/retenciones");
    renderRetenciones(data);
  }

  async function loadCarga() {
    const data = await apiFetch("/api/autoridad/carga");
    renderCarga(data);
  }

  tbodySolicitudes.addEventListener("click", async (ev) => {
    const otorgarBtn = ev.target.closest("button[data-otorgar]");
    const retenerBtn = ev.target.closest("button[data-retener]");
    if (!otorgarBtn && !retenerBtn) return;

    try {
      if (otorgarBtn) {
        const id = Number(otorgarBtn.dataset.otorgar);
        const canalSel = tbodySolicitudes.querySelector(`select[data-canal="${id}"]`);
        const payload = { otorgar: true, canal: canalSel ? canalSel.value : "verde", motivo_retencion: null };
        const data = await apiFetch(`/api/autoridad/manifiestos/${id}/levante`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        setResult(solicitudesResult, data);
      } else if (retenerBtn) {
        const id = Number(retenerBtn.dataset.retener);
        const motivo = window.prompt("Motivo de retencion (obligatorio):", "");
        if (!motivo) {
          setResult(solicitudesResult, "Debes ingresar un motivo para retener.");
          return;
        }
        const payload = { otorgar: false, canal: null, motivo_retencion: motivo };
        const data = await apiFetch(`/api/autoridad/manifiestos/${id}/levante`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        setResult(solicitudesResult, data);
      }
      await Promise.all([loadSolicitudes(), loadRetenciones(), loadCarga()]);
    } catch (err) {
      setResult(solicitudesResult, `Error: ${err.message}`);
    }
  });

  tbodyRetenciones.addEventListener("click", async (ev) => {
    const aclararBtn = ev.target.closest("button[data-aclarar]");
    const rechazarBtn = ev.target.closest("button[data-rechazar]");
    if (!aclararBtn && !rechazarBtn) return;
    try {
      let id = 0;
      let payload = {};
      if (aclararBtn) {
        id = Number(aclararBtn.dataset.aclarar);
        payload = { resolucion: "aclarar", motivo: null, observacion: "Aclarada por autoridad" };
      } else {
        id = Number(rechazarBtn.dataset.rechazar);
        const motivo = window.prompt("Motivo obligatorio para rechazar:", "");
        if (!motivo) {
          setResult(retencionesResult, "Rechazar requiere motivo.");
          return;
        }
        payload = { resolucion: "rechazar", motivo, observacion: "Rechazo por autoridad" };
      }
      const data = await apiFetch(`/api/autoridad/retenciones/${id}/resolver`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setResult(retencionesResult, data);
      await Promise.all([loadRetenciones(), loadSolicitudes(), loadCarga()]);
    } catch (err) {
      setResult(retencionesResult, `Error: ${err.message}`);
    }
  });

  refreshSolicitudes.addEventListener("click", () => loadSolicitudes().catch((err) => setResult(solicitudesResult, `Error: ${err.message}`)));
  refreshRetenciones.addEventListener("click", () => loadRetenciones().catch((err) => setResult(retencionesResult, `Error: ${err.message}`)));
  refreshCarga.addEventListener("click", () => loadCarga().catch((err) => setResult(retencionesResult, `Error: ${err.message}`)));

  (async () => {
    try {
      await Promise.all([loadSolicitudes(), loadRetenciones(), loadCarga()]);
    } catch (err) {
      setResult(solicitudesResult, `Error inicial: ${err.message}`);
    }
  })();
}

initNaviera();
initAgente();
initAutoridad();

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

// El backend guarda UTC y lo manda sin zona ("2026-09-25T16:00:00"): sin la
// Z, el navegador lo tomaria como hora local y mostraria 6 h de diferencia.
function parseUtc(value) {
  if (!value) return null;
  const texto = String(value);
  const tieneZona = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(texto);
  const d = new Date(tieneZona ? texto : `${texto}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

function fmtDate(value) {
  if (!value) return "-";
  const d = parseUtc(value);
  if (!d) return toText(value);
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


// ════════════════════════ comunes a naviera, agente y autoridad ════════════════════════

function postJson(url, body) {
  return apiFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
}

function mensaje(el, texto, ok = true) {
  if (!el) return;
  el.textContent = texto;
  el.className = `resultado ${ok ? "ok" : "error"}`;
}

function llenarTabla(tabla, columnas, filas, filaHtml, vacio = "Sin datos.") {
  if (!tabla) return;
  const cuerpo = filas.length
    ? filas.map(filaHtml).join("")
    : `<tr><td colspan="${columnas.length}" class="muted">${vacio}</td></tr>`;
  tabla.innerHTML = `<thead><tr>${columnas.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>${cuerpo}</tbody>`;
  actualizarRelojesRol();
}

function duracion(segundos) {
  const s = Math.max(0, Math.floor(segundos));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${h} h ${m} min`;
}

// <span class="reloj-rol" data-desde="..."> muestra el reloj de permanencia en horas y minutos
function relojRol(desdeIso) {
  return desdeIso ? `<span class="reloj-rol" data-desde="${escapeHtml(desdeIso)}"></span>` : "-";
}

function actualizarRelojesRol() {
  document.querySelectorAll(".reloj-rol").forEach((el) => {
    const d = parseUtc(el.dataset.desde);
    if (d) el.textContent = duracion((Date.now() - d.getTime()) / 1000);
  });
}

const ESTADO_DOC = {
  declarado: "Declarado (sin levante)",
  declaracion_presentada: "Declaracion presentada",
  levante_solicitado: "Levante solicitado",
  levante_otorgado: "Levante otorgado",
  levante_retenido: "Levante retenido",
};

function autorizacion(m) {
  const canal = m.canal ? ` <span class="chip ${m.canal === "rojo" ? "chip-bad" : "chip-ok"}">canal ${escapeHtml(m.canal)}</span>` : "";
  return `${escapeHtml(ESTADO_DOC[m.estadoDocumental] || m.estadoDocumental)}${canal}`;
}

function initTabs(root) {
  const botones = Array.from(root.querySelectorAll(".tab-btn"));
  const paneles = Array.from(root.querySelectorAll(".tab-panel"));
  const activar = (tab) => {
    botones.forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
    paneles.forEach((p) => p.classList.toggle("hidden", p.dataset.tabPanel !== tab));
    if (window.location.hash !== `#${tab}`) window.history.replaceState(null, "", `#${tab}`);
    root.dispatchEvent(new CustomEvent("pestana", { detail: tab }));
  };
  botones.forEach((b) => b.addEventListener("click", () => activar(b.dataset.tab)));
  const inicial = (window.location.hash || "").replace("#", "");
  activar(botones.some((b) => b.dataset.tab === inicial) ? inicial : botones[0].dataset.tab);
  setInterval(actualizarRelojesRol, 30000);
}

function htmlDetalleManifiesto(d, { conDeclaracion = true } = {}) {
  const historial = (d.historial || []).map((h) => {
    const valores = Object.entries(h.valores || {}).filter(([, v]) => v !== null && v !== "")
      .map(([k, v]) => `${k}: ${v}`).join(", ");
    return `<tr><td>${escapeHtml(fmtDate(h.ts))}</td><td><span class="chip">${escapeHtml(h.origen)}</span></td>
      <td>${h.tipo === "observacion" ? "<strong>Observacion:</strong> " : ""}${escapeHtml(h.descripcion)}</td>
      <td><small>${escapeHtml(valores)}</small></td></tr>`;
  }).join("") || "<tr><td colspan='4'>Sin eventos.</td></tr>";
  const decl = d.declaracion;
  const declaracion = !conDeclaracion ? "" : decl
    ? `<h3>Declaracion de mercancias</h3>
       <table class="data-table"><tr><th>Numero</th><td>${escapeHtml(decl.numero)}</td><th>Regimen</th><td>${escapeHtml(decl.regimen)}</td></tr>
       <tr><th>Valor declarado</th><td>${escapeHtml(decl.valorDeclarado)}</td><th>Agente</th><td>${escapeHtml(decl.agente)}</td></tr>
       <tr><th>Descripcion</th><td colspan="3">${escapeHtml(decl.descripcion)}</td></tr></table>`
    : "<p class='muted'>Aun no hay declaracion presentada.</p>";
  const turnos = (d.turnos || []).map((t) => `${t.id} (${escapeHtml(t.estado)})`).join(", ") || "-";
  return `<h2>Manifiesto ${d.id} - ${escapeHtml(d.contenedorId)}</h2>
    <table class="data-table">
      <tr><th>Operacion</th><td>${escapeHtml(d.tipoOperacion)}</td><th>Naviera</th><td>${escapeHtml(d.navieraNombre)}</td></tr>
      <tr><th>Peso declarado</th><td>${escapeHtml(d.pesoDeclaradoG)} g${d.pesoDeclaradoAnteriorG ? ` <small>(anterior: ${escapeHtml(d.pesoDeclaradoAnteriorG)} g)</small>` : ""}</td>
          <th>Tolerancia</th><td>${escapeHtml(d.toleranciaPct)} %</td></tr>
      <tr><th>Transportista</th><td>${escapeHtml(d.transportistaNombre)}</td><th>Tarjeta RFID</th><td>${escapeHtml(d.vehiculoUid)}</td></tr>
      <tr><th>Autorizacion</th><td>${autorizacion(d)}${d.motivoLevante ? `<br><small>Motivo: ${escapeHtml(d.motivoLevante)}</small>` : ""}</td>
          <th>Estado operativo</th><td>${escapeHtml(d.estadoOperativo)} | ${escapeHtml(d.ubicacion)}</td></tr>
      <tr><th>Observaciones</th><td colspan="3">${escapeHtml(d.observaciones)}</td></tr>
      <tr><th>Turnos</th><td colspan="3">${turnos}</td></tr>
    </table>
    ${declaracion}
    <h3>Historial</h3>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>Fecha</th><th>Origen</th><th>Evento</th><th>Valores</th></tr></thead>
    <tbody>${historial}</tbody></table></div>`;
}

async function abrirDetalle(url, opciones) {
  const dlg = document.getElementById("dlg-rol");
  const body = document.getElementById("dlg-rol-body");
  body.textContent = "Cargando...";
  dlg.showModal();
  try {
    body.innerHTML = htmlDetalleManifiesto(await apiFetch(url), opciones);
  } catch (err) {
    body.textContent = `Error: ${err.message}`;
  }
}

// ════════════════════════ NAVIERA (sec. 5.1 y 5.2) ════════════════════════

function initNaviera() {
  const root = document.getElementById("naviera-root");
  if (!root) return;
  const $ = (id) => document.getElementById(id);
  const form = $("naviera-form-manifiesto");
  const result = $("naviera-result");

  async function cargarFormulario() {
    const [transportistas, catalogo] = await Promise.all([
      apiFetch("/api/naviera/transportistas"), apiFetch("/api/naviera/catalogo")]);
    $("naviera-transportista").innerHTML = transportistas
      .map((t) => `<option value="${t.id}">${escapeHtml(t.nombre)}</option>`).join("");
    $("naviera-catalogo").innerHTML = catalogo.map((c) => `<option value="${escapeHtml(c.contenedorId)}"></option>`).join("");
  }

  async function cargarManifiestos() {
    try {
      const items = await apiFetch("/api/naviera/manifiestos");
      llenarTabla($("naviera-table-manifiestos"),
        ["Id", "Contenedor", "Operacion", "Peso declarado", "Tolerancia", "Estado documental", "Estado operativo", "Acciones"],
        items, (m) => {
          const anulable = !m.anulado && !(m.estadoOperativo || "").startsWith("Turno") && m.estadoOperativo !== "En patio";
          return `<tr>
            <td>${m.id}</td><td>${escapeHtml(m.contenedorId)}</td><td>${escapeHtml(m.tipoOperacion)}</td>
            <td>${escapeHtml(m.pesoDeclaradoG)} g</td><td>${escapeHtml(m.toleranciaPct)} %</td>
            <td>${autorizacion(m)}</td><td>${escapeHtml(m.anulado ? "Anulado" : m.estadoOperativo)}</td>
            <td class="acciones"><button type="button" data-detalle="${m.id}">Ver detalle</button>
              <button type="button" data-anular="${m.id}" class="btn-warn" ${anulable ? "" : "disabled"}
                title="${anulable ? "" : "Solo sin turno asociado"}">Anular</button></td></tr>`;
        }, "Aun no declaraste manifiestos.");
    } catch (err) {
      mensaje(result, `Error: ${err.message}`, false);
    }
  }

  async function cargarContenedores() {
    const f = new FormData($("naviera-filtros"));
    const qs = new URLSearchParams(Array.from(f.entries()).filter(([, v]) => v)).toString();
    try {
      const items = await apiFetch(`/api/naviera/contenedores?${qs}`);
      llenarTabla($("naviera-table-contenedores"),
        ["Contenedor", "Operacion", "Estado", "Ubicacion actual", "Autorizacion vigente", "Permanencia"],
        items, (c) => `<tr><td>${escapeHtml(c.contenedorId)}</td><td>${escapeHtml(c.tipoOperacion)}</td>
          <td>${escapeHtml(c.estadoOperativo)}</td><td>${escapeHtml(c.ubicacion)}</td><td>${autorizacion(c)}</td>
          <td>${relojRol(c.enPatioDesde)}</td></tr>`, "Sin contenedores.");
    } catch (err) {
      mensaje(result, `Error: ${err.message}`, false);
    }
  }

  $("naviera-nuevo").addEventListener("click", () => form.classList.toggle("hidden"));
  $("naviera-cancelar").addEventListener("click", () => form.classList.add("hidden"));
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const tolerancia = $("naviera-tolerancia").value;
    const payload = {
      contenedor_id: $("naviera-contenedor").value.trim().toUpperCase(),
      tipo_operacion: $("naviera-operacion").value,
      peso_declarado_g: Number($("naviera-peso").value),
      tolerancia_pct: tolerancia === "" ? null : Number(tolerancia),
      transportista_id: Number($("naviera-transportista").value),
      vehiculo_uid: $("naviera-rfid").value.trim() || null,
      observaciones: $("naviera-observaciones").value.trim() || null,
    };
    try {
      const r = await postJson("/api/naviera/manifiestos", payload);
      mensaje(result, `Manifiesto ${r.id} declarado para ${payload.contenedor_id}.`);
      form.reset();
      form.classList.add("hidden");
      cargarManifiestos();
    } catch (err) {
      mensaje(result, `Rechazado: ${err.message}`, false);
    }
  });

  root.addEventListener("click", async (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    if (b.dataset.detalle) abrirDetalle(`/api/naviera/manifiestos/${b.dataset.detalle}`);
    if (b.dataset.anular) {
      if (!window.confirm(`Anular el manifiesto ${b.dataset.anular}?`)) return;
      try {
        await postJson(`/api/naviera/manifiestos/${b.dataset.anular}/anular`);
        mensaje(result, `Manifiesto ${b.dataset.anular} anulado.`);
        cargarManifiestos();
      } catch (err) {
        mensaje(result, `Rechazado: ${err.message}`, false);
      }
    }
  });
  $("naviera-filtros").addEventListener("submit", (ev) => { ev.preventDefault(); cargarContenedores(); });
  root.addEventListener("pestana", (ev) => (ev.detail === "contenedores" ? cargarContenedores() : cargarManifiestos()));

  cargarFormulario().catch((err) => mensaje(result, `Error: ${err.message}`, false));
  initTabs(root);
}

// ════════════════════════ AGENTE (sec. 5.3 y 5.4) ════════════════════════

function initAgente() {
  const root = document.getElementById("agente-root");
  if (!root) return;
  const $ = (id) => document.getElementById(id);
  const result = $("agente-result");
  let manifiestoDeclarando = null;

  async function cargarPendientes() {
    try {
      const items = await apiFetch("/api/agente/declaraciones");
      llenarTabla($("agente-table-pendientes"),
        ["Manifiesto", "Contenedor", "Naviera", "Operacion", "Peso declarado", "Estado", "Acciones"],
        items, (m) => `<tr>
          <td>${m.id}</td><td>${escapeHtml(m.contenedorId)}</td><td>${escapeHtml(m.navieraNombre)}</td>
          <td>${escapeHtml(m.tipoOperacion)}</td><td>${escapeHtml(m.pesoDeclaradoG)} g</td><td>${autorizacion(m)}</td>
          <td class="acciones">
            <button type="button" data-declarar="${m.id}" data-contenedor="${escapeHtml(m.contenedorId)}"
              ${m.estadoDocumental === "declarado" ? "" : "disabled"}>Presentar declaracion</button>
            <button type="button" data-levante="${m.id}" ${m.estadoDocumental === "declaracion_presentada" ? "" : "disabled"}
              title="Solo con la declaracion presentada">Solicitar levante</button>
            <button type="button" data-observar="${m.id}">Adjuntar observacion</button>
          </td></tr>`, "No hay manifiestos pendientes de levante.");
    } catch (err) {
      mensaje(result, `Error: ${err.message}`, false);
    }
  }

  const SITUACION = { pendiente: "", autorizada: "chip-ok", retenida: "chip-bad" };

  async function cargarSeguimiento() {
    const f = new FormData($("agente-filtros"));
    const qs = new URLSearchParams(Array.from(f.entries()).filter(([, v]) => v)).toString();
    try {
      const items = await apiFetch(`/api/agente/seguimiento?${qs}`);
      llenarTabla($("agente-table-seguimiento"),
        ["Declaracion", "Contenedor", "Naviera", "Estado", "Canal", "Motivo de retencion", "Presentada"],
        items, (d) => `<tr><td>${escapeHtml(d.numeroDeclaracion)}</td><td>${escapeHtml(d.contenedorId)}</td>
          <td>${escapeHtml(d.naviera)}</td><td><span class="chip ${SITUACION[d.situacion]}">${escapeHtml(d.situacion)}</span></td>
          <td>${escapeHtml(d.canal)}</td><td>${escapeHtml(d.motivoRetencion)}</td><td>${escapeHtml(fmtDate(d.createdAt))}</td></tr>`,
        "Sin solicitudes.");
    } catch (err) {
      mensaje(result, `Error: ${err.message}`, false);
    }
  }

  $("agente-form-declaracion").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    try {
      await postJson("/api/agente/declaraciones", {
        manifiesto_id: manifiestoDeclarando,
        numero_declaracion: f.get("numero_declaracion").trim(),
        regimen: f.get("regimen"),
        descripcion: f.get("descripcion").trim(),
        valor_declarado: Number(f.get("valor_declarado")),
      });
      ev.target.reset();
      $("dlg-declaracion").close();
      mensaje(result, `Declaracion presentada para el manifiesto ${manifiestoDeclarando}.`);
      cargarPendientes();
    } catch (err) {
      mensaje(result, `Rechazado: ${err.message}`, false);
      $("dlg-declaracion").close();
    }
  });

  root.addEventListener("click", async (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    try {
      if (b.dataset.declarar) {
        manifiestoDeclarando = Number(b.dataset.declarar);
        $("dlg-declaracion-titulo").textContent = `Presentar declaracion - ${b.dataset.contenedor}`;
        $("dlg-declaracion").showModal();
      }
      if (b.dataset.levante) {
        await postJson(`/api/agente/manifiestos/${b.dataset.levante}/solicitar-levante`);
        mensaje(result, `Levante solicitado para el manifiesto ${b.dataset.levante}.`);
        cargarPendientes();
      }
      if (b.dataset.observar) {
        const texto = window.prompt("Observacion para la autoridad:", "");
        if (!texto || !texto.trim()) return;
        await postJson(`/api/agente/manifiestos/${b.dataset.observar}/observaciones`, { texto });
        mensaje(result, `Observacion adjuntada al manifiesto ${b.dataset.observar}.`);
      }
    } catch (err) {
      mensaje(result, `Rechazado: ${err.message}`, false);
    }
  });
  $("agente-refresh").addEventListener("click", cargarPendientes);
  $("agente-filtros").addEventListener("submit", (ev) => { ev.preventDefault(); cargarSeguimiento(); });
  root.addEventListener("pestana", (ev) => (ev.detail === "seguimiento" ? cargarSeguimiento() : cargarPendientes()));
  initTabs(root);
}

// ════════════════════════ AUTORIDAD (sec. 5.5, 5.6 y 5.7) ════════════════════════

function initAutoridad() {
  const root = document.getElementById("autoridad-root");
  if (!root) return;
  const $ = (id) => document.getElementById(id);
  const result = $("autoridad-result");

  async function cargarSolicitudes() {
    try {
      const items = await apiFetch("/api/autoridad/solicitudes");
      llenarTabla($("autoridad-table-solicitudes"),
        ["Manifiesto", "Contenedor", "Naviera", "Agente", "Declaracion", "Peso declarado", "Canal", "Acciones"],
        items, (m) => `<tr>
          <td>${m.id}</td><td>${escapeHtml(m.contenedorId)}</td><td>${escapeHtml(m.navieraNombre)}</td>
          <td>${escapeHtml(m.agenteNombre)}</td><td>${escapeHtml(m.numeroDeclaracion)}</td><td>${escapeHtml(m.pesoDeclaradoG)} g</td>
          <td><select data-canal="${m.id}"><option value="">Elegir canal</option>
            <option value="verde">Verde</option><option value="rojo">Rojo</option></select></td>
          <td class="acciones"><button type="button" data-otorgar="${m.id}">Otorgar levante</button>
            <button type="button" data-retener="${m.id}" class="btn-warn">Retener</button>
            <button type="button" data-declaracion="${m.id}">Ver declaracion</button></td></tr>`,
        "No hay solicitudes pendientes.");
    } catch (err) {
      mensaje(result, `Error: ${err.message}`, false);
    }
  }

  async function cargarRetenciones() {
    const estado = $("autoridad-ret-estado").value;
    try {
      const items = (await apiFetch("/api/autoridad/retenciones")).filter((r) => !estado || r.estado === estado);
      llenarTabla($("autoridad-table-retenciones"),
        ["Id", "Turno / vehiculo", "Contenedor", "Causa", "Momento", "Plaza", "Tiempo", "Rol facultado", "Resolucion"],
        items, (r) => {
          const fin = r.resolvedAt ? parseUtc(r.resolvedAt) : new Date();
          const tiempo = duracion((fin.getTime() - parseUtc(r.createdAt).getTime()) / 1000);
          const acciones = r.estado === "abierta"
            ? `<button type="button" data-aclarar="${r.id}">Aclarar</button>
               <button type="button" data-rechazar="${r.id}" class="btn-warn">Rechazar</button>`
            : `${escapeHtml(r.resolucion)}${r.motivo ? `: ${escapeHtml(r.motivo)}` : ""}`;
          return `<tr><td>${r.id}</td><td>Turno ${r.turnoId}<br>${escapeHtml(r.vehiculoUid)}</td><td>${escapeHtml(r.contenedorId)}</td>
            <td><strong>${escapeHtml(r.causa)}</strong></td><td>${escapeHtml(r.estacion)}<br><small>${escapeHtml(fmtDate(r.createdAt))}</small></td>
            <td>${escapeHtml(r.plaza)}</td><td>${tiempo}</td><td>${escapeHtml(r.rolFacultado)}</td><td class="acciones">${acciones}</td></tr>`;
        }, "Sin retenciones aduaneras.");
    } catch (err) {
      mensaje(result, `Error: ${err.message}`, false);
    }
  }

  async function cargarCarga() {
    const f = new FormData($("autoridad-filtros"));
    const qs = new URLSearchParams(Array.from(f.entries()).filter(([, v]) => v)).toString();
    try {
      const items = await apiFetch(`/api/autoridad/carga?${qs}`);
      llenarTabla($("autoridad-table-carga"),
        ["Contenedor", "Naviera", "Estado", "Ubicacion", "Autorizacion", "Permanencia", ""],
        items, (c) => `<tr><td>${escapeHtml(c.contenedorId)}</td><td>${escapeHtml(c.naviera)}</td>
          <td>${escapeHtml(c.estadoOperativo)}</td><td>${escapeHtml(c.ubicacion)}</td><td>${autorizacion(c)}</td>
          <td>${relojRol(c.enPatioDesde)}</td>
          <td><button type="button" data-declaracion="${c.manifiestoId}">Ver detalle</button></td></tr>`,
        "Sin carga que coincida.");
    } catch (err) {
      mensaje(result, `Error: ${err.message}`, false);
    }
  }

  root.addEventListener("click", async (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    try {
      if (b.dataset.declaracion) return abrirDetalle(`/api/autoridad/manifiestos/${b.dataset.declaracion}`);
      if (b.dataset.otorgar) {
        const canal = root.querySelector(`select[data-canal="${b.dataset.otorgar}"]`).value;
        if (!canal) return mensaje(result, "Elige el canal de selectivo antes de otorgar el levante.", false);
        if (!window.confirm(`Otorgar el levante del manifiesto ${b.dataset.otorgar} con canal ${canal}?`)) return;
        await postJson(`/api/autoridad/manifiestos/${b.dataset.otorgar}/levante`, { otorgar: true, canal });
        mensaje(result, `Levante otorgado (canal ${canal}).`);
        cargarSolicitudes();
      }
      if (b.dataset.retener) {
        const motivo = window.prompt("Causa de la retencion del levante (obligatoria):", "");
        if (!motivo || !motivo.trim()) return;
        await postJson(`/api/autoridad/manifiestos/${b.dataset.retener}/levante`, { otorgar: false, motivo_retencion: motivo });
        mensaje(result, "Levante retenido; se aviso al transportista.");
        cargarSolicitudes();
      }
      if (b.dataset.aclarar) {
        const observacion = window.prompt("Aclarar: el turno continua. Observacion opcional:", "");
        if (observacion === null) return;
        await postJson(`/api/autoridad/retenciones/${b.dataset.aclarar}/resolver`,
          { resolucion: "aclarar", observacion: observacion || null });
        cargarRetenciones();
      }
      if (b.dataset.rechazar) {
        const motivo = window.prompt("Rechazar: se anula el turno. Motivo (obligatorio):", "");
        if (!motivo || !motivo.trim()) return;
        await postJson(`/api/autoridad/retenciones/${b.dataset.rechazar}/resolver`, { resolucion: "rechazar", motivo });
        cargarRetenciones();
      }
    } catch (err) {
      mensaje(result, `Rechazado: ${err.message}`, false);
    }
  });
  $("autoridad-refresh-solicitudes").addEventListener("click", cargarSolicitudes);
  $("autoridad-refresh-retenciones").addEventListener("click", cargarRetenciones);
  $("autoridad-ret-estado").addEventListener("change", cargarRetenciones);
  $("autoridad-filtros").addEventListener("submit", (ev) => { ev.preventDefault(); cargarCarga(); });
  root.addEventListener("pestana", (ev) => {
    if (ev.detail === "retenciones") cargarRetenciones();
    else if (ev.detail === "carga") cargarCarga();
    else cargarSolicitudes();
  });
  initTabs(root);
}

initNaviera();
initAgente();
initAutoridad();

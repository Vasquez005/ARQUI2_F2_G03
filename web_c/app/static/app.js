// Interfaz TERMINAL (Fase_2_PORTUS.md sec. 4). Usa los ayudantes de roles.js
// (escapeHtml, fmtDate, parseUtc, apiFetch).
//
// Tiempo real sin polling (sec. 4.1): todo lo que cambia llega por el
// WebSocket /ws/terminal, que reenvia MQTT:
//   portus/evt/#          -> estado fisico de las placas (garita, pesaje, salida, grua, latidos)
//   portus/cmd/respuesta  -> ACK/REJ de cada comando
//   portus/srv/alarma     -> alarma nueva generada por el backend
//   portus/srv/cambio     -> cambio de un turno, retencion, plaza, posicion o intento
// Ante un portus/srv/cambio se vuelve a pedir SOLO lo que cambio. El unico
// temporizador redibuja relojes y la antiguedad del enlace; no consulta nada.
(function () {
  const wsUrl = window.PORTUS_WS_URL;
  if (!wsUrl) return;

  const $ = (id) => document.getElementById(id);
  const DISPOSITIVOS = ["UNO_ENTRADA", "UNO_SALIDA", "MEGA_GRUA"];
  const UMBRAL_ENLACE_MS = 15000; // 3 latidos de 5 s (sec. 10.2)
  const DOS_HORAS_S = 2 * 3600;
  const FINALES = ["Cerrado", "Anulado"];

  // enum EstadoGrua del Mega (PORTUS_Fase1_v2.ino) -> estado del sinoptico
  const ESTADOS_GRUA = [
    ["Referenciando", "movimiento"], ["En reposo", "ok"], ["Desplazandose", "movimiento"],
    ["Izando", "movimiento"], ["Izando", "movimiento"], ["Izando", "movimiento"],
    ["Trasladando", "movimiento"], ["Depositando", "movimiento"], ["Depositando", "movimiento"],
    ["Depositando", "movimiento"], ["Desplazandose", "movimiento"], ["Desplazandose", "movimiento"],
    ["En reposo", "ok"], ["En falla", "bad"],
  ];

  const st = {
    dev: Object.fromEntries(DISPOSITIVOS.map((d) => [d, { ultimo: null, hb: {} }])),
    garita: { estado: "Libre", clase: "idle", uid: null, detalle: "" },
    talanquera: { estado: null, moviendo: false },
    pesaje: { estado: "Libre", clase: "idle", uid: null },
    aguja: { estado: null, clase: "idle" },
    salida: { estado: null, moviendo: false, garita: "Libre", uid: null, detalle: "" },
    grua: { estado: null, pos: null, suspendida: false, mantenimiento: false },
    turnosActivos: [],
    parqueo: [],
    patio: [],
    alarmasActivas: 0,
    eventosGrua: [],
  };

  // ════════════════════════ utilidades ════════════════════════

  function fmtHora(d) {
    return d ? d.toLocaleTimeString() : "-";
  }

  function fmtDur(segundos) {
    if (segundos === null || segundos === undefined) return "-";
    const s = Math.max(0, Math.floor(segundos));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return h ? `${h} h ${m} min` : `${m} min ${s % 60} s`;
  }

  function gramos(v) {
    return v === null || v === undefined ? "-" : `${v} g`;
  }

  // <span class="reloj" data-desde="iso"> se redibuja cada segundo
  function reloj(desdeIso, hastaIso) {
    if (!desdeIso) return "-";
    const hasta = hastaIso ? ` data-hasta="${escapeHtml(hastaIso)}"` : "";
    return `<span class="reloj" data-desde="${escapeHtml(desdeIso)}"${hasta}></span>`;
  }

  function actualizarRelojes() {
    const ahora = Date.now();
    document.querySelectorAll(".reloj").forEach((el) => {
      const desde = parseUtc(el.dataset.desde);
      if (!desde) return;
      const fin = el.dataset.hasta ? parseUtc(el.dataset.hasta) : null;
      const s = ((fin ? fin.getTime() : ahora) - desde.getTime()) / 1000;
      el.textContent = fmtDur(s);
      if (el.dataset.limite) el.closest("tr")?.classList.toggle("fila-excedida", s > Number(el.dataset.limite));
    });
  }

  function tabla(el, columnas, filas, filaHtml, vacio = "Sin datos.") {
    if (!el) return;
    const thead = `<thead><tr>${columnas.map((c) => `<th>${c}</th>`).join("")}</tr></thead>`;
    const cuerpo = filas.length
      ? filas.map(filaHtml).join("")
      : `<tr><td colspan="${columnas.length}" class="muted">${vacio}</td></tr>`;
    el.innerHTML = `${thead}<tbody>${cuerpo}</tbody>`;
    actualizarRelojes();
  }

  function toast(texto, clase = "") {
    const cont = $("toasts");
    if (!cont) return;
    const div = document.createElement("div");
    div.className = `toast ${clase}`;
    div.textContent = texto;
    cont.appendChild(div);
    setTimeout(() => div.remove(), 6000);
  }

  async function accion(promesa, exito) {
    try {
      const r = await promesa;
      if (exito) toast(exito, "toast-ok");
      return r;
    } catch (err) {
      toast(`Rechazado por el servidor: ${err.message}`, "toast-bad");
      return null;
    }
  }

  function post(url, body) {
    return apiFetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
  }

  function turnoPorUid(uid) {
    return st.turnosActivos.find((t) => t.vehiculoUid === uid) || null;
  }

  function chipVehiculo(uid) {
    if (!uid) return "";
    const t = turnoPorUid(uid);
    const titulo = t ? `Turno ${t.id} - ver detalle` : "Sin turno activo";
    return `<button type="button" class="vehiculo${t ? "" : " sin-turno"}" data-vehiculo="${escapeHtml(uid)}"
      title="${titulo}">${escapeHtml(uid)}</button>`;
  }

  // ════════════════════════ estado fisico (eventos MQTT) ════════════════════════

  function setTalanquera(obj, nuevo) {
    if (!nuevo || obj.estado === nuevo) return;
    const habia = obj.estado !== null;
    obj.estado = nuevo;
    if (!habia) return;
    obj.moviendo = true; // el servo tarda: se muestra "En movimiento" un momento
    setTimeout(() => { obj.moviendo = false; renderSinoptico(); }, 1200);
  }

  const PESAJE_HB = {
    libre: ["Libre", "idle"], en_camino: ["Midiendo", "movimiento"],
    aprobado: ["Medicion valida", "ok"], rechazado: ["Fuera de tolerancia", "bad"],
  };

  function aplicarEvento(topic, msg, enVivo) {
    if (!msg || typeof msg !== "object") return;
    const d = msg.data || {};
    const origen = msg.origin;
    const ts = msg.ts ? new Date(msg.ts * 1000) : new Date();

    if (st.dev[origen]) {
      const dev = st.dev[origen];
      if (!dev.ultimo || ts > dev.ultimo) dev.ultimo = ts;
    }

    if (topic === "portus/evt/estado" && st.dev[origen]) {
      st.dev[origen].hb = d;
      if (origen === "UNO_ENTRADA") {
        setTalanquera(st.talanquera, d.barra);
        const p = PESAJE_HB[d.pesaje];
        if (p && (p[0] !== st.pesaje.estado)) Object.assign(st.pesaje, { estado: p[0], clase: p[1] });
        if (d.pesaje === "libre") st.pesaje.uid = null;
      }
      if (origen === "UNO_SALIDA") setTalanquera(st.salida, d.barra);
      if (origen === "MEGA_GRUA") {
        st.grua.estado = Number(d.estado);
        st.grua.suspendida = d.suspendida === "1";
        st.grua.mantenimiento = d.mantenimiento === "1";
      }
    }

    if (topic === "portus/evt/garita") {
      const g = st.garita;
      if (d.evento === "rfid") Object.assign(g, { estado: "Validando", clase: "movimiento", uid: d.uid, detalle: "" });
      if (d.evento === "autorizado") {
        Object.assign(g, { estado: "Autorizada", clase: "ok", uid: d.uid, detalle: d.op || "" });
        setTalanquera(st.talanquera, "abierta");
      }
      if (d.evento === "rechazado") {
        const quien = d.decision === "local" ? " (decidio la garita)" : "";
        Object.assign(g, { estado: "Rechazada", clase: "bad", uid: d.uid, detalle: `${d.motivo || ""}${quien}` });
      }
      if ((d.evento || "").startsWith("barra_abajo")) {
        setTalanquera(st.talanquera, "cerrada");
        Object.assign(g, { estado: "Libre", clase: "idle", uid: null, detalle: "" });
      }
      if (d.estado === "iniciando") Object.assign(g, { estado: "Libre", clase: "idle", uid: null, detalle: "Reinicio" });
    }

    if (topic === "portus/evt/pesaje") {
      const p = st.pesaje;
      if (d.evento === "en_camino") Object.assign(p, { estado: "Midiendo", clase: "movimiento", uid: d.uid });
      if (d.evento === "meseta") {
        const ok = d.resultado === "ok";
        Object.assign(p, { estado: ok ? "Medicion valida" : "Fuera de tolerancia", clase: ok ? "ok" : "bad", uid: d.uid });
        Object.assign(st.aguja, ok ? { estado: "Recta (a transferencia)", clase: "ok" } : { estado: "Hacia parqueo", clase: "warn" });
      }
      if (d.evento === "aguja_abajo" || d.evento === "fin_rechazo") {
        Object.assign(p, { estado: "Libre", clase: "idle", uid: null });
        Object.assign(st.aguja, { estado: "Recta (a transferencia)", clase: "idle" });
      }
    }

    if (topic === "portus/evt/salida") {
      const s = st.salida;
      if (d.evento === "rfid_salida") Object.assign(s, { garita: "Validando", uid: d.uid, detalle: "" });
      if (d.evento === "salida_autorizada") {
        Object.assign(s, { garita: "Autorizada", uid: d.uid, detalle: d.decision === "local" ? "decidio la garita" : "" });
        setTalanquera(s, "abierta");
      }
      if (d.evento === "rechazado") Object.assign(s, { garita: "Rechazada", uid: d.uid, detalle: d.motivo || "" });
      if (d.evento === "salida_completada") {
        setTalanquera(s, "cerrada");
        Object.assign(s, { garita: "Libre", uid: null, detalle: "" });
      }
    }

    if (topic === "portus/evt/grua") {
      if (d.estado !== undefined && d.estado !== "boot") st.grua.estado = Number(d.estado);
      if (d.pos !== undefined) st.grua.pos = Number(d.pos);
      st.eventosGrua.unshift({ ts, ...d });
      st.eventosGrua.length = Math.min(st.eventosGrua.length, 100);
    }

    if (topic === "portus/cmd/respuesta") {
      if (d.name === "AgujaRecta" && msg.type === "ACK") Object.assign(st.aguja, { estado: "Recta (a transferencia)", clase: "ok" });
      if (d.name === "AgujaParqueo" && msg.type === "ACK") Object.assign(st.aguja, { estado: "Hacia parqueo", clase: "warn" });
      if (d.name === "AgujaLiberar" && msg.type === "ACK") Object.assign(st.aguja, { estado: "Liberando parqueo", clase: "movimiento" });
      if (enVivo) registrarRespuesta(msg);
    }
  }

  // ════════════════════════ sinoptico ════════════════════════

  function enlacePerdido(dev) {
    const u = st.dev[dev].ultimo;
    return !u || Date.now() - u.getTime() > UMBRAL_ENLACE_MS;
  }

  function setEl(id, texto, clase) {
    const el = $(id);
    if (!el) return;
    el.textContent = texto;
    el.className = `sin-val est-${clase || "idle"}`;
  }

  function modoSistema() {
    if (st.grua.mantenimiento) return ["Mantenimiento", "warn"];
    const degradado = ["UNO_ENTRADA", "UNO_SALIDA"].some((d) => st.dev[d].hb.degradado === "1");
    if (degradado || DISPOSITIVOS.some(enlacePerdido)) return ["Degradado", "bad"];
    return ["Operacion normal", "ok"];
  }

  function renderEnlaces() {
    const cont = $("sin-enlaces");
    if (!cont) return;
    const perdidos = [];
    cont.innerHTML = DISPOSITIVOS.map((dev) => {
      const u = st.dev[dev].ultimo;
      const perdido = enlacePerdido(dev);
      if (perdido) perdidos.push(dev);
      return `<span class="chip ${perdido ? "chip-bad" : "chip-ok"}">${dev}: ${perdido ? "desconectado" : "conectado"}
        <small>ultimo mensaje ${u ? fmtHora(u) : "nunca"}</small></span>`;
    }).join("");
    document.querySelectorAll("[data-dev]").forEach((el) => {
      el.classList.toggle("stale", perdidos.includes(el.dataset.dev));
    });
    const aviso = $("sin-aviso-enlace");
    if (aviso) {
      aviso.classList.toggle("hidden", perdidos.length === 0);
      aviso.textContent = perdidos.length
        ? `Enlace perdido con ${perdidos.join(", ")}: lo marcado en gris es el ultimo estado conocido, no el actual.`
        : "";
    }
    const [modo, clase] = modoSistema();
    const elModo = $("sin-modo");
    if (elModo) {
      elModo.textContent = modo;
      elModo.className = `chip chip-${clase}`;
    }
  }

  function renderSinoptico() {
    const activos = st.turnosActivos;
    const enEspera = activos.filter((t) => t.estado === "EnGarita");
    setEl("el-espera", String(enEspera.length), enEspera.length ? "warn" : "idle");

    setEl("el-garita", st.garita.estado, st.garita.clase);
    $("el-garita-sub").innerHTML = `${chipVehiculo(st.garita.uid)} ${escapeHtml(st.garita.detalle || "")}`;

    const tal = st.talanquera;
    setEl("el-talanquera", tal.moviendo ? "En movimiento" : (tal.estado ? (tal.estado === "abierta" ? "Abierta" : "Cerrada") : "-"),
      tal.moviendo ? "movimiento" : (tal.estado === "abierta" ? "ok" : "idle"));

    setEl("el-pesaje", st.pesaje.estado, st.pesaje.clase);
    const tPesaje = st.pesaje.uid ? turnoPorUid(st.pesaje.uid) : null;
    const ultimo = tPesaje && tPesaje.pesoMedidoEntradaG !== null ? `ultimo: ${gramos(tPesaje.pesoMedidoEntradaG)} (simulado)` : "";
    $("el-pesaje-sub").innerHTML = `${chipVehiculo(st.pesaje.uid)} ${ultimo}`;

    setEl("el-aguja", st.aguja.estado || "Recta (a transferencia)", st.aguja.clase);

    const enTransf = activos.find((t) => t.estado === "EnTransferencia");
    const posicionando = activos.filter((t) => t.estado === "EnRuta");
    if (enTransf) {
      setEl("el-transferencia", "Transferencia en curso", "movimiento");
      $("el-transferencia-sub").innerHTML = chipVehiculo(enTransf.vehiculoUid);
    } else if (posicionando.length) {
      setEl("el-transferencia", "Vehiculo posicionandose", "warn");
      $("el-transferencia-sub").innerHTML = posicionando.map((t) => chipVehiculo(t.vehiculoUid)).join(" ");
    } else {
      setEl("el-transferencia", "Libre", "idle");
      $("el-transferencia-sub").innerHTML = "";
    }

    const sal = st.salida;
    setEl("el-salida", sal.moviendo ? "En movimiento" : (sal.estado ? (sal.estado === "abierta" ? "Abierta" : "Cerrada") : "-"),
      sal.moviendo ? "movimiento" : (sal.estado === "abierta" ? "ok" : "idle"));
    const dentro = st.dev.UNO_SALIDA.hb.dentro;
    $("el-salida-sub").innerHTML = `Verificacion: ${escapeHtml(sal.garita)} ${chipVehiculo(sal.uid)} ${escapeHtml(sal.detalle || "")}`
      + (dentro !== undefined ? `<br>Vehiculos dentro: ${escapeHtml(dentro)}` : "");

    renderParqueo();
    renderGrua();
    renderPatio($("el-patio"));
    renderEnlaces();
  }

  function renderParqueo() {
    const cont = $("el-parqueo");
    if (!cont) return;
    if (!st.parqueo.length) {
      cont.innerHTML = "<span class='muted'>Sin datos.</span>";
      return;
    }
    cont.innerHTML = st.parqueo.map((p) => {
      if (!p.ocupada) return `<div class="plaza est-idle"><strong>Plaza ${p.id}</strong><br>Libre</div>`;
      const estado = p.retencionResuelta ? "Resuelta, esperando salir" : `Retenido ${escapeHtml(p.causa || "")}`;
      return `<div class="plaza ${p.retencionResuelta ? "est-warn" : "est-bad"}">
        <strong>Plaza ${p.id}</strong><br>${chipVehiculo(p.vehiculoUid)}<br>${estado}<br>${reloj(p.desde)}
        <br><button type="button" data-liberar-plaza="${p.id}" ${p.retencionResuelta ? "" : "disabled"}
          title="${p.retencionResuelta ? "Envia AgujaLiberar" : "Primero hay que resolver la retencion"}">Liberar parqueo</button>
      </div>`;
    }).join("");
  }

  function renderGrua() {
    const g = st.grua;
    const [nombre, clase] = g.estado !== null && ESTADOS_GRUA[g.estado] ? ESTADOS_GRUA[g.estado] : ["-", "idle"];
    const texto = g.suspendida ? `${nombre} (suspendida)` : nombre;
    setEl("el-grua", texto, g.suspendida ? "warn" : clase);
    const enTransf = st.turnosActivos.find((t) => t.estado === "EnTransferencia");
    $("el-grua-sub").textContent = `Posicion: ${g.pos === null || g.pos < 0 ? "sin referencia" : `P${g.pos}`}`
      + ` | Trabajo: ${enTransf ? `${enTransf.tipoOperacion} ${enTransf.contenedorId}` : "ninguno"}`;
    const pendientes = st.turnosActivos.filter((t) => t.estado === "EnRuta");
    $("el-cola").textContent = `${pendientes.length} pendiente(s)`
      + (pendientes.length ? `: ${pendientes.map((t) => t.tipoOperacion).join(", ")}` : "");

    $("grua-estado").textContent = texto;
    $("grua-pos").textContent = g.pos === null ? "-" : String(g.pos);
    $("grua-susp").textContent = g.suspendida ? "Si" : "No";
    $("grua-mant").textContent = g.mantenimiento ? "Si" : "No";

    const puedeReferenciar = g.suspendida || nombre === "En reposo";
    $("btn-reanudar").disabled = !g.suspendida;
    $("btn-referenciar").disabled = !puedeReferenciar;
    $("btn-mantenimiento").textContent = g.mantenimiento ? "Salir de mantenimiento" : "Modo mantenimiento";
  }

  const PATIO_CLASE = { LIBRE: "idle", RESERVADA: "warn", OCUPADA_1: "ok", OCUPADA_2: "ok", BLOQUEADA: "bad" };

  function renderPatio(cont) {
    if (!cont) return;
    cont.innerHTML = st.patio.map((p) => `
      <button type="button" class="posicion est-${PATIO_CLASE[p.estado] || "idle"}" data-posicion="${p.id}">
        <strong>P${p.id}</strong> <small>${escapeHtml(p.estado)}</small>
        <span class="nivel">N2: ${escapeHtml(p.contenedorNivel2 || "-")}</span>
        <span class="nivel">N1: ${escapeHtml(p.contenedorNivel1 || "-")}</span>
      </button>`).join("") || "<span class='muted'>Sin datos.</span>";
  }

  // ════════════════════════ datos del servidor ════════════════════════

  async function cargarTurnosActivos() {
    st.turnosActivos = await apiFetch("/api/terminal/turnos?activos=true");
  }

  async function cargarPatio() {
    const data = await apiFetch("/api/terminal/patio");
    st.patio = data.patio || [];
    st.parqueo = data.parqueo || [];
  }

  // Recargas por evento, agrupadas: varios cambios seguidos -> una sola peticion
  const pendientes = new Set();
  let temporizadorRecarga = null;

  function programarRecarga(...que) {
    que.forEach((q) => pendientes.add(q));
    clearTimeout(temporizadorRecarga);
    temporizadorRecarga = setTimeout(async () => {
      const lista = Array.from(pendientes);
      pendientes.clear();
      try {
        const tareas = [];
        if (lista.includes("sinoptico")) tareas.push(cargarTurnosActivos(), cargarPatio());
        await Promise.all(tareas);
        renderSinoptico();
        if (lista.includes("turnos") && cargadas.has("turnos")) cargarTurnos();
        if (lista.includes("intentos") && cargadas.has("turnos")) cargarIntentos();
        if (lista.includes("retenciones") && cargadas.has("retenciones")) cargarRetenciones();
        if (lista.includes("patio") && cargadas.has("patio")) cargarPestanaPatio();
      } catch (err) {
        toast(`No se pudo actualizar: ${err.message}`, "toast-bad");
      }
    }, 250);
  }

  const RECARGA_POR_ENTIDAD = {
    turno: ["sinoptico", "turnos"],
    retencion: ["sinoptico", "retenciones"],
    parqueo: ["sinoptico", "retenciones"],
    patio: ["sinoptico", "patio"],
    intento: ["intentos"],
  };

  // ════════════════════════ comandos remotos ════════════════════════

  const esperando = new Map(); // nombre de comando -> elemento de la lista

  function lineaRespuesta(texto, clase) {
    const cont = $("respuestas");
    if (!cont) return null;
    cont.querySelector(".muted")?.remove();
    const div = document.createElement("div");
    div.className = `respuesta ${clase}`;
    div.textContent = texto;
    cont.prepend(div);
    while (cont.children.length > 20) cont.lastChild.remove();
    return div;
  }

  async function enviarComando(name, params = {}, confirmar = null) {
    if (confirmar && !window.confirm(confirmar)) return;
    const hora = new Date().toLocaleTimeString();
    const extra = Object.keys(params).length ? ` (${Object.entries(params).map(([k, v]) => `${k}=${v}`).join(", ")})` : "";
    try {
      const r = await post("/api/terminal/comando", { name, params });
      const target = r.published ? r.published.target : "";
      const linea = lineaRespuesta(`${hora} ${name}${extra} enviado a ${target}: esperando respuesta...`, "pendiente");
      esperando.set(name, linea);
      setTimeout(() => {
        if (esperando.get(name) === linea) {
          esperando.delete(name);
          linea.textContent = `${hora} ${name}${extra}: sin respuesta del controlador en 6 s`;
          linea.className = "respuesta bad";
        }
      }, 6000);
    } catch (err) {
      lineaRespuesta(`${hora} ${name}${extra}: no se envio (${err.message})`, "bad");
    }
  }

  function registrarRespuesta(msg) {
    const d = msg.data || {};
    const ok = msg.type === "ACK";
    const texto = ok
      ? `${msg.origin} ACEPTO ${d.name}`
      : `${msg.origin} RECHAZO ${d.name}: ${d.causa || "sin causa"}`;
    const hora = new Date().toLocaleTimeString();
    const linea = esperando.get(d.name);
    if (linea) {
      esperando.delete(d.name);
      linea.textContent = `${hora} ${texto}`;
      linea.className = `respuesta ${ok ? "ok" : "bad"}`;
    } else {
      lineaRespuesta(`${hora} ${texto}`, ok ? "ok" : "bad"); // ej. comandos que manda el servidor
    }
    if (!ok) toast(texto, "toast-bad");
  }

  function parametrosDeTexto(texto) {
    const params = {};
    (texto || "").split(/[;,\s]+/).filter(Boolean).forEach((par) => {
      const [k, ...v] = par.split("=");
      if (k && v.length) params[k.trim()] = v.join("=").trim();
    });
    return params;
  }

  // ════════════════════════ bitacora de eventos ════════════════════════

  function describirEvento(topic, msg) {
    if (!msg || typeof msg !== "object") return String(msg);
    if (topic === "portus/srv/alarma") return `ALARMA ${msg.codigo} (${msg.severidad}): ${msg.descripcion}`;
    if (topic === "portus/srv/cambio") return `servidor: cambio en ${msg.entidad} ${msg.id}`;
    const datos = Object.entries(msg.data || {}).map(([k, v]) => `${k}=${v}`).join(" ");
    return `${msg.origin || "?"} ${msg.type || ""} ${topic.replace("portus/", "")} ${datos}`;
  }

  function agregarBitacora(topic, msg, cuando) {
    const log = $("event-log");
    if (!log) return;
    if (topic === "portus/evt/estado") return; // los latidos llenarian la bitacora; van en "Estado del enlace"
    const row = document.createElement("div");
    row.className = `log-row${topic.startsWith("portus/srv") ? " log-srv" : ""}`;
    row.textContent = `${fmtHora(cuando)}  ${describirEvento(topic, msg)}`;
    log.prepend(row);
    while (log.children.length > 200) log.lastChild.remove();
  }

  // ════════════════════════ WebSocket ════════════════════════

  function setBroker(conectado) {
    const el = $("mqtt-connected");
    if (!el) return;
    el.textContent = conectado ? "Conectado" : "Desconectado";
    el.className = `chip ${conectado ? "chip-ok" : "chip-bad"}`;
  }

  function recibir(topic, payload, enVivo) {
    if (topic === "portus/srv/cambio") {
      if (enVivo) programarRecarga(...(RECARGA_POR_ENTIDAD[payload.entidad] || []));
      return;
    }
    if (topic === "portus/srv/alarma") {
      if (enVivo) alarmaNueva(payload);
      return;
    }
    aplicarEvento(topic, payload, enVivo);
  }

  let reintentoMs = 1000;

  function conectar() {
    const ws = new WebSocket(wsUrl);
    ws.addEventListener("open", () => { reintentoMs = 1000; });
    ws.addEventListener("close", () => {
      setBroker(false);
      setTimeout(conectar, reintentoMs); // reconecta; al volver llega un snapshot nuevo
      reintentoMs = Math.min(reintentoMs * 2, 15000);
    });
    ws.addEventListener("message", (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (_) { return; }
      if (msg.kind === "snapshot") {
        setBroker(!!msg.connected);
        // Primero el ultimo mensaje de cada placa, despues lo reciente, del mas viejo al mas nuevo
        (msg.ultimos || []).forEach((e) => recibir(e.topic, e.payload, false));
        const recientes = (msg.events || []).slice().reverse();
        recientes.forEach((e) => recibir(e.topic, e.payload, false));
        recientes.forEach((e) => agregarBitacora(e.topic, e.payload, new Date(e.ts)));
        renderSinoptico();
        return;
      }
      if (msg.kind === "status") {
        setBroker(!!msg.connected);
        return;
      }
      if (msg.kind === "event") {
        setBroker(!!msg.connected);
        recibir(msg.topic, msg.payload, true);
        agregarBitacora(msg.topic, msg.payload, new Date());
        renderSinoptico();
        if (msg.topic === "portus/evt/grua" && cargadas.has("grua")) renderTablaGrua();
      }
    });
  }

  // ════════════════════════ pestaña Turnos ════════════════════════

  function filtrosTurnos() {
    const f = new FormData($("turnos-filtros"));
    return Object.fromEntries(Array.from(f.entries()).filter(([, v]) => v));
  }

  function filaTurno(t) {
    const activo = !FINALES.includes(t.estado);
    const hasta = t.closedAt || null;
    return `<tr>
      <td>${t.id}</td>
      <td>${chipVehiculo(t.vehiculoUid)}<br><small>${escapeHtml(t.transportistaNombre)}</small></td>
      <td>${escapeHtml(t.contenedorId)}</td>
      <td>${escapeHtml(t.tipoOperacion)}</td>
      <td><span class="chip">${escapeHtml(t.estado)}</span></td>
      <td>${escapeHtml(t.estacionActual)}</td>
      <td>${gramos(t.pesoDeclaradoG)} / ${gramos(t.pesoMedidoEntradaG)} / ${gramos(t.pesoMedidoSalidaG)}</td>
      <td>${escapeHtml(t.posicionPatio)}</td>
      <td>${escapeHtml(fmtDate(t.createdAt))}<br>${reloj(t.createdAt, hasta)}</td>
      <td class="acciones">
        <button type="button" data-detalle="${t.id}">Ver detalle</button>
        ${activo && t.estado !== "Retenido" ? `<button type="button" data-retener="${t.id}">Retener</button>
        <button type="button" data-anular="${t.id}" class="btn-warn">Anular</button>` : ""}
      </td>
    </tr>`;
  }

  const COLS_TURNO = ["Turno", "Vehiculo / transportista", "Contenedor", "Operacion", "Estado", "Estacion",
    "Peso decl. / entrada / salida", "Patio", "Creado / tiempo", "Acciones"];

  async function cargarTurnos() {
    const f = filtrosTurnos();
    const base = { estado: f.estado, tipo_operacion: f.tipo_operacion, q: f.q };
    const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v)).toString();
    try {
      const [activos, historicos] = await Promise.all([
        apiFetch(`/api/terminal/turnos?${qs({ ...base, activos: "true" })}`),
        apiFetch(`/api/terminal/turnos?${qs({ ...base, activos: "false", desde: f.desde, hasta: f.hasta })}`),
      ]);
      tabla($("tabla-turnos-activos"), COLS_TURNO, activos, filaTurno, "Sin turnos activos.");
      tabla($("tabla-turnos-historicos"), COLS_TURNO, historicos, filaTurno, "Sin turnos historicos.");
    } catch (err) {
      toast(`Error cargando turnos: ${err.message}`, "toast-bad");
    }
  }

  async function verTurno(id) {
    const dlg = $("dlg-turno");
    const body = $("dlg-turno-body");
    body.innerHTML = "Cargando...";
    dlg.showModal();
    try {
      const t = await apiFetch(`/api/terminal/turnos/${id}`);
      const eventos = (t.lineaDeTiempo || []).map((e) => {
        const valores = Object.entries(e.valores || {}).filter(([, v]) => v !== null && v !== "")
          .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(", ");
        const d = parseUtc(e.ts);
        return `<tr><td>${d ? d.toLocaleString() : "-"}</td><td><span class="chip">${escapeHtml(e.origen)}</span></td>
          <td>${escapeHtml(e.descripcion)}</td><td><small>${escapeHtml(valores)}</small></td></tr>`;
      }).join("");
      body.innerHTML = `<h2>Turno ${t.id} - ${escapeHtml(t.estado)}</h2>
        <p>${escapeHtml(t.tipoOperacion)} | Contenedor ${escapeHtml(t.contenedorId)} | Vehiculo ${escapeHtml(t.vehiculoUid)}
          | ${escapeHtml(t.transportistaNombre)}</p>
        <p>Peso declarado ${gramos(t.pesoDeclaradoG)} | entrada ${gramos(t.pesoMedidoEntradaG)} | salida ${gramos(t.pesoMedidoSalidaG)}
          | Tiempo en terminal ${reloj(t.createdAt, t.closedAt)}</p>
        <h3>Linea de tiempo</h3>
        <div class="table-wrap"><table class="data-table"><thead><tr><th>Hora</th><th>Origen</th><th>Evento</th><th>Valores</th></tr></thead>
        <tbody>${eventos || "<tr><td colspan='4'>Sin eventos.</td></tr>"}</tbody></table></div>`;
      actualizarRelojes();
    } catch (err) {
      body.textContent = `Error: ${err.message}`;
    }
  }

  async function retenerTurno(id) {
    const obs = window.prompt(`Retener el turno ${id} (RT06). Observacion opcional:`, "");
    if (obs === null) return;
    await accion(post(`/api/terminal/turnos/${id}/retener`, { observacion: obs || null }), `Turno ${id} retenido`);
  }

  async function anularTurno(id) {
    const causa = window.prompt(`Anular el turno ${id}: el vehiculo sale sin completar la operacion. Causa:`, "");
    if (causa === null) return;
    await accion(post(`/api/terminal/turnos/${id}/anular`, { causa: causa || null }), `Turno ${id} anulado`);
  }

  async function cargarIntentos() {
    try {
      const filas = await apiFetch("/api/terminal/intentos");
      tabla($("tabla-intentos"), ["Hora", "Estacion", "Vehiculo", "Contenedor", "Causa", "Decidio"], filas, (i) => `<tr>
        <td>${escapeHtml(fmtDate(i.ts))}</td><td>${escapeHtml(i.estacion)}</td><td>${escapeHtml(i.vehiculoUid)}</td>
        <td>${escapeHtml(i.contenedorId)}</td><td>${escapeHtml(i.causa)}</td><td>${escapeHtml(i.decididoPor)}</td></tr>`,
      "Sin intentos rechazados.");
    } catch (err) {
      toast(`Error cargando intentos: ${err.message}`, "toast-bad");
    }
  }

  let transportistas = [];

  async function cargarTransportistas() {
    const data = await apiFetch("/api/terminal/transportistas");
    transportistas = data.transportistas || [];
    const opciones = transportistas.map((t) =>
      `<option value="${t.id}">${t.id} - ${escapeHtml(t.nombre)}${t.vinculado ? " (vinculado)" : ""}</option>`).join("");
    $("transportista-select").innerHTML = opciones || "<option value=''>Sin transportistas</option>";
    $("vehiculo-transportista").innerHTML = `<option value="">Sin transportista</option>${opciones}`;
  }

  async function cargarVehiculos() {
    try {
      const filas = await apiFetch("/api/terminal/vehiculos");
      const nombre = (id) => (transportistas.find((t) => t.id === id) || {}).nombre;
      tabla($("tabla-vehiculos"), ["UID", "Transportista", "Placa", "Activo"], filas, (v) => `<tr>
        <td>${escapeHtml(v.uid)}</td><td>${escapeHtml(nombre(v.transportistaId))}</td>
        <td>${escapeHtml(v.placa)}</td><td>${v.activo ? "Si" : "No"}</td></tr>`, "Sin tarjetas registradas.");
    } catch (err) {
      toast(`Error cargando vehiculos: ${err.message}`, "toast-bad");
    }
  }

  // ════════════════════════ pestaña Retenciones ════════════════════════

  function filaRetencion(r) {
    const peso = r.diferenciaG !== null && r.diferenciaG !== undefined
      ? `${gramos(r.pesoDeclaradoG)} decl. / ${gramos(r.pesoMedidoG)} med.<br>dif. ${r.diferenciaG} g (${r.diferenciaPct} %)`
      : "-";
    const facultado = r.rolFacultado === "TERMINAL";
    let acciones = "";
    if (r.estado === "abierta") {
      // Sec. 4.3 regla 2: el rol no facultado no ve los botones (el servidor igual lo rechaza)
      acciones = facultado
        ? `<button type="button" data-resolver="aclarar" data-id="${r.id}">Aclarar</button>
           ${["RT01", "RT02"].includes(r.causa) ? `<button type="button" data-resolver="corregir" data-id="${r.id}"
             data-medido="${r.pesoMedidoG}">Corregir</button>` : ""}
           <button type="button" data-resolver="rechazar" data-id="${r.id}" class="btn-warn">Rechazar</button>`
        : `<span class="muted">Resuelve ${escapeHtml(r.rolFacultado)}</span>`;
    } else {
      acciones = `${escapeHtml(r.resolucion)}${r.motivo ? `: ${escapeHtml(r.motivo)}` : ""}`;
    }
    return `<tr>
      <td>${r.id}</td>
      <td>Turno ${r.turnoId}<br>${chipVehiculo(r.vehiculoUid)}</td>
      <td>${escapeHtml(r.contenedorId)}</td>
      <td><strong>${escapeHtml(r.causa)}</strong></td>
      <td>${escapeHtml(r.estacion)}<br><small>${escapeHtml(fmtDate(r.createdAt))}</small></td>
      <td>${escapeHtml(r.plaza)}</td>
      <td>${reloj(r.createdAt, r.resolvedAt)}</td>
      <td>${peso}</td>
      <td>${escapeHtml(r.rolFacultado)}</td>
      <td>${r.observacion ? `<small>${escapeHtml(r.observacion)}</small><br>` : ""}${acciones}</td>
    </tr>`;
  }

  const COLS_RET = ["Id", "Turno / vehiculo", "Contenedor", "Causa", "Momento", "Plaza", "Tiempo",
    "Evidencia de peso", "Rol facultado", "Resolucion"];

  async function cargarRetenciones() {
    const f = Object.fromEntries(new FormData($("retenciones-filtros")).entries());
    const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString();
    try {
      const filas = await apiFetch(`/api/terminal/retenciones?${qs}`);
      tabla($("tabla-ret-abiertas"), COLS_RET, filas.filter((r) => r.estado === "abierta"), filaRetencion, "Sin retenciones abiertas.");
      tabla($("tabla-ret-resueltas"), COLS_RET, filas.filter((r) => r.estado !== "abierta"), filaRetencion, "Sin retenciones resueltas.");
    } catch (err) {
      toast(`Error cargando retenciones: ${err.message}`, "toast-bad");
    }
  }

  async function resolverRetencion(boton) {
    const id = boton.dataset.id;
    const resolucion = boton.dataset.resolver;
    let motivo = null;
    let observacion = null;
    if (resolucion === "rechazar") {
      motivo = window.prompt(`Rechazar la retencion ${id}: se anula el turno y el vehiculo sale. Motivo (obligatorio):`, "");
      if (motivo === null) return;
      if (!motivo.trim()) {
        toast("Rechazar requiere un motivo.", "toast-bad");
        return;
      }
    } else {
      const aviso = resolucion === "corregir"
        ? `Corregir la retencion ${id}: el peso declarado pasa a ${boton.dataset.medido} g. Observacion opcional:`
        : `Aclarar la retencion ${id}: el turno continua sin cambiar el manifiesto. Observacion opcional:`;
      observacion = window.prompt(aviso, "");
      if (observacion === null) return;
    }
    await accion(post(`/api/terminal/retenciones/${id}/resolver`, { resolucion, motivo, observacion: observacion || null }),
      `Retencion ${id}: ${resolucion}`);
  }

  // ════════════════════════ pestaña Patio ════════════════════════

  async function cargarPestanaPatio() {
    try {
      await cargarPatio();
      renderPatio($("patio-posiciones"));
      renderSinoptico();
      let filas = await apiFetch("/api/terminal/patio/inventario");
      if ($("patio-orden").checked) filas = filas.slice().sort((a, b) => (b.permanenciaS || 0) - (a.permanenciaS || 0));
      tabla($("tabla-inventario"), ["Contenedor", "Naviera", "Posicion / nivel", "Peso declarado", "Autorizacion",
        "Ingreso a la terminal", "Permanencia", "Remociones"], filas, (c) => `<tr class="${c.permanenciaS > DOS_HORAS_S ? "fila-excedida" : ""}">
        <td>${escapeHtml(c.contenedorId)}</td><td>${escapeHtml(c.naviera)}</td><td>P${c.posicion} / N${c.nivel}</td>
        <td>${gramos(c.pesoDeclaradoG)}</td><td>${escapeHtml(c.estadoAutorizacion)}</td>
        <td>${escapeHtml(fmtDate(c.ingresoTerminal))}</td>
        <td>${c.enPatioDesde ? `<span class="reloj" data-desde="${escapeHtml(c.enPatioDesde)}" data-limite="${DOS_HORAS_S}"></span>` : "-"}</td>
        <td>${escapeHtml(c.remociones)}</td></tr>`, "El patio esta vacio.");
    } catch (err) {
      toast(`Error cargando patio: ${err.message}`, "toast-bad");
    }
  }

  function verPosicion(id) {
    const p = st.patio.find((x) => x.id === Number(id));
    if (!p) return;
    const bloqueada = p.estado === "BLOQUEADA";
    $("dlg-posicion-body").innerHTML = `<h2>Posicion P${p.id}</h2>
      <p>Estado: <span class="chip">${escapeHtml(p.estado)}</span> | Remociones: ${escapeHtml(p.remociones)}</p>
      <table class="data-table"><tr><th>Nivel</th><th>Contenedor</th><th>En patio desde</th></tr>
        <tr><td>2</td><td>${escapeHtml(p.contenedorNivel2)}</td><td>${p.nivel2Desde ? reloj(p.nivel2Desde) : "-"}</td></tr>
        <tr><td>1</td><td>${escapeHtml(p.contenedorNivel1)}</td><td>${p.nivel1Desde ? reloj(p.nivel1Desde) : "-"}</td></tr></table>
      <div class="controles">
        <button type="button" data-patio-accion="bloquear" data-id="${p.id}" ${bloqueada ? "disabled" : ""}>Bloquear</button>
        <button type="button" data-patio-accion="liberar" data-id="${p.id}" ${bloqueada ? "" : "disabled"}
          title="${bloqueada ? "" : "Solo si la posicion esta bloqueada"}">Liberar</button>
      </div>`;
    actualizarRelojes();
    $("dlg-posicion").showModal();
  }

  // ════════════════════════ pestaña Alarmas ════════════════════════

  function setBadge(n) {
    st.alarmasActivas = n;
    const b = $("badge-alarmas");
    if (!b) return;
    b.textContent = String(n);
    b.classList.toggle("hidden", n === 0);
  }

  async function contarAlarmasActivas() {
    try {
      setBadge((await apiFetch("/api/terminal/alarmas?estado=activa")).length);
    } catch (_) { /* el conteo es informativo */ }
  }

  function alarmaNueva(a) {
    setBadge(st.alarmasActivas + 1);
    toast(`${a.codigo} (${a.severidad}): ${a.descripcion}`, ["critica", "alta"].includes(a.severidad) ? "toast-bad" : "toast-warn");
    if (cargadas.has("alarmas")) cargarAlarmas();
  }

  function filaAlarma(a) {
    const activa = a.estado === "activa";
    return `<tr class="sev-${escapeHtml(a.severidad)}">
      <td>${a.id}</td><td>${escapeHtml(fmtDate(a.createdAt))}</td>
      <td><strong>${escapeHtml(a.codigo)}</strong> <span class="chip sev">${escapeHtml(a.severidad)}</span></td>
      <td>${escapeHtml(a.origen)}</td><td>${escapeHtml(a.descripcion)}</td>
      <td>${activa ? `<button type="button" data-reconocer="${a.id}">Reconocer</button>`
        : `Reconocida ${escapeHtml(fmtDate(a.ackAt))}${a.ackComentario ? `<br><small>${escapeHtml(a.ackComentario)}</small>` : ""}`}</td>
    </tr>`;
  }

  async function cargarAlarmas() {
    const sev = $("alarmas-severidad").value;
    const qs = sev ? `&severidad=${encodeURIComponent(sev)}` : "";
    try {
      const [activas, historicas] = await Promise.all([
        apiFetch(`/api/terminal/alarmas?estado=activa${qs}`),
        apiFetch(`/api/terminal/alarmas?estado=reconocida${qs}`),
      ]);
      const cols = ["Id", "Aparicion", "Alarma", "Origen", "Descripcion", "Reconocimiento"];
      tabla($("tabla-alarmas-activas"), cols, activas, filaAlarma, "Sin alarmas activas.");
      tabla($("tabla-alarmas-historicas"), cols, historicas, filaAlarma, "Sin alarmas reconocidas.");
      if (!sev) setBadge(activas.length);
      else contarAlarmasActivas();
    } catch (err) {
      toast(`Error cargando alarmas: ${err.message}`, "toast-bad");
    }
  }

  // ════════════════════════ pestaña Grua ════════════════════════

  function renderTablaGrua() {
    tabla($("tabla-grua"), ["Hora", "Evento", "Estado", "Posicion"], st.eventosGrua, (e) => {
      const nombre = ESTADOS_GRUA[Number(e.estado)] ? ESTADOS_GRUA[Number(e.estado)][0] : e.estado;
      return `<tr><td>${fmtHora(e.ts)}</td><td>${escapeHtml(e.evt)}</td><td>${escapeHtml(nombre)}</td><td>${escapeHtml(e.pos)}</td></tr>`;
    }, "Sin eventos de grua desde que se abrio la pagina.");
  }

  // ════════════════════════ pestañas ════════════════════════

  const cargadas = new Set();
  const CARGAR_PESTANA = {
    turnos: () => Promise.all([cargarTurnos(), cargarIntentos(), cargarVehiculos()]),
    retenciones: cargarRetenciones,
    patio: cargarPestanaPatio,
    alarmas: cargarAlarmas,
    grua: async () => renderTablaGrua(),
  };

  function activarPestana(tab) {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("hidden", p.dataset.tabPanel !== tab));
    if (window.location.hash !== `#${tab}`) window.history.replaceState(null, "", `#${tab}`);
    if (CARGAR_PESTANA[tab]) {
      cargadas.add(tab);
      CARGAR_PESTANA[tab]();
    }
  }

  // ════════════════════════ eventos de la pagina ════════════════════════

  document.addEventListener("click", async (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    if (b.classList.contains("tab-btn")) return activarPestana(b.dataset.tab);
    if (b.dataset.vehiculo) {
      const t = turnoPorUid(b.dataset.vehiculo);
      if (t) verTurno(t.id);
      else toast(`El vehiculo ${b.dataset.vehiculo} no tiene turno activo.`);
      return;
    }
    if (b.dataset.detalle) return verTurno(b.dataset.detalle);
    if (b.dataset.retener) return retenerTurno(b.dataset.retener);
    if (b.dataset.anular) return anularTurno(b.dataset.anular);
    if (b.dataset.resolver) return resolverRetencion(b);
    if (b.dataset.posicion) return verPosicion(b.dataset.posicion);
    if (b.dataset.patioAccion) {
      const { id, patioAccion } = b.dataset;
      const r = await accion(post(`/api/terminal/patio/${id}/${patioAccion}`),
        `Posicion P${id}: ${patioAccion === "bloquear" ? "PosicionBloquear" : "PosicionLiberar"} enviado`);
      if (r) $("dlg-posicion").close();
      return;
    }
    if (b.dataset.liberarPlaza) {
      const plaza = b.dataset.liberarPlaza;
      if (!window.confirm(`Enviar AgujaLiberar para la plaza ${plaza}?`)) return;
      await accion(post(`/api/terminal/parqueo/${plaza}/liberar`), `AgujaLiberar enviado (plaza ${plaza})`);
      return;
    }
    if (b.dataset.reconocer) {
      const comentario = window.prompt(`Reconocer la alarma ${b.dataset.reconocer}. Comentario opcional:`, "");
      if (comentario === null) return;
      if (await accion(post(`/api/terminal/alarmas/${b.dataset.reconocer}/reconocer`, { comentario: comentario || null }))) {
        cargarAlarmas();
      }
    }
  });

  $("btn-suspender").addEventListener("click", () => enviarComando("GruaSuspender"));
  $("btn-reanudar").addEventListener("click", () => enviarComando("GruaReanudar"));
  $("btn-referenciar").addEventListener("click", () => enviarComando("GruaReferenciar"));
  $("btn-talanquera").addEventListener("click", () =>
    enviarComando("AbrirTalanquera", {}, "Abrir la talanquera de ingreso manualmente?"));
  $("btn-puerta").addEventListener("click", () =>
    enviarComando("AbrirPuertaSalida", {}, "Abrir la puerta de salida manualmente?"));
  $("btn-mantenimiento").addEventListener("click", () => {
    const activar = !st.grua.mantenimiento;
    enviarComando("ModoMantenimiento", { valor: activar ? "activar" : "desactivar" },
      activar ? "Activar el modo mantenimiento? La grua no tomara trabajos de turnos." : "Salir del modo mantenimiento?");
  });
  $("btn-silenciar").addEventListener("click", () => enviarComando("AlarmaSilenciar"));

  $("command-form").addEventListener("submit", (e) => {
    e.preventDefault();
    enviarComando($("command-input").value, parametrosDeTexto($("command-params").value));
  });

  $("turnos-filtros").addEventListener("submit", (e) => {
    e.preventDefault();
    cargarTurnos();
  });
  $("retenciones-filtros").addEventListener("change", cargarRetenciones);
  $("patio-orden").addEventListener("change", cargarPestanaPatio);
  $("alarmas-severidad").addEventListener("change", cargarAlarmas);
  $("btn-reconocer-todas").addEventListener("click", async () => {
    if (!window.confirm("Reconocer todas las alarmas activas de severidad media y baja?")) return;
    const r = await accion(post("/api/terminal/alarmas/reconocer-todas"));
    if (r) {
      toast(`${r.reconocidas} alarma(s) reconocida(s). Las criticas y altas se reconocen una por una.`, "toast-ok");
      cargarAlarmas();
    }
  });

  $("form-vehiculo").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const body = {
      uid: f.get("uid"),
      transportista_id: f.get("transportista_id") ? Number(f.get("transportista_id")) : null,
      placa: f.get("placa") || "",
      activo: f.get("activo") === "on",
    };
    if (await accion(post("/api/terminal/vehiculos", body), `Tarjeta ${body.uid} guardada`)) {
      e.target.reset();
      cargarVehiculos();
    }
  });

  $("refresh-transportistas").addEventListener("click", cargarTransportistas);
  $("generate-link-code").addEventListener("click", async () => {
    const id = Number($("transportista-select").value);
    if (!id) return toast("Selecciona un transportista.");
    const r = await accion(post("/api/terminal/vinculacion/generar", { transportistaId: id }));
    if (r) {
      $("link-code-result").innerHTML = `Codigo para <strong>${escapeHtml(r.nombre)}</strong>:
        <span class="codigo">${escapeHtml(r.codigo)}</span> (un solo uso, vence ${escapeHtml(r.expiraLocal)})`;
    }
  });

  // ════════════════════════ arranque ════════════════════════

  (async () => {
    try {
      await Promise.all([cargarTurnosActivos(), cargarPatio(), cargarTransportistas(), contarAlarmasActivas()]);
    } catch (err) {
      toast(`Error cargando datos iniciales: ${err.message}`, "toast-bad");
    }
    renderSinoptico();
    conectar();
    const hashTab = (window.location.hash || "").replace("#", "");
    const existe = Array.from(document.querySelectorAll(".tab-btn")).some((b) => b.dataset.tab === hashTab);
    activarPestana(existe ? hashTab : "operacion");
  })();

  // Solo redibuja (relojes, antiguedad del enlace, modo); no consulta al servidor.
  setInterval(() => {
    actualizarRelojes();
    renderEnlaces();
  }, 1000);
})();

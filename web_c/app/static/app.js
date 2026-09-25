(function () {
  const wsUrl = window.PORTUS_WS_URL;
  if (!wsUrl) return;

  const elConnected = document.getElementById("mqtt-connected");
  const elHeartbeat = document.getElementById("mqtt-heartbeat");
  const elLog = document.getElementById("event-log");
  const commandForm = document.getElementById("command-form");
  const commandInput = document.getElementById("command-input");
  const commandResult = document.getElementById("command-result");
  const transportistaSelect = document.getElementById("transportista-select");
  const refreshTransportistasBtn = document.getElementById("refresh-transportistas");
  const generateLinkCodeBtn = document.getElementById("generate-link-code");
  const linkCodeResult = document.getElementById("link-code-result");
  const tabButtons = Array.from(document.querySelectorAll(".tab-btn"));
  const tabPanels = Array.from(document.querySelectorAll(".tab-panel"));
  const refreshTurnosBtn = document.getElementById("refresh-turnos");
  const refreshRetencionesBtn = document.getElementById("refresh-retenciones");
  const refreshPatioBtn = document.getElementById("refresh-patio");
  const refreshAlarmasBtn = document.getElementById("refresh-alarmas");
  const refreshGruaBtn = document.getElementById("refresh-grua");
  const refreshCitasBtn = document.getElementById("refresh-citas");
  const refreshReportesBtn = document.getElementById("refresh-reportes");
  const turnosResult = document.getElementById("turnos-result");
  const retencionesResult = document.getElementById("retenciones-result");
  const patioResult = document.getElementById("patio-result");
  const alarmasResult = document.getElementById("alarmas-result");
  const gruaResult = document.getElementById("grua-result");
  const citasResult = document.getElementById("citas-result");
  const reportesResult = document.getElementById("reportes-result");
  const loadedTabs = new Set();
  const recentEvents = [];

  function setConnection(connected) {
    if (!elConnected) return;
    elConnected.textContent = connected ? "Conectado" : "Desconectado";
    elConnected.style.color = connected ? "#1a7f37" : "#cf222e";
  }

  function setHeartbeat(ts) {
    if (!elHeartbeat) return;
    elHeartbeat.textContent = ts || "N/A";
  }

  function appendLog(eventObj) {
    if (!elLog) return;
    recentEvents.unshift(eventObj);
    if (recentEvents.length > 200) recentEvents.pop();
    const row = document.createElement("div");
    row.className = "log-row";
    row.textContent = JSON.stringify(eventObj);
    elLog.prepend(row);
  }

  const ws = new WebSocket(wsUrl);
  ws.addEventListener("open", () => {
    setConnection(true);
    ws.send("hello");
  });
  ws.addEventListener("close", () => setConnection(false));
  ws.addEventListener("error", () => setConnection(false));
  ws.addEventListener("message", (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.kind === "snapshot") {
        setConnection(!!msg.connected);
        setHeartbeat(msg.lastHeartbeat);
        (msg.events || []).forEach((item) => appendLog(item));
        return;
      }
      if (typeof msg.connected === "boolean") {
        setConnection(msg.connected);
      }
      if (msg.lastHeartbeat) {
        setHeartbeat(msg.lastHeartbeat);
      }
      appendLog(msg);
    } catch (e) {
      appendLog({ raw: ev.data });
    }
  });

  if (commandForm) {
    commandForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const cmd = commandInput.value.trim();
      if (!cmd) return;
      const res = await fetch("/api/terminal/comando", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: cmd }),
      });
      const data = await res.json();
      commandResult.textContent = JSON.stringify(data, null, 2);
    });
  }

  async function getJson(url) {
    const res = await fetch(url);
    const data = await res.json();
    return { status: res.status, data };
  }

  async function loadTurnos() {
    if (!turnosResult) return;
    turnosResult.textContent = "Cargando...";
    try {
      const { data } = await getJson("/api/terminal/turnos");
      turnosResult.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
      turnosResult.textContent = `Error cargando turnos: ${String(err)}`;
    }
  }

  async function loadRetenciones() {
    if (!retencionesResult) return;
    retencionesResult.textContent = "Cargando...";
    try {
      const { data } = await getJson("/api/terminal/retenciones");
      retencionesResult.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
      retencionesResult.textContent = `Error cargando retenciones: ${String(err)}`;
    }
  }

  async function loadPatio() {
    if (!patioResult) return;
    patioResult.textContent = "Cargando...";
    try {
      const { data } = await getJson("/api/terminal/patio");
      patioResult.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
      patioResult.textContent = `Error cargando patio: ${String(err)}`;
    }
  }

  async function loadAlarmas() {
    if (!alarmasResult) return;
    alarmasResult.textContent = "Cargando...";
    try {
      const { data } = await getJson("/api/terminal/alarmas");
      alarmasResult.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
      alarmasResult.textContent = `Error cargando alarmas: ${String(err)}`;
    }
  }

  async function loadGrua() {
    if (!gruaResult) return;
    const eventosGrua = recentEvents.filter((e) => e && e.topic === "portus/evt/grua").slice(0, 40);
    if (eventosGrua.length === 0) {
      gruaResult.textContent = "Sin eventos de grua aun. Ejecuta un ciclo y vuelve a actualizar.";
      return;
    }
    gruaResult.textContent = JSON.stringify(eventosGrua, null, 2);
  }

  async function loadCitas() {
    if (!citasResult) return;
    citasResult.textContent = "Cargando...";
    try {
      const { data } = await getJson("/api/terminal/turnos");
      const resumen = (data || []).map((t) => ({
        turno: t.id,
        contenedor: t.contenedorId,
        operacion: t.tipoOperacion,
        estado: t.estado,
        estacion: t.estacionActual,
        creado: t.createdAt,
      }));
      citasResult.textContent = JSON.stringify(resumen, null, 2);
    } catch (err) {
      citasResult.textContent = `Error cargando citas: ${String(err)}`;
    }
  }

  async function loadReportes() {
    if (!reportesResult) return;
    reportesResult.textContent = "Calculando...";
    try {
      const { data } = await getJson("/api/terminal/turnos");
      const turnos = Array.isArray(data) ? data : [];
      const porEstado = {};
      let cerrados = 0;
      turnos.forEach((t) => {
        porEstado[t.estado] = (porEstado[t.estado] || 0) + 1;
        if (t.estado === "CERRADO") cerrados++;
      });
      const eventosGrua = recentEvents.filter((e) => e && e.topic === "portus/evt/grua").length;
      const resumen = {
        total_turnos: turnos.length,
        turnos_cerrados: cerrados,
        turnos_por_estado: porEstado,
        eventos_grua_en_memoria: eventosGrua,
        generado_en: new Date().toISOString(),
      };
      reportesResult.textContent = JSON.stringify(resumen, null, 2);
    } catch (err) {
      reportesResult.textContent = `Error calculando reportes: ${String(err)}`;
    }
  }

  async function loadTabData(tab) {
    if (loadedTabs.has(tab)) return;
    if (tab === "turnos") await loadTurnos();
    if (tab === "retenciones") await loadRetenciones();
    if (tab === "patio") await loadPatio();
    if (tab === "alarmas") await loadAlarmas();
    if (tab === "grua") await loadGrua();
    if (tab === "citas") await loadCitas();
    if (tab === "reportes") await loadReportes();
    loadedTabs.add(tab);
  }

  function activateTab(tab) {
    tabButtons.forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === tab));
    tabPanels.forEach((panel) => panel.classList.toggle("hidden", panel.dataset.tabPanel !== tab));
    if (window.location.hash !== `#${tab}`) window.history.replaceState(null, "", `#${tab}`);
    loadTabData(tab);
  }

  if (tabButtons.length > 0) {
    tabButtons.forEach((btn) => {
      btn.addEventListener("click", () => activateTab(btn.dataset.tab));
    });
    const hashTab = (window.location.hash || "").replace("#", "");
    const initialTab = tabButtons.some((b) => b.dataset.tab === hashTab) ? hashTab : "operacion";
    activateTab(initialTab);
  }

  if (refreshTurnosBtn) refreshTurnosBtn.addEventListener("click", loadTurnos);
  if (refreshRetencionesBtn) refreshRetencionesBtn.addEventListener("click", loadRetenciones);
  if (refreshPatioBtn) refreshPatioBtn.addEventListener("click", loadPatio);
  if (refreshAlarmasBtn) refreshAlarmasBtn.addEventListener("click", loadAlarmas);
  if (refreshGruaBtn) refreshGruaBtn.addEventListener("click", loadGrua);
  if (refreshCitasBtn) refreshCitasBtn.addEventListener("click", loadCitas);
  if (refreshReportesBtn) refreshReportesBtn.addEventListener("click", loadReportes);

  async function loadTransportistas() {
    if (!transportistaSelect) return;
    const res = await fetch("/api/terminal/transportistas");
    const data = await res.json();
    transportistaSelect.innerHTML = "";
    if (!data.transportistas || !data.transportistas.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "Sin transportistas";
      transportistaSelect.appendChild(opt);
      return;
    }
    data.transportistas.forEach((t) => {
      const opt = document.createElement("option");
      opt.value = t.id;
      opt.textContent = `${t.id} - ${t.nombre}${t.vinculado ? " (vinculado)" : ""}`;
      transportistaSelect.appendChild(opt);
    });
  }

  if (refreshTransportistasBtn) {
    refreshTransportistasBtn.addEventListener("click", loadTransportistas);
  }

  if (generateLinkCodeBtn) {
    generateLinkCodeBtn.addEventListener("click", async () => {
      const transportistaId = transportistaSelect ? Number(transportistaSelect.value) : 0;
      if (!transportistaId) {
        if (linkCodeResult) linkCodeResult.textContent = "Selecciona un transportista.";
        return;
      }
      const res = await fetch("/api/terminal/vinculacion/generar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transportistaId }),
      });
      const data = await res.json();
      if (linkCodeResult) linkCodeResult.textContent = JSON.stringify(data, null, 2);
    });
  }

  if (transportistaSelect) {
    loadTransportistas();
  }
})();

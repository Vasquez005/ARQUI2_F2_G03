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

(() => {
  const key = "mneme.fimathe.settings.v1";
  const fields = [
    ["timeframe_minutes", "Tempo gráfico", "select", [[1, "M1"], [5, "M5"], [15, "M15"]]],
    ["channel_candles", "Velas do canal", "number", 2, 100, 1, "O modelo do laboratório usa quatro velas fechadas."],
    ["marking", "Marcação", "select", [["wicks", "Pavios"], ["bodies", "Corpos"]]],
    ["initial_balance", "Capital simulado (USD)", "number", 0.01, 1e12],
    ["risk_pct", "Risco máximo por entrada (%)", "number", 0.00000001, 10],
    ["reward_risk", "Alvo / risco (R)", "number", 0.00000001, 20],
    ["contract_size", "Unidades de XAU por lote", "number", 0.00000001, 1e12, "any", "Use o tamanho do contrato da fonte do CSV."],
    ["min_lots", "Lote mínimo", "number", 0.00000001, 1e12],
    ["max_lots", "Lote máximo", "number", 0.00000001, 1e12],
    ["lot_step", "Passo do lote", "number", 0.00000001, 1e12],
    ["spread", "Spread (preço, ask − bid)", "number", 0, 1e12],
    ["slippage", "Slippage por lado (preço)", "number", 0, 1e12],
    ["commission_per_lot", "Comissão por lote e por lado (USD)", "number", 0, 1e12],
    ["max_exposure_pct", "Exposição nominal máxima (%)", "number", 0.00000001, 100],
    ["daily_profit_target_pct", "Parar entradas ao ganhar no dia (%)", "number", 0.00000001, 100],
    ["daily_loss_limit_pct", "Parar entradas ao perder no dia (%)", "number", 0.00000001, 100],
    ["csv_utc_offset_minutes", "Fuso dos horários sem zona (minutos de UTC)", "number", -840, 840, 1, "Ex.: UTC = 0; Brasília = −180. ISO com zona e Unix já identificam o horário."],
  ];
  function read() {
    try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return null; }
  }
  const valid = c => c?.schema === 1 && c.strategy === "fimathe" && c.symbol === "XAUUSD" && fields.every(([k,,type,min,max]) => {
    const v = c.parameters?.[k];
    return type === "select" ? min.some(([x]) => x === v) : typeof v === "number" && Number.isFinite(v) && v >= min && v <= max;
  }) && ["channel_candles", "csv_utc_offset_minutes"].every(k => Number.isInteger(c.parameters[k]))
    && c.parameters.min_lots <= c.parameters.max_lots && c.parameters.lot_step <= c.parameters.max_lots;
  const download = (value, name) => {
    const a = document.createElement("a"), url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
    a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  globalThis.FimatheSettings = { read, valid, download };
  const form = document.getElementById("fimatheSettings");
  if (!form) return;
  const box = document.getElementById("fimatheFields"), message = document.getElementById("fimatheSettingsStatus");
  for (const [name, label, type, min, max, step, hint] of fields) {
    const field = document.createElement("div"); field.className = "field";
    const lab = document.createElement("label"); lab.htmlFor = "fimathe-" + name; lab.textContent = label;
    const input = document.createElement(type === "select" ? "select" : "input");
    input.id = lab.htmlFor; input.name = name; input.required = true;
    if (type === "select") {
      input.add(new Option("Selecione…", ""));
      for (const [value, text] of min) input.add(new Option(text, value));
    } else { input.type = "number"; input.min = min; input.max = max; input.step = step ?? "any"; }
    field.append(lab, input);
    if (hint) { const note = document.createElement("small"); note.className = "hint"; note.textContent = hint; field.append(note); }
    box.append(field);
  }
  function show(config) {
    for (const [k] of fields) form.elements.namedItem(k).value = config?.parameters?.[k] ?? "";
    message.textContent = valid(config) ? "Regra salva neste navegador. Exporte para usar também pela linha de comando." : "Regra incompleta: somente observação. Preencha todos os campos, inclusive custos.";
  }
  function value() {
    return { schema: 1, strategy: "fimathe", symbol: "XAUUSD", parameters: Object.fromEntries(fields.map(([k,,type]) => {
      const v = form.elements.namedItem(k).value;
      return [k, v === "" ? null : type === "select" && k === "marking" ? v : Number(v)];
    })) };
  }
  form.addEventListener("submit", event => {
    event.preventDefault();
    try { const config = value(); localStorage.setItem(key, JSON.stringify(config)); show(config); }
    catch { message.textContent = "Não foi possível salvar neste navegador. Verifique a permissão de armazenamento."; }
  });
  document.getElementById("fimatheExport").addEventListener("click", () => {
    const config = value();
    if (!form.reportValidity() || !valid(config)) { message.textContent = "Complete a regra e confira os limites dos lotes antes de exportar."; return; }
    try { localStorage.setItem(key, JSON.stringify(config)); download(config, "mneme-fimathe-config.json"); show(config); }
    catch { message.textContent = "Não foi possível salvar ou exportar a configuração."; }
  });
  show(read());
})();

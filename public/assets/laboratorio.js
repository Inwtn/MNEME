(() => {
  const body = document.getElementById("labStrategies");
  const status = document.getElementById("labStatus");
  let catalog = [];
  const fmt = n => typeof n === "number" && Number.isFinite(n) ? new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 }).format(n) : "—";
  function row(values) {
    const tr = document.createElement("tr");
    for (const value of values) { const td = document.createElement("td"); td.textContent = value; tr.append(td); }
    body.append(tr);
  }
  function render(results = []) {
    body.replaceChildren();
    for (const strategy of catalog) {
      const found = results.filter(r => (r.setup ?? r.modelo ?? (r.strategy === "fimathe-experimental-v1" ? "Fimathe (canais)" : null)) === strategy.name);
      if (!found.length) {
        const incomplete = strategy.name === "Fimathe (canais)" && !globalThis.FimatheSettings.valid(globalThis.FimatheSettings.read());
        row([strategy.name, strategy.kind === "modelo" ? "Modelo" : "Setup", "—", "—", "—", "—", incomplete ? "Aguardando configuração" : "Aguardando resultado medido"]);
        continue;
      }
      for (const r of found) {
        const m = r.metrics;
        const count = m?.closed ?? r.operacoes ?? r.sinais ?? r.previsoes;
        const accuracy = m ? m.accuracy_pct : r.acerto == null ? null : r.acerto * 100;
        const result = m ? `${fmt(m.net_profit)} USD` : r.retorno_medio_pct != null ? `${fmt(r.retorno_medio_pct)}% / operação` : "—";
        row([strategy.name, strategy.kind === "modelo" ? "Modelo" : "Setup", [r.par ?? r.symbol, r.minutos ? `${r.minutos} min` : r.settings?.timeframe_minutes ? `M${r.settings.timeframe_minutes}` : r.horizonte ? `${r.horizonte} min` : null].filter(Boolean).join(" · ") || "—", fmt(count), count > 0 && accuracy != null ? `${fmt(accuracy)}%` : "—", result, count > 0 ? "Experimental · resultado importado" : "Sem amostra encerrada"]);
      }
    }
  }
  document.getElementById("labResults").addEventListener("change", async event => {
    try {
      const file = event.target.files[0];
      if (!file || file.size > 32 * 1024 * 1024) throw Error("Use um arquivo de até 32 MB.");
      const value = JSON.parse(await file.text());
      const results = Array.isArray(value) ? value : [value];
      if (results.length > 10000 || !results.every(r => r && typeof r === "object" && !Array.isArray(r))) throw Error("Formato de relatório inválido.");
      if (!results.some(r => catalog.some(s => s.name === (r.setup ?? r.modelo ?? (r.strategy === "fimathe-experimental-v1" ? "Fimathe (canais)" : null))))) throw Error("Nenhuma estratégia do catálogo foi encontrada neste relatório.");
      render(results); status.textContent = "Resultados importados nesta aba · não representam acompanhamento ao vivo.";
    } catch (error) { status.textContent = error.message; }
  });
  fetch("/assets/laboratorio-catalogo.json", { cache: "no-store" }).then(r => { if (!r.ok) throw Error(); return r.json(); }).then(value => {
    catalog = value.strategies; render(); status.textContent = "Estratégias do laboratório Python · resultados medidos por ativo e período.";
  }).catch(() => { status.textContent = "Não foi possível carregar o catálogo de estratégias."; });
})();

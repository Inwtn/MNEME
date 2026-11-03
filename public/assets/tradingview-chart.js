// Todos os gráficos do painel usam o widget oficial do TradingView.
(() => {
  const symbol = document.getElementById("tradingViewSymbol");
  const interval = document.getElementById("tradingViewInterval");
  const widget = document.getElementById("tradingViewChart");
  const status = document.getElementById("tradingViewStatus");
  const symbols = new Set([...symbol.options].map(option => option.value));
  const intervals = new Set([...interval.options].map(option => option.value));
  function tick() {
    const state = globalThis.CandleClock.remaining(symbol.value, interval.value);
    document.getElementById("candleClockValue").textContent = state.text;
    document.getElementById("candleClockLabel").textContent = state.estimated ? "Previsto em" : "Fecha em";
    document.getElementById("candleClockValue").setAttribute("aria-label", symbol.selectedOptions[0].textContent + " · " + interval.selectedOptions[0].textContent + " · fechamento previsto: " + state.text);
    document.getElementById("candleClockNote").textContent = state.estimated
      ? "Previsão pela sessão regular de Nova York. Feriados, atrasos e sessões especiais podem alterar o fechamento do TradingView."
      : "Atualiza a cada segundo, pelo horário do intervalo (UTC). Mantenha o relógio do dispositivo correto.";
  }
  function load() {
    if (!symbols.has(symbol.value) || !intervals.has(interval.value)) return;
    tick();
    const [exchange, ticker] = symbol.value.split(":");
    const link = document.getElementById("tradingViewExternalLink");
    link.href = `https://www.tradingview.com/symbols/${ticker}/?exchange=${exchange}`;
    status.textContent = "TradingView · horário de Brasília · escolha o ativo e o intervalo nos seletores acima para sincronizar o contador.";
    const container = document.createElement("div");
    container.className = "tradingview-widget-container";
    const chart = document.createElement("div");
    chart.className = "tradingview-widget-container__widget";
    const attribution = document.createElement("div");
    attribution.className = "tradingview-widget-copyright";
    const attributionLink = link.cloneNode(true);
    attributionLink.removeAttribute("id");
    attribution.append(attributionLink, " por TradingView");
    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;
    script.textContent = JSON.stringify({ autosize: true, symbol: symbol.value, interval: interval.value,
      timezone: "America/Sao_Paulo", theme: "dark", style: "1", locale: "br",
      // O widget não oferece o contador nativo. Os seletores externos comandam ambos.
      allow_symbol_change: false, hide_top_toolbar: true, hide_legend: true,
      calendar: false, support_host: "https://www.tradingview.com" });
    script.onerror = () => { if (container.isConnected) status.textContent = "Não foi possível carregar o gráfico. Tente recarregar ou abra o TradingView pelo link abaixo."; };
    container.append(chart, attribution, script);
    widget.replaceChildren(container);
  }
  symbol.addEventListener("change", load);
  interval.addEventListener("change", load);
  document.getElementById("tradingViewRetry").addEventListener("click", load);
  document.addEventListener("visibilitychange", tick);
  setInterval(tick, 1000);
  load();
})();

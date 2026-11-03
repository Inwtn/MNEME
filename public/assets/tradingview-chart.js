// Todos os gráficos do painel usam o widget oficial do TradingView.
(() => {
  const symbol = document.getElementById("tradingViewSymbol");
  const interval = document.getElementById("tradingViewInterval");
  const widget = document.getElementById("tradingViewChart");
  const status = document.getElementById("tradingViewStatus");
  const symbols = new Set([...symbol.options].map(option => option.value));
  const intervals = new Set([...interval.options].map(option => option.value));
  function load() {
    if (!symbols.has(symbol.value) || !intervals.has(interval.value)) return;
    const [exchange, ticker] = symbol.value.split(":");
    const link = document.getElementById("tradingViewExternalLink");
    link.href = `https://www.tradingview.com/symbols/${ticker}/?exchange=${exchange}`;
    status.textContent = "TradingView · horário de Brasília · escolha o ativo e o intervalo acima ou nas ferramentas do gráfico.";
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
      allow_symbol_change: true, calendar: false, support_host: "https://www.tradingview.com",
      enabled_features: ["countdown"],
      overrides: { "mainSeriesProperties.showCountdown": true } });
    script.onerror = () => { if (container.isConnected) status.textContent = "Não foi possível carregar o gráfico. Tente recarregar ou abra o TradingView pelo link abaixo."; };
    container.append(chart, attribution, script);
    widget.replaceChildren(container);
  }
  symbol.addEventListener("change", load);
  interval.addEventListener("change", load);
  document.getElementById("tradingViewRetry").addEventListener("click", load);
  load();
})();

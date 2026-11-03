(() => {
  const activity = new FeedMinuteActivity();
  const formatTime = time => new Date(time).toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit", hour12: false });
  const formatNumber = n => n.toLocaleString("pt-BR");
  const tabs = [...document.querySelectorAll("[data-feed-tab]")];
  function selectTab(tab, focus = false) {
    for (const button of tabs) {
      const selected = button === tab;
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
      document.getElementById(button.getAttribute("aria-controls")).hidden = !selected;
    }
    if (focus) tab.focus();
    draw();
  }
  for (const [index, tab] of tabs.entries()) {
    tab.addEventListener("click", () => selectTab(tab));
    tab.addEventListener("keydown", event => {
      const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1
        : event.key === "ArrowRight" ? (index + 1) % tabs.length : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length : null;
      if (next !== null) { event.preventDefault(); selectTab(tabs[next], true); }
    });
  }
  const replay = document.getElementById("minuteIncludeReplay");
  const period = document.getElementById("minuteCoinPeriod");
  let optionKey = "";
  const scoreCoin = document.getElementById("scoreCoin");
  const scorePeriod = document.getElementById("scorePeriod");
  const scoreReplay = document.getElementById("scoreReplay");
  let scoreOptionsKey = "";
  function drawScore() {
    const available = activity.snapshot().coins.slice().sort((a, b) => a.symbol.localeCompare(b.symbol) || a.chain.localeCompare(b.chain));
    const keys = JSON.stringify(available.map(coin => coin.key));
    if (keys !== scoreOptionsKey) {
      const selected = scoreCoin.value;
      scoreCoin.innerHTML = '<option value="all">Todas as moedas</option>' + available.map(coin => '<option value="' + esc(coin.key) + '">' + esc(coin.symbol) + ' · ' + esc(coin.chain) + '</option>').join("");
      scoreCoin.value = available.some(coin => coin.key === selected) ? selected : "all";
      scoreOptionsKey = keys;
    }
    const score = activity.score({ minutes: Number(scorePeriod.value), coinKey: scoreCoin.value === "all" ? null : scoreCoin.value, includeReplay: scoreReplay.checked });
    document.getElementById("scoreBuyPeople").textContent = formatNumber(score.buyers);
    document.getElementById("scoreSellPeople").textContent = formatNumber(score.sellers);
    document.getElementById("scoreBuyUnit").textContent = score.buyers === 1 ? "pessoa" : "pessoas";
    document.getElementById("scoreSellUnit").textContent = score.sellers === 1 ? "pessoa" : "pessoas";
    document.getElementById("scoreBuyOperations").textContent = formatNumber(score.buyOperations) + (score.buyOperations === 1 ? " operação de compra" : " operações de compra");
    document.getElementById("scoreSellOperations").textContent = formatNumber(score.sellOperations) + (score.sellOperations === 1 ? " operação de venda" : " operações de venda");
    document.getElementById("scoreNote").textContent = (scoreReplay.checked ? "Histórico incluído. " : "Somente eventos recebidos ao vivo. ") + ((!score.buyOperations && !score.sellOperations) ? "Nenhuma operação dessas moedas recebida no período. " : "") + "Contagem parcial desta aba; reinicia ao recarregar. Cada pessoa conta uma vez por lado; quem comprou e vendeu conta nos dois." + (score.unidentified ? " " + formatNumber(score.unidentified) + " operações sem trader identificado não entram na contagem de pessoas." : "");
  }
  for (const control of [scoreCoin, scorePeriod, scoreReplay]) control.addEventListener("change", drawScore);
  function draw() {
    drawScore();
    const selected = period.value;
    const snapshot = activity.snapshot(replay.checked, selected === "all" ? null : Number(selected));
    const currentTime = Math.floor(Date.now() / 60000) * 60000;
    const current = snapshot.rows.find(row => row.time === currentTime) ?? { buy: 0, sell: 0, total: 0 };
    document.getElementById("minuteCurrent").textContent = `${formatTime(currentTime)} · ${formatNumber(current.buy)} compras · ${formatNumber(current.sell)} vendas · ${formatNumber(current.total)} operações`;
    document.getElementById("minuteHistory").innerHTML = snapshot.rows.flatMap(row => row.coins.map(coin => `<tr><td>${formatTime(row.time)}${row.time === currentTime ? ' <span class="tag">Agora</span>' : ""}</td><td><b>${esc(coin.symbol)}</b> <small class="muted">${esc(coin.chain)}</small></td><td class="num up">${formatNumber(coin.buy)}</td><td class="num down">${formatNumber(coin.sell)}</td><td class="num">${formatNumber(coin.total)}</td><td class="num muted">${formatNumber(coin.replay)}</td></tr>`)).join("") || '<tr><td colspan="6" class="empty">Aguardando operações neste período.</td></tr>';
    const nextKey = snapshot.rows.map(row => row.time).join(",");
    if (nextKey !== optionKey) {
      period.innerHTML = '<option value="all">Últimos 60 minutos</option>' + snapshot.rows.map(row => `<option value="${row.time}">${formatTime(row.time)}</option>`).join("");
      optionKey = nextKey;
    }
    period.value = snapshot.rows.some(row => String(row.time) === selected) ? selected : "all";
    // Se o minuto selecionado saiu da janela, o ranking acompanha o período completo.
    const ranking = period.value === selected ? snapshot.coins : activity.snapshot(replay.checked).coins;
    document.getElementById("minuteCoinRanking").innerHTML = ranking.slice(0, 20).map((coin, index) => `<tr><td>${index + 1}</td><td>${esc(coin.symbol)} <small class="muted">${esc(coin.chain)}</small></td><td class="num up">${formatNumber(coin.buy)}</td><td class="num down">${formatNumber(coin.sell)}</td><td class="num">${formatNumber(coin.buy + coin.sell)}</td></tr>`).join("") || '<tr><td colspan="5" class="empty">Nenhuma moeda com operações no período.</td></tr>';
  }
  replay.addEventListener("change", draw);
  period.addEventListener("change", draw);
  let pending = false;
  window.feedActivity = {
    observe(events) {
      activity.observe(events);
      if (!pending) { pending = true; requestAnimationFrame(() => { pending = false; draw(); }); }
    },
  };
  setInterval(draw, 10000);
  draw();
})();

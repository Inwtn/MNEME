// Relógio de referência: não lê nem exporta cotações do widget incorporado.
(() => {
  const durations = new Set([1, 3, 5, 15, 30, 60, 120, 240, 360, 720, 1440]);
  const ny = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });
  const auckland = new Intl.DateTimeFormat("en-US", { timeZone: "Pacific/Auckland", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  function format(seconds) {
    const parts = [Math.floor(seconds / 60) % 60, seconds % 60];
    if (seconds >= 3600) parts.unshift(Math.floor(seconds / 3600));
    return parts.map(v => String(v).padStart(2, "0")).join(":");
  }
  function remaining(symbol, interval, now = Date.now()) {
    const minutes = interval === "D" ? 1440 : Number(interval);
    if (!durations.has(minutes) || !Number.isFinite(now)) return { text: "Intervalo indisponível" };
    let anchor = 0, sessionClose = Infinity;
    const estimated = symbol.startsWith("OANDA:");
    if (estimated) {
      const p = Object.fromEntries(ny.formatToParts(now).map(v => [v.type, v.value]));
      const minute = Number(p.hour) * 60 + Number(p.minute);
      const gold = symbol === "OANDA:XAUUSD", open = (gold ? 18 : 17) * 60 + 5, close = 16 * 60 + 59;
      const weekend = p.weekday === "Sat" || (p.weekday === "Fri" && minute >= close) || (p.weekday === "Sun" && minute < open);
      const pause = minute >= close && minute < open;
      const nz = Object.fromEntries(auckland.formatToParts(now).map(v => [v.type, v.value]));
      const nzMinute = Number(nz.hour) * 60 + Number(nz.minute);
      if (weekend || pause || (symbol === "OANDA:NZDUSD" && nzMinute >= 419 && nzMinute < 425)) return { text: "Fora da sessão regular", estimated };
      // Previsão alinhada à virada diária de Nova York, com ajuste automático de DST.
      const elapsed = ((minute - 17 * 60 + 1440) % 1440) * 60000 + Number(p.second) * 1000 + ((now % 1000 + 1000) % 1000);
      anchor = now - elapsed;
      const toClose = ((close - minute + 1440) % 1440) * 60000 - Number(p.second) * 1000 - (now % 1000);
      sessionClose = now + toClose;
    } else if (!symbol.startsWith("BINANCE:")) return { text: "Ativo indisponível" };
    const duration = minutes * 60000;
    const closesAt = Math.min(anchor + (Math.floor((now - anchor) / duration) + 1) * duration, sessionClose);
    return { text: format(Math.max(1, Math.ceil((closesAt - now) / 1000))), closesAt, estimated };
  }
  globalThis.CandleClock = { remaining };
})();

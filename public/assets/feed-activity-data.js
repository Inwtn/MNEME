// Contagem observada nesta aba; cada evento conta uma operação, independentemente do valor.
globalThis.FeedMinuteActivity = class {
  constructor(now = Date.now) {
    this.now = now;
    this.seen = new Map();
    this.minutes = new Map();
  }
  prune() {
    const first = Math.floor(this.now() / 60000) * 60000 - 59 * 60000;
    for (const [id, time] of this.seen) if (time < first) this.seen.delete(id);
    for (const time of this.minutes.keys()) if (time < first) this.minutes.delete(time);
    return first;
  }
  observe(events) {
    const first = this.prune();
    const current = Math.floor(this.now() / 60000) * 60000;
    for (const event of events) {
      const time = Math.floor(Date.parse(event.eventTime) / 60000) * 60000;
      if (!event.eventId || this.seen.has(event.eventId) || !Number.isFinite(time)
        || time < first || time > current || !["buy", "sell"].includes(event.eventType)) continue;
      this.seen.set(event.eventId, time);
      let minute = this.minutes.get(time);
      if (!minute) { minute = { time, coins: new Map(), participants: [] }; this.minutes.set(time, minute); }
      // Endereço e rede evitam juntar tokens distintos com o mesmo ticker.
      const key = JSON.stringify([event.chain ?? "", event.tokenAddress ?? event.tokenSymbol ?? ""]);
      let coin = minute.coins.get(key);
      if (!coin) {
        coin = { key, symbol: event.tokenSymbol ?? "Sem ticker", chain: event.chain ?? "—", buy: 0, sell: 0, replayBuy: 0, replaySell: 0 };
        minute.coins.set(key, coin);
      }
      const handle = typeof event.traderHandle === "string" ? event.traderHandle.trim().toLowerCase() : "";
      const trader = event.userId ? `id:${event.userId}` : handle ? `handle:${handle}` : null;
      minute.participants.push({ symbol: String(event.tokenSymbol ?? "").trim().toUpperCase(), trader, side: event.eventType, key, replay: !!event.replay, at: Date.parse(event.eventTime) });
      coin[event.eventType]++;
      if (event.replay) coin[event.eventType === "buy" ? "replayBuy" : "replaySell"]++;
    }
  }
  score({ minutes = 5, coinKey = null, includeReplay = true, symbols = null } = {}) {
    this.prune();
    const since = this.now() - minutes * 60000;
    const buyers = new Set(), sellers = new Set();
    let buyOperations = 0, sellOperations = 0, unidentified = 0;
    for (const minute of this.minutes.values()) for (const trade of minute.participants) {
      if ((symbols && !symbols.includes(trade.symbol)) || trade.at < since || (!includeReplay && trade.replay) || (coinKey !== null && trade.key !== coinKey)) continue;
      if (trade.side === "buy") buyOperations++; else sellOperations++;
      if (!trade.trader) { unidentified++; continue; }
      (trade.side === "buy" ? buyers : sellers).add(trade.trader);
    }
    return { buyers: buyers.size, sellers: sellers.size, buyOperations, sellOperations, unidentified };
  }
  snapshot(includeReplay = true, selectedMinute = null) {
    this.prune();
    const coins = new Map();
    const rows = [...this.minutes.values()].sort((a, b) => b.time - a.time).map(minute => {
      let buy = 0, sell = 0, replay = 0;
      const minuteCoins = [];
      for (const coin of minute.coins.values()) {
        const b = coin.buy - (includeReplay ? 0 : coin.replayBuy);
        const s = coin.sell - (includeReplay ? 0 : coin.replaySell);
        const historical = includeReplay ? coin.replayBuy + coin.replaySell : 0;
        buy += b; sell += s; replay += historical;
        if (b + s > 0) minuteCoins.push({ ...coin, buy: b, sell: s, replay: historical, total: b + s });
        if (selectedMinute !== null && minute.time !== selectedMinute) continue;
        const aggregate = coins.get(coin.key) ?? { ...coin, buy: 0, sell: 0 };
        aggregate.buy += b; aggregate.sell += s;
        coins.set(coin.key, aggregate);
      }
      minuteCoins.sort((a, b) => b.total - a.total || a.symbol.localeCompare(b.symbol));
      return { time: minute.time, buy, sell, replay, total: buy + sell, coins: minuteCoins };
    });
    return { rows, coins: [...coins.values()].filter(c => c.buy + c.sell > 0)
      .sort((a, b) => (b.buy + b.sell) - (a.buy + a.sell) || a.symbol.localeCompare(b.symbol)) };
  }
};

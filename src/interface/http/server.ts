import { timingSafeEqual } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createServer, type Server } from "node:http";
import { extname, normalize, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import type { ControlController, DashboardController, HealthController, SettingsController } from "./controllers.js";
import { Router, sendJson } from "./router.js";
import type { MarketController } from "./marketController.js";

const PUBLIC_DIR = resolve(fileURLToPath(new URL("../../../public/", import.meta.url)));
const PAGES: Record<string, string> = { "/": "index.html", "/configuracoes": "settings.html" };
const TYPES: Record<string, string> = { ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".svg": "image/svg+xml", ".png": "image/png", ".webmanifest": "application/manifest+json",
};

/**
 * Servidor HTTP do painel. Por padrão só escuta em 127.0.0.1; fora disso exige senha.
 * Num servidor, prefira manter 127.0.0.1 e acessar por túnel SSH.
 * Escritas exigem o cabeçalho x-mneme: um site
 * de terceiros não consegue enviá-lo sem permissão de CORS, o que impede que outra
 * página aberta no navegador mande o bot comprar ou vender.
 */
export function startHttpServer(
  opts: { host: string; port: number; password: string | null },
  c: { dashboard: DashboardController; settings: SettingsController; control: ControlController; health: HealthController; market: MarketController },
): Server {
  const { host, port, password } = opts;
  const router = new Router()
    .on("GET", "/api/health", c.health.get)
    .on("GET", "/api/market/candles", c.market.candles)
    .on("GET", "/api/state", c.dashboard.state)
    .on("GET", "/api/stream", c.dashboard.stream)
    .on("GET", "/api/settings", c.settings.get)
    .on("PUT", "/api/settings", c.settings.put)
    .on("POST", "/api/pause", c.control.pause)
    .on("POST", "/api/resume", c.control.resume)
    .on("POST", "/api/positions/:id/close", c.control.closePosition);

  const server = createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    try {
      if (password && url.pathname !== "/api/health" && !authorized(req.headers.authorization, password)) {
        res.writeHead(401, { "www-authenticate": `Basic realm="MNEME", charset="UTF-8"` });
        return res.end("Senha necessária.");
      }
      if (req.method !== "GET" && req.headers["x-mneme"] !== "1") return sendJson(res, 403, { error: "Cabeçalho x-mneme ausente." });

      const route = router.match(req.method ?? "GET", url.pathname);
      if (route) return await route.handler(req, res, route.params);

      if (req.method === "GET") {
        const file = PAGES[url.pathname] ?? (url.pathname.startsWith("/assets/") ? url.pathname.slice(1) : null);
        if (file) {
          const path = resolve(PUBLIC_DIR, normalize(file));
          if (!path.startsWith(PUBLIC_DIR + sep)) return sendJson(res, 404, { error: "Não encontrado." });
          const body = await readFile(path).catch(() => null);
          if (body) {
            res.writeHead(200, { "content-type": TYPES[extname(path)] ?? "application/octet-stream", "cache-control": "no-store" });
            return res.end(body);
          }
        }
      }
      sendJson(res, 404, { error: "Não encontrado." });
    } catch (err) {
      sendJson(res, 500, { error: err instanceof Error ? err.message : String(err) });
    }
  });

  server.on("error", (err: NodeJS.ErrnoException) => {
    if (err.code === "EADDRINUSE") {
      console.error(`A porta ${port} já está em uso por outro programa. Defina MNEME_PORT no .env com outra porta.`);
      process.exit(1);
    }
    throw err;
  });
  server.listen(port, host);
  return server;
}

/** Autenticação básica: qualquer usuário, senha do MNEME_PASSWORD (comparação em tempo constante). */
function authorized(header: string | undefined, password: string): boolean {
  if (!header?.startsWith("Basic ")) return false;
  const decoded = Buffer.from(header.slice(6), "base64").toString("utf8");
  const given = Buffer.from(decoded.slice(decoded.indexOf(":") + 1));
  const expected = Buffer.from(password);
  return given.length === expected.length && timingSafeEqual(given, expected);
}

// Dev-сервер: статика из этой папки, /api/* проксируется на prism mock (порт 4010).
import http from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
const target = process.env.API_URL || "http://127.0.0.1:4010";
const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json" };

http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname.startsWith("/api/")) {
    const body = ["GET", "HEAD"].includes(req.method) ? undefined : req;
    const up = await fetch(target + url.pathname + url.search, {
      method: req.method, headers: { "content-type": req.headers["content-type"] || "" }, body, duplex: "half",
    }).catch(() => null);
    if (!up) { res.writeHead(502).end(); return; }
    res.writeHead(up.status, Object.fromEntries(up.headers));
    res.end(Buffer.from(await up.arrayBuffer()));
    return;
  }
  const rel = normalize(url.pathname === "/" ? "/index.html" : url.pathname).replace(/^(\.\.[/\\])+/, "");
  try {
    const data = await readFile(join(root, rel));
    res.writeHead(200, { "content-type": types[extname(rel)] || "application/octet-stream" }).end(data);
  } catch {
    res.writeHead(404).end("not found");
  }
}).listen(8000, "127.0.0.1", () => console.log("http://127.0.0.1:8000 -> prism", target));

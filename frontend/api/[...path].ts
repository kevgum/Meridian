/**
 * Vercel Serverless Function — production equivalent of vite.config.ts's dev
 * proxy. Injects Elasticsearch Basic Auth server-side so the browser never
 * sees the password, then forwards the request to the tunnelled cluster.
 *
 * ELASTIC_TUNNEL_URL and ELASTIC_PASSWORD are Vercel environment variables
 * (production scope), never committed to the repo.
 */
export default async function handler(req: any, res: any) {
  const tunnelUrl = process.env.ELASTIC_TUNNEL_URL;
  const password = process.env.ELASTIC_PASSWORD;

  if (!tunnelUrl || !password) {
    res.status(503).json({ error: 'Elasticsearch tunnel not configured' });
    return;
  }

  const target = tunnelUrl.replace(/\/$/, '') + String(req.url).replace(/^\/api/, '');
  const auth = Buffer.from(`elastic:${password}`).toString('base64');

  try {
    const upstream = await fetch(target, {
      headers: { Authorization: `Basic ${auth}` },
    });
    const body = await upstream.text();
    res.status(upstream.status);
    res.setHeader('Content-Type', upstream.headers.get('content-type') || 'application/json');
    res.send(body);
  } catch (err) {
    res.status(502).json({ error: 'Elasticsearch tunnel unreachable', detail: String(err) });
  }
}

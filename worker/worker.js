// BarrierCheck AI — Cloudflare Worker proxy for Upstage Studio API.
// The API key lives ONLY in the Worker secret UPSTAGE_API_KEY (never in this file or the repo).
// Required settings (Cloudflare dashboard → Worker → Settings → Variables):
//   UPSTAGE_API_KEY  (Secret)  : Upstage API key of the organization that owns the workflow
//   PROJECT_ID       (Text)    : Studio project id, e.g. proj_...
//   WORKFLOW_ID      (Text)    : Studio workflow id, e.g. agt_...
//   CONFIG_ID        (Text)    : Studio config number, e.g. 4
//   ALLOWED_ORIGIN   (Text)    : https://yeono1220.github.io
//   ACCESS_CODE      (Secret, optional): if set, requests must send header x-access-code with this value
const API = 'https://api.upstage.ai/v2';
const MAX_BYTES = 30 * 1024 * 1024;

function cors(env, origin) {
  const ok = origin && origin === env.ALLOWED_ORIGIN;
  return {
    'Access-Control-Allow-Origin': ok ? origin : env.ALLOWED_ORIGIN,
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type,Accept,x-access-code',
    'Access-Control-Max-Age': '600',
    'Vary': 'Origin',
  };
}
const json = (obj, status, headers) => new Response(JSON.stringify(obj), { status, headers: { ...headers, 'Content-Type': 'application/json' } });

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin');
    const h = cors(env, origin);
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: h });
    if (origin !== env.ALLOWED_ORIGIN) return json({ error: 'Origin not allowed' }, 403, h);
    if (env.ACCESS_CODE && request.headers.get('x-access-code') !== env.ACCESS_CODE) return json({ error: 'Access code required' }, 401, h);

    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, '');
    let body = null, ctype = request.headers.get('Content-Type');

    // Allow only the four calls the demo needs.
    if (request.method === 'GET' && path === '/status') {
      return json({ configured: true, label: env.LABEL || 'BarrierCheck AI', output_contract: 'compact' }, 200, h);
    } else if (request.method === 'POST' && path === '/files') {
      const len = Number(request.headers.get('Content-Length') || 0);
      if (len > MAX_BYTES) return json({ error: 'File too large' }, 413, h);
      body = request.body;
    } else if (request.method === 'GET' && /^\/files\/[A-Za-z0-9_-]+$/.test(path)) {
      // status polling
    } else if (request.method === 'POST' && path === '/responses') {
      let incoming;
      try { incoming = await request.json(); } catch { return json({ error: 'Invalid JSON' }, 400, h); }
      const fileId = incoming?.input?.[0]?.content?.[0]?.file_id;
      if (typeof fileId !== 'string' || !/^[A-Za-z0-9_-]+$/.test(fileId)) return json({ error: 'file_id required' }, 400, h);
      // Workflow and config are fixed here; the browser cannot choose another workflow.
      body = JSON.stringify({ model: env.WORKFLOW_ID, config_id: String(env.CONFIG_ID), include: ['all'],
        input: [{ role: 'user', content: [{ type: 'input_file', file_id: fileId }] }] });
      ctype = 'application/json';
    } else if (request.method === 'GET' && /^\/responses\/[A-Za-z0-9_-]+$/.test(path)) {
      // job polling
    } else {
      return json({ error: 'Not allowed' }, 404, h);
    }

    const headers = { 'Authorization': 'Bearer ' + env.UPSTAGE_API_KEY, 'Accept': 'application/json', 'x-project-id': env.PROJECT_ID };
    if (ctype) headers['Content-Type'] = ctype;
    const upstream = await fetch(API + path + url.search, { method: request.method, headers, body });
    const text = await upstream.text();
    return new Response(text, { status: upstream.status, headers: { ...h, 'Content-Type': 'application/json' } });
  },
};

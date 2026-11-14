// Cloudflare Pages Function: GET /api/warranty?serial=AH-AQ33-0001
// Reads a record from the WARRANTY_KV namespace bound to this Pages project.
// Buyer names and emails are never returned, only details about the piece.

const SERIAL = /^AH-[A-Z0-9]{2,6}-\d{4}$/;

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'x-content-type-options': 'nosniff'
    }
  });
}

export async function onRequestGet({ request, env }) {
  const raw = new URL(request.url).searchParams.get('serial') || '';
  const serial = raw.trim().toUpperCase();

  if (!SERIAL.test(serial)) return json({ found: false, error: 'invalid_serial' }, 400);
  if (!env.WARRANTY_KV) return json({ found: false, error: 'not_configured' }, 503);

  const stored = await env.WARRANTY_KV.get(serial);
  if (!stored) return json({ found: false }, 404);

  let rec;
  try { rec = JSON.parse(stored); } catch (e) { return json({ found: false, error: 'bad_record' }, 500); }

  return json({
    found: true,
    serial,
    piece: rec.piece,
    materials: rec.materials,
    strungOn: rec.strungOn,
    cord: rec.cord,
    lot: rec.lot
  });
}

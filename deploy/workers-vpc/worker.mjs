const PUBLIC_ORIGIN = 'https://fucheng.momonong.workers.dev';

function unavailable() {
  return new Response('府城球館系統準備中，請稍後再試。', {
    status: 503,
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-store',
      'Retry-After': '30',
    },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.origin !== PUBLIC_ORIGIN) {
      return new Response('Invalid origin', { status: 400 });
    }
    const clientIP = request.headers.get('CF-Connecting-IP');
    if (!clientIP || clientIP.length > 64 || !/^[0-9a-f:.]+$/i.test(clientIP) || !env.fucheng) {
      return unavailable();
    }
    const headers = new Headers(request.headers);
    for (const name of ['Forwarded', 'X-Forwarded-For', 'X-Forwarded-Proto',
      'X-Forwarded-Host', 'CF-Connecting-IP', 'True-Client-IP']) {
      headers.delete(name);
    }
    headers.set('Host', url.host);
    headers.set('CF-Connecting-IP', clientIP);
    headers.set('X-Forwarded-Proto', 'https');
    // Keep Origin, session cookies and CSRF unchanged; the app validates them.
    // The VPC Service selects 172.30.98.2:8000; this URL supplies its public Host.
    url.protocol = 'http:';
    try {
      const forwarded = new Request(url, request);
      const response = await env.fucheng.fetch(new Request(forwarded, {
        headers, redirect: 'manual',
      }));
      const result = new Response(response.body, response);
      result.headers.set('Cache-Control', 'no-store');
      return result;
    } catch {
      return unavailable();
    }
  },
};

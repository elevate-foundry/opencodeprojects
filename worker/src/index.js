/**
 * fable-proxy: Cloudflare Worker that forwards Anthropic API requests.
 * 
 * - Stores ANTHROPIC_API_KEY as a Cloudflare secret (never in code)
 * - Forwards all /v1/* requests to api.anthropic.com
 * - Adds CORS headers for flexibility
 * - Rejects requests without a valid bearer token (FABLE_TOKEN secret)
 */

export default {
  async fetch(request, env) {
    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
          "Access-Control-Allow-Headers": "*",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    const url = new URL(request.url);

    // Health check
    if (url.pathname === "/" || url.pathname === "/health") {
      return new Response(JSON.stringify({ status: "ok", proxy: "fable" }), {
        headers: { "content-type": "application/json" },
      });
    }

    // Only proxy /v1/* paths
    if (!url.pathname.startsWith("/v1/")) {
      return new Response("Not found", { status: 404 });
    }

    // Auth gate: require FABLE_TOKEN if set (optional — skip if not configured)
    if (env.FABLE_TOKEN) {
      const authHeader = request.headers.get("x-fable-token") || "";
      if (authHeader !== env.FABLE_TOKEN) {
        return new Response("Unauthorized", { status: 401 });
      }
    }

    // Build upstream request
    const upstream = `${env.UPSTREAM}${url.pathname}${url.search}`;
    const headers = new Headers(request.headers);

    // Inject the real API key (stored as Cloudflare secret)
    if (env.ANTHROPIC_API_KEY) {
      headers.set("x-api-key", env.ANTHROPIC_API_KEY);
    }

    // Remove host header to avoid upstream rejection
    headers.delete("host");
    headers.delete("x-fable-token");

    const upstreamResponse = await fetch(upstream, {
      method: request.method,
      headers,
      body: request.method !== "GET" ? request.body : undefined,
    });

    // Return response with CORS
    const response = new Response(upstreamResponse.body, {
      status: upstreamResponse.status,
      statusText: upstreamResponse.statusText,
      headers: upstreamResponse.headers,
    });
    response.headers.set("Access-Control-Allow-Origin", "*");

    return response;
  },
};

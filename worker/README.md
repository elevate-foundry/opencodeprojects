# fable-proxy (Cloudflare Worker)

Stable URL proxy for Anthropic API. Replaces the broken `localhost:8377` dependency.

## Deploy (one-time)

```bash
cd worker
npm install
npx wrangler login          # opens browser, auth with Cloudflare
npx wrangler deploy         # deploys to https://fable-proxy.<your-subdomain>.workers.dev

# Store your API key as a secret (never in code):
npx wrangler secret put ANTHROPIC_API_KEY
# paste your key when prompted

# Optional: add an auth token so only your devices can use it:
npx wrangler secret put FABLE_TOKEN
```

## Use on Termux

After deploying, update your phone's opencode.json:

```bash
sed -i 's|http://127.0.0.1:8377|https://fable-proxy.YOUR-SUBDOMAIN.workers.dev|' ~/opencodeprojects/opencode.json
```

If you set FABLE_TOKEN, also add to .env:
```
FABLE_TOKEN=your-secret-token
```

And the fable binary will send it via the `x-fable-token` header (requires a small patch to opencode-src).

## For fable-cli

```bash
export ANTHROPIC_BASE_URL=https://fable-proxy.YOUR-SUBDOMAIN.workers.dev
python3 bin/fable-cli
```

## Cost

Cloudflare Workers free tier: 100,000 requests/day. More than enough.

# am-client S3 + CloudFront Deploy — Design

**Date:** 2026-07-09
**Status:** Approved for implementation planning
**Repo slot:** `aws-deploy-demo/` (Track 1, Day 3) — frontend half of the deploy, following
the already-applied ECS Fargate/ALB/RDS backend.

## Context

The `docker-101/anagrams-2` app's backend (Express API + MySQL) is live on ECS Fargate
behind an ALB, provisioned via Terraform in `aws-deploy-demo/terraform/` (29 resources,
`terraform apply` already run, verified working). The one piece of the original
`aws-deploy-demo/README.md` task list still outstanding is deploying the React/Vite
client (`am-client`) as a static site. This spec covers that remaining piece.

`am-client` currently hardcodes every API call to `http://localhost:3001/...` (fetch
calls across `App.jsx`, `Login.jsx`, `SignUp.jsx`, `Game.jsx`, `PlayNowCard.jsx`,
`ChallengeCard.jsx`, `FriendsCard.jsx`, plus an `EventSource` connection for real-time
updates in `ContextProvider.jsx`). The ALB is HTTP-only (no ACM cert, no custom domain).

## Explicit scope decisions

- **No custom domain.** Use CloudFront's default `*.cloudfront.net` hostname and its
  default TLS certificate. No Route53 purchase, no ACM cert request.
- **CloudFront fronts both the static app and the API**, as two behaviors on one
  distribution, rather than giving the ALB its own HTTPS listener. This avoids the
  domain requirement (ACM can't issue a cert for a raw ALB DNS name) while still
  avoiding mixed-content errors, since the browser only ever talks to the single
  HTTPS CloudFront hostname.
- **API routes move behind an `/api` prefix** on the Express server, so CloudFront can
  route on a single clean path pattern (`/api/*` → ALB, everything else → S3) instead
  of enumerating today's ~10 flat endpoint paths individually (brittle — new endpoints
  would silently 404 through S3 otherwise).
- **S3 bucket stays fully private**, accessed only via CloudFront through Origin Access
  Control (OAC). No S3 static-website-hosting mode, no public bucket policy.
- **IaC:** Terraform, added to the existing `aws-deploy-demo/terraform/` scaffold —
  consistent with the backend work.
- **Deploy mechanism:** manual `npm run build` → `aws s3 sync` → CloudFront
  invalidation, matching the existing "no CI yet" pattern (ECR pushes are also manual
  today). GitHub Actions CI remains the deferred stretch goal from the README.
- **`terraform apply` will be run as part of this work** (not left as a manual
  follow-up step), since S3 + CloudFront cost is trivial (well under $1-2/month for
  demo-level traffic) compared to the RDS/NAT-style always-on costs that motivated
  deferring `apply` on the backend piece.

## Architecture & Components

1. **S3 bucket** — private, holds the built `am-client/dist/` output. No website
   hosting config; CloudFront is the only reader (via OAC bucket policy).
2. **CloudFront distribution**, single hostname:
   - Default behavior (`*`) → S3 origin via OAC. Cached normally (static assets).
   - `/api/*` behavior → ALB origin, `http-only` origin protocol policy (ALB has no
     TLS listener), **caching disabled** (TTL=0, all headers/cookies/query strings
     forwarded) so POST bodies, auth cookies, and the `/api/events` SSE stream pass
     through live rather than being cached or buffered.
   - Custom error response: S3's 403 (object not found, since the bucket is private —
     S3 returns 403 rather than 404 for unauthorized/missing keys via OAC) is rewritten
     to serve `/index.html` with a 200 status, so `react-router-dom`'s `BrowserRouter`
     client-side routes survive a hard refresh or direct link.
   - No ACM certificate — CloudFront's default certificate covers `*.cloudfront.net`.
3. **Terraform** — new file(s) in `aws-deploy-demo/terraform/` (e.g. `s3_cloudfront.tf`)
   alongside the existing VPC/ECS/ALB/RDS resources. New output for the CloudFront
   distribution's domain name (the app's public URL going forward).

## Data flow

The browser only ever talks to one origin: the CloudFront hostname
(`https://<distribution-id>.cloudfront.net`). Requests to `/`, `/game`, `/assets/*.js`,
etc. are served from S3 (cached). Requests to `/api/*` are forwarded by CloudFront to
the ALB uncached, which forwards to the Express server's routes (now mounted under
`/api`). This makes client and API same-origin in production — no CORS, and any
cookie-based auth works without cross-site cookie complications. This is a strict
improvement over the current local-dev setup, where client (`:5173`) and server
(`:3001`) are genuinely different origins and CORS is required.

## Code changes

- **Server** (`docker-101/anagrams-2/server/src/index.js`): mount all existing routes
  under `/api` (`/login` → `/api/login`, `/events` → `/api/events`, etc).
- **Client** (`am-client`): introduce an `API_BASE_URL` constant read from
  `import.meta.env.VITE_API_URL`. Replace every hardcoded `http://localhost:3001/...`
  (fetch and `EventSource` call sites listed above) with `${API_BASE_URL}/...`.
  - Local dev: `VITE_API_URL=http://localhost:3001/api` — behavior unchanged from
    today aside from the new prefix.
  - Production build: `VITE_API_URL=/api` — a relative path; no domain is baked into
    the built JS bundle, since in production the browser is already talking to
    CloudFront and CloudFront does the routing.
- **CORS**: server's existing CORS config must continue to allow the local-dev
  cross-origin case (`:5173` → `:3001`). No CORS handling is needed in production
  (same-origin via CloudFront).

## Deploy workflow

1. `cd am-client && npm run build` → produces `dist/`.
2. `aws s3 sync dist/ s3://<bucket> --delete`.
3. `aws cloudfront create-invalidation --distribution-id <id> --paths "/*"` — required
   on every deploy since CloudFront caches aggressively; without it, redeploys won't
   be visible to existing visitors.

These three steps are documented in `aws-deploy-demo/README.md` (and/or a
`terraform/README.md` section), matching the existing manual ECR-push instructions.
This is the natural seam where the deferred CI stretch goal (GitHub Actions
build/push) would plug in later.

## Verification

After `terraform apply` (CloudFront distributions take 5-15 minutes to reach
`Deployed` status):

- Load the CloudFront URL in a browser; confirm the app shell and assets load with no
  mixed-content or CORS errors in the network tab.
- Sign up / log in — confirms `/api/*` → ALB routing and cookie handling work.
- Play a game round and exercise the friends/challenge flow.
- Specifically verify the SSE `/api/events` stream (friend request notifications) —
  flagged as the one piece not guaranteed to work cleanly on the first try, since
  streaming through a CDN is more failure-prone than plain request/response. Debug
  live if it misbehaves rather than assuming correctness from the design.
- Hard-refresh on a non-root client-side route (e.g. `/game`) to confirm the
  403→`index.html` rewrite serves the SPA correctly instead of an error page.

## Out of scope

- Custom domain / Route53 / ACM certificate.
- HTTPS on the ALB directly.
- CI/CD (GitHub Actions + OIDC) — remains the deferred stretch goal.
- Any change to the RapidAPI third-party integration in `am-client/src/constants.js`
  (unrelated to this deploy).

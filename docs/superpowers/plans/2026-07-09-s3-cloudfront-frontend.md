# am-client S3 + CloudFront Deploy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy `am-client` (the Vite/React frontend) to a CloudFront distribution backed by a private S3 bucket, with `/api/*` requests on the same distribution forwarded to the already-live ALB — so the whole app is reachable over HTTPS from one URL with no custom domain and no mixed-content errors.

**Architecture:** One CloudFront distribution, two origins: S3 (via Origin Access Control) for the built static app, and the existing ALB (HTTP-only, origin-to-origin) for `/api/*`. The Express server's routes move behind an `/api` prefix so CloudFront can route on that single path pattern. The client swaps every hardcoded `http://localhost:3001/...` call for a `VITE_API_URL`-driven `API_BASE_URL` constant (relative `/api` in production, unchanged `http://localhost:3001/api` in local dev).

**Tech Stack:** Terraform (AWS provider ~> 5.0), AWS S3, CloudFront (OAC, managed cache/origin-request policies), Express (Node), Vite/React.

## Global Constraints

- Region: `us-east-1` (all existing resources already live there; CloudFront itself is global and doesn't require this, but the S3 bucket does).
- No custom domain, no ACM certificate — use CloudFront's default `*.cloudfront.net` certificate.
- Terraform code lives in `aws-deploy-demo/terraform/`, following the existing scaffold's conventions: `${var.project_name}-<thing>` naming, `default_tags` (Project/ManagedBy) plus a resource-specific `Name` tag, provider versions already pinned in `versions.tf` (`aws ~> 5.0`, `random ~> 3.6`).
- AWS credentials are already configured in this environment (`aws sts get-caller-identity` resolves to account `798294347421`, confirmed during the backend deploy).
- **`terraform apply` runs live as part of this plan** (Task 4) — explicitly agreed with the user, since S3 + CloudFront cost is trivial (well under $1-2/month for demo traffic) compared to the RDS/ALB fixed costs that motivated deferring `apply` on the backend piece.
- `docker-101/anagrams-2/server/Dockerfile.dev` (local dev) is untouched; only the production `Dockerfile` image gets rebuilt/pushed (Task 5).
- Docker builds must use `--platform linux/amd64` — Fargate defaults to X86_64 and a plain `docker build` on Apple Silicon produces an arm64 image that won't run (hit and fixed once already during the backend deploy; the existing README's redeploy instructions are missing this flag and get corrected in Task 7).
- Out of scope: CI/CD (GitHub Actions), any change to the RapidAPI integration in `am-client/src/constants.js`, HTTPS on the ALB directly.
- Full design context: `docs/superpowers/specs/2026-07-09-s3-cloudfront-frontend-design.md`.

---

### Task 1: Move Express routes behind `/api` and update the ALB health check path

**Files:**
- Modify: `docker-101/anagrams-2/server/src/index.js` (11 route path strings)
- Modify: `aws-deploy-demo/terraform/variables.tf:37-41` (`health_check_path` default)

**Interfaces:**
- Consumes: nothing new
- Produces: every API route now lives under `/api/*` (`/api/signup`, `/api/login`, `/api/score`, `/api/me`, `/api/friend-request`, `/api/friends/accept`, `/api/friends/decline`, `/api/challenge`, `/api/challenges/:id/accept`, `/api/events`, `/api/health`) — consumed by Task 2 (client call sites), Task 3 (CloudFront's `/api/*` behavior), and Task 5 (ECS redeploy)

- [ ] **Step 1: Prefix every route with `/api`**

In `docker-101/anagrams-2/server/src/index.js`, apply these exact replacements (one per route registration):

```
app.post("/signup", async (req, res) => {          →  app.post("/api/signup", async (req, res) => {
app.post("/login", async (req, res) => {            →  app.post("/api/login", async (req, res) => {
app.post('/score', authenticateToken, ...           →  app.post('/api/score', authenticateToken, ...
app.get('/me', authenticateToken, ...                →  app.get('/api/me', authenticateToken, ...
app.post('/friend-request', authenticateToken, ...   →  app.post('/api/friend-request', authenticateToken, ...
app.post("/friends/accept", authenticateToken, ...   →  app.post("/api/friends/accept", authenticateToken, ...
app.post("/friends/decline", authenticateToken, ...  →  app.post("/api/friends/decline", authenticateToken, ...
app.post("/challenge", authenticateToken, ...        →  app.post("/api/challenge", authenticateToken, ...
app.post("/challenges/:id/accept", authenticateToken, ...  →  app.post("/api/challenges/:id/accept", authenticateToken, ...
app.get('/events', authenticateToken, ...            →  app.get('/api/events', authenticateToken, ...
app.get("/health", (req, res) => {                   →  app.get("/api/health", (req, res) => {
```

Concretely, each is a one-line change, e.g.:

```javascript
// before
app.post("/signup", async (req, res) => {

// after
app.post("/api/signup", async (req, res) => {
```

Apply the same pattern to all 11 lines listed above — only the path string changes, nothing else in each route body.

- [ ] **Step 2: Update the ALB health check path variable**

In `aws-deploy-demo/terraform/variables.tf`, change:

```hcl
variable "health_check_path" {
  description = "ALB target group health check path"
  type        = string
  default     = "/health"
}
```

to:

```hcl
variable "health_check_path" {
  description = "ALB target group health check path"
  type        = string
  default     = "/api/health"
}
```

- [ ] **Step 3: Verify the server routes locally**

```bash
cd docker-101/anagrams-2/server
npm install   # only if node_modules is missing
npm start &
SERVER_PID=$!
sleep 2
curl -s http://localhost:3001/api/health
echo
curl -s -o /dev/null -w "old path status: %{http_code}\n" http://localhost:3001/health
kill $SERVER_PID
```

Expected: first curl prints `{"status":"ok"}`; second line prints `old path status: 404` (confirming the flat `/health` path no longer resolves).

- [ ] **Step 4: Verify the Terraform variable change with a real plan**

Step 3 leaves the shell in `docker-101/anagrams-2/server` — move back up to the Terraform directory:

```bash
cd ../../../aws-deploy-demo/terraform
terraform plan
```

Expected: `Plan: 0 to add, 1 to change, 0 to destroy.` — the one change is `aws_lb_target_group.api`'s `health_check.path` moving from `/health` to `/api/health`.

- [ ] **Step 5: Commit**

```bash
git add docker-101/anagrams-2/server/src/index.js aws-deploy-demo/terraform/variables.tf
git commit -m "Move API routes behind /api prefix for CloudFront routing"
```

---

### Task 2: Client — introduce `API_BASE_URL` and replace every hardcoded API call

**Files:**
- Modify: `docker-101/anagrams-2/am-client/src/constants.js`
- Modify: `docker-101/anagrams-2/am-client/src/App.jsx`
- Modify: `docker-101/anagrams-2/am-client/src/contexts/ContextProvider.jsx`
- Modify: `docker-101/anagrams-2/am-client/src/components/Login.jsx`
- Modify: `docker-101/anagrams-2/am-client/src/components/SignUp.jsx`
- Modify: `docker-101/anagrams-2/am-client/src/components/Game.jsx`
- Modify: `docker-101/anagrams-2/am-client/src/components/play-now-card/PlayNowCard.jsx`
- Modify: `docker-101/anagrams-2/am-client/src/components/challenge-card/ChallengeCard.jsx`
- Modify: `docker-101/anagrams-2/am-client/src/components/friends-card/FriendsCard.jsx`

**Interfaces:**
- Consumes: `docker-101/anagrams-2/server`'s `/api/*` routes from Task 1 (functionally, not at build time — the client doesn't import server code)
- Produces: `API_BASE_URL` exported from `am-client/src/constants.js`, consumed by Task 6's production build (`VITE_API_URL=/api npm run build`)

- [ ] **Step 1: Add `API_BASE_URL` to `constants.js`**

In `docker-101/anagrams-2/am-client/src/constants.js`, change:

```javascript

export const API_URL = 'https://wordsapiv1.p.rapidapi.com/words/';
```

to:

```javascript

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:3001/api';

export const API_URL = 'https://wordsapiv1.p.rapidapi.com/words/';
```

- [ ] **Step 2: `App.jsx`**

Change the import:

```javascript
// before
import { Home, Game, Login, SignUp } from './components';

// after
import { Home, Game, Login, SignUp } from './components';
import { API_BASE_URL } from './constants';
```

Change the fetch call:

```javascript
// before
            fetch("http://localhost:3001/me", {

// after
            fetch(`${API_BASE_URL}/me`, {
```

- [ ] **Step 3: `ContextProvider.jsx`**

Change the import:

```javascript
// before
import React, { createContext, useContext, useEffect, useRef, useState } from 'react';

// after
import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '../constants';
```

Change the fetch call:

```javascript
// before
        fetch("http://localhost:3001/me", {

// after
        fetch(`${API_BASE_URL}/me`, {
```

Change the `EventSource` call:

```javascript
// before
        const es = new EventSource(`http://localhost:3001/events?token=${token}`);

// after
        const es = new EventSource(`${API_BASE_URL}/events?token=${token}`);
```

- [ ] **Step 4: `Login.jsx`**

Change the import:

```javascript
// before
import { useStateContext } from '../contexts/ContextProvider';

// after
import { useStateContext } from '../contexts/ContextProvider';
import { API_BASE_URL } from '../constants';
```

Change the fetch call:

```javascript
// before
        fetch("http://localhost:3001/login", {

// after
        fetch(`${API_BASE_URL}/login`, {
```

- [ ] **Step 5: `SignUp.jsx`**

Change the import:

```javascript
// before
import { useStateContext } from '../contexts/ContextProvider';

// after
import { useStateContext } from '../contexts/ContextProvider';
import { API_BASE_URL } from '../constants';
```

Change the fetch call:

```javascript
// before
        fetch("http://localhost:3001/signup", {

// after
        fetch(`${API_BASE_URL}/signup`, {
```

- [ ] **Step 6: `Game.jsx`**

Change the import (add `API_BASE_URL` to the existing constants import):

```javascript
// before
import { scores, options, API_URL, letterSets } from "../constants";

// after
import { scores, options, API_URL, API_BASE_URL, letterSets } from "../constants";
```

Change the fetch call:

```javascript
// before
        fetch("http://localhost:3001/score", {

// after
        fetch(`${API_BASE_URL}/score`, {
```

- [ ] **Step 7: `PlayNowCard.jsx`**

Change the import:

```javascript
// before
import { letterSets } from "../../constants";

// after
import { letterSets, API_BASE_URL } from "../../constants";
```

Change the fetch call:

```javascript
// before
        fetch("http://localhost:3001/challenge", {

// after
        fetch(`${API_BASE_URL}/challenge`, {
```

- [ ] **Step 8: `ChallengeCard.jsx`**

Change the import:

```javascript
// before
import { useStateContext } from '../../contexts/ContextProvider';

// after
import { useStateContext } from '../../contexts/ContextProvider';
import { API_BASE_URL } from '../../constants';
```

Change the fetch call:

```javascript
// before
        fetch(`http://localhost:3001/challenges/${challengeId}/accept`, {

// after
        fetch(`${API_BASE_URL}/challenges/${challengeId}/accept`, {
```

- [ ] **Step 9: `FriendsCard.jsx`**

Change the import:

```javascript
// before
import { letterSets } from '../../constants';

// after
import { letterSets, API_BASE_URL } from '../../constants';
```

Change all four fetch calls:

```javascript
// before
        fetch("http://localhost:3001/friend-request", {
// after
        fetch(`${API_BASE_URL}/friend-request`, {

// before
        fetch("http://localhost:3001/friends/accept", {
// after
        fetch(`${API_BASE_URL}/friends/accept`, {

// before
        fetch("http://localhost:3001/friends/decline", {
// after
        fetch(`${API_BASE_URL}/friends/decline`, {

// before
        fetch("http://localhost:3001/challenge", {
// after
        fetch(`${API_BASE_URL}/challenge`, {
```

- [ ] **Step 10: Confirm no hardcoded URLs remain outside the fallback default**

```bash
cd docker-101/anagrams-2/am-client
grep -rn "localhost:3001" src/ | grep -v "src/constants.js"
```

Expected: no output. (`constants.js` itself still contains `localhost:3001` — that's the intentional local-dev fallback.)

- [ ] **Step 11: Lint**

```bash
npm run lint
```

Expected: exits with status 0, no errors (catches unused imports, syntax mistakes from the edits above).

- [ ] **Step 12: Confirm the production build succeeds**

```bash
npm run build
```

Expected: completes with a `dist/` directory created and a `✓ built in ...` line, no errors.

- [ ] **Step 13: Commit**

```bash
git add docker-101/anagrams-2/am-client/src/constants.js \
        docker-101/anagrams-2/am-client/src/App.jsx \
        docker-101/anagrams-2/am-client/src/contexts/ContextProvider.jsx \
        docker-101/anagrams-2/am-client/src/components/Login.jsx \
        docker-101/anagrams-2/am-client/src/components/SignUp.jsx \
        docker-101/anagrams-2/am-client/src/components/Game.jsx \
        docker-101/anagrams-2/am-client/src/components/play-now-card/PlayNowCard.jsx \
        docker-101/anagrams-2/am-client/src/components/challenge-card/ChallengeCard.jsx \
        docker-101/anagrams-2/am-client/src/components/friends-card/FriendsCard.jsx
git commit -m "Replace hardcoded API URLs with configurable API_BASE_URL"
```

---

### Task 3: Terraform — S3 bucket + CloudFront distribution

**Files:**
- Create: `aws-deploy-demo/terraform/s3_cloudfront.tf`
- Modify: `aws-deploy-demo/terraform/outputs.tf`

**Interfaces:**
- Consumes: `aws_lb.main.dns_name` (`aws-deploy-demo/terraform/alb.tf:1`), `var.project_name` (`variables.tf:7-11`) — both already exist
- Produces: outputs `cloudfront_domain_name`, `cloudfront_distribution_id`, `client_bucket_name` — consumed by Task 5 (server verify uses `alb_dns_name`, already existing) and Task 6 (client deploy)

- [ ] **Step 1: Write `s3_cloudfront.tf`**

```hcl
resource "random_id" "client_bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "client" {
  bucket = "${var.project_name}-client-${random_id.client_bucket_suffix.hex}"

  tags = {
    Name = "${var.project_name}-client"
  }
}

resource "aws_s3_bucket_public_access_block" "client" {
  bucket = aws_s3_bucket.client.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "client" {
  name                              = "${var.project_name}-client-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer" {
  name = "Managed-AllViewer"
}

resource "aws_cloudfront_distribution" "client" {
  enabled             = true
  default_root_object = "index.html"
  # North America + Europe only — keeps cost down for a low-traffic demo,
  # vs. the default PriceClass_All (every edge location worldwide).
  price_class = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.client.bucket_regional_domain_name
    origin_id                = "s3-client"
    origin_access_control_id = aws_cloudfront_origin_access_control.client.id
  }

  origin {
    domain_name = aws_lb.main.dns_name
    origin_id   = "alb-api"

    custom_origin_config {
      http_port              = 80
      https_port              = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods          = ["GET", "HEAD"]
    target_origin_id        = "s3-client"
    viewer_protocol_policy  = "redirect-to-https"
    cache_policy_id         = data.aws_cloudfront_cache_policy.caching_optimized.id
  }

  ordered_cache_behavior {
    path_pattern              = "/api/*"
    allowed_methods           = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods             = ["GET", "HEAD"]
    target_origin_id           = "alb-api"
    viewer_protocol_policy     = "https-only"
    cache_policy_id            = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id   = data.aws_cloudfront_origin_request_policy.all_viewer.id
  }

  # SPA client-side routing: react-router-dom paths like /game don't exist
  # as S3 objects, so serve index.html and let the app's router take over.
  # Both codes are handled because S3 can return either for a missing key
  # depending on the request, and OAC-signed requests specifically.
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name = "${var.project_name}-client-cdn"
  }
}

resource "aws_s3_bucket_policy" "client" {
  bucket = aws_s3_bucket.client.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowCloudFrontServicePrincipal"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.client.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.client.arn
        }
      }
    }]
  })
}
```

- [ ] **Step 2: Add outputs**

Append to `aws-deploy-demo/terraform/outputs.tf`:

```hcl

output "cloudfront_domain_name" {
  description = "Public HTTPS URL for the deployed client app"
  value       = "https://${aws_cloudfront_distribution.client.domain_name}"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID, needed for cache invalidations"
  value       = aws_cloudfront_distribution.client.id
}

output "client_bucket_name" {
  description = "S3 bucket holding the built client assets"
  value       = aws_s3_bucket.client.bucket
}
```

- [ ] **Step 3: Format, validate, and plan**

```bash
cd aws-deploy-demo/terraform
terraform fmt
terraform validate
terraform plan
```

Expected: `terraform validate` prints `Success! The configuration is valid.`; `terraform plan` shows `Plan: 6 to add, 1 to change, 0 to destroy.` (the 6 new resources: `random_id.client_bucket_suffix`, `aws_s3_bucket.client`, `aws_s3_bucket_public_access_block.client`, `aws_cloudfront_origin_access_control.client`, `aws_cloudfront_distribution.client`, `aws_s3_bucket_policy.client`; the 1 change is the health check path from Task 1, still unapplied).

- [ ] **Step 4: Commit**

```bash
git add aws-deploy-demo/terraform/s3_cloudfront.tf aws-deploy-demo/terraform/outputs.tf
git commit -m "Add S3 + CloudFront Terraform config for the am-client frontend"
```

---

### Task 4: Apply the Terraform changes (live infrastructure)

**Files:** none (infrastructure-only; no source files change)

**Interfaces:**
- Consumes: Task 1's `variables.tf` edit, Task 3's `s3_cloudfront.tf`/`outputs.tf`
- Produces: live AWS resources; `terraform output cloudfront_domain_name` / `cloudfront_distribution_id` / `client_bucket_name` become resolvable — consumed by Task 6

- [ ] **Step 1: Apply**

```bash
cd aws-deploy-demo/terraform
terraform apply -auto-approve
```

Expected: ends with `Apply complete! Resources: 6 added, 1 changed, 0 destroyed.`

- [ ] **Step 2: Wait for the CloudFront distribution to finish deploying**

```bash
DIST_ID=$(terraform output -raw cloudfront_distribution_id)
aws cloudfront wait distribution-deployed --id "$DIST_ID"
echo "CloudFront domain: $(terraform output -raw cloudfront_domain_name)"
```

Expected: the `wait` command returns (can take 5-15 minutes) with no error, then the domain name prints (a `*.cloudfront.net` URL).

No commit for this task — it's a live infrastructure change with no source files to track; the Terraform code itself was already committed in Task 3.

---

### Task 5: Rebuild and redeploy the API container with the new `/api` routes

**Files:** none (deploy-only; `src/index.js` was already modified and committed in Task 1)

**Interfaces:**
- Consumes: Task 1's server code, the existing `ecr_repository_url` / `alb_dns_name` Terraform outputs
- Produces: the live ECS service now runs the `/api`-prefixed routes — consumed by Task 7's end-to-end smoke test

- [ ] **Step 1: Build, tag, and push the updated image**

```bash
cd docker-101/anagrams-2/server
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  $(terraform -chdir=../../../aws-deploy-demo/terraform output -raw ecr_repository_url | cut -d/ -f1)
docker build --platform linux/amd64 -t anagrams-api .
docker tag anagrams-api:latest \
  $(terraform -chdir=../../../aws-deploy-demo/terraform output -raw ecr_repository_url):latest
docker push \
  $(terraform -chdir=../../../aws-deploy-demo/terraform output -raw ecr_repository_url):latest
```

Expected: `docker push` finishes with a digest line, no errors.

- [ ] **Step 2: Force a new ECS deployment and wait for it to stabilize**

```bash
aws ecs update-service --cluster anagrams-cluster --service anagrams-api \
  --force-new-deployment --region us-east-1
aws ecs wait services-stable --cluster anagrams-cluster --services anagrams-api \
  --region us-east-1
```

Expected: both commands complete with no error (the `wait` can take a couple of minutes while the new task passes its health check).

- [ ] **Step 3: Verify directly against the ALB**

Step 1 leaves the shell in `docker-101/anagrams-2/server` — move back up to the Terraform directory:

```bash
cd ../../../aws-deploy-demo/terraform
curl -s "$(terraform output -raw alb_dns_name)/api/health"
echo
curl -s -o /dev/null -w "old path status: %{http_code}\n" "$(terraform output -raw alb_dns_name)/health"
```

Expected: first line `{"status":"ok"}`; second line `old path status: 404`.

No commit for this task — it only pushes a container image and triggers a deployment, no source files change.

---

### Task 6: Build and deploy the client to S3, verify via CloudFront

**Files:** none (deploy-only; client source was already modified and committed in Task 2)

**Interfaces:**
- Consumes: Task 2's client code, Task 4's `client_bucket_name` / `cloudfront_distribution_id` / `cloudfront_domain_name` outputs
- Produces: the CloudFront distribution now serves the built app — consumed by Task 7's end-to-end smoke test

- [ ] **Step 1: Build the client for production**

```bash
cd docker-101/anagrams-2/am-client
VITE_API_URL=/api npm run build
```

Expected: `dist/` is (re)created with no build errors.

- [ ] **Step 2: Sync to S3 and invalidate the CloudFront cache**

```bash
aws s3 sync dist/ s3://$(terraform -chdir=../../../aws-deploy-demo/terraform output -raw client_bucket_name) --delete
aws cloudfront create-invalidation \
  --distribution-id $(terraform -chdir=../../../aws-deploy-demo/terraform output -raw cloudfront_distribution_id) \
  --paths "/*"
```

Expected: `aws s3 sync` lists the uploaded files (`index.html`, hashed JS/CSS under `assets/`); `create-invalidation` prints an invalidation ID and `"Status": "InProgress"`.

- [ ] **Step 3: Verify the app loads and the SPA fallback works**

```bash
CF_URL=$(terraform -chdir=../../../aws-deploy-demo/terraform output -raw cloudfront_domain_name)
curl -s "$CF_URL" | grep -o 'id="root"'
curl -s "$CF_URL/game" | grep -o 'id="root"'
```

Expected: both commands print `id="root"` — the first confirms the built `index.html` is served at the root, the second confirms a non-existent client-side route (`/game`) still gets `index.html` via the 404→200 rewrite instead of an S3 error page.

No commit for this task — `dist/` is gitignored and no source files change.

---

### Task 7: End-to-end smoke test through CloudFront, and update docs

**Files:**
- Modify: `aws-deploy-demo/README.md`
- Modify: `aws-deploy-demo/terraform/README.md`

**Interfaces:**
- Consumes: Task 5 (API live under `/api/*`) and Task 6 (client live on CloudFront)
- Produces: nothing consumed by later tasks — this is the final verification task

- [ ] **Step 1: Exercise the `/api/*` proxy through CloudFront**

```bash
CF_URL=$(terraform -chdir=aws-deploy-demo/terraform output -raw cloudfront_domain_name)

SIGNUP_RESP=$(curl -s -X POST "$CF_URL/api/signup" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"smoketest_$(date +%s)\",\"password\":\"testpass123\"}")
echo "$SIGNUP_RESP"
TOKEN=$(echo "$SIGNUP_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -s "$CF_URL/api/me" -H "Authorization: Bearer $TOKEN"
echo
```

Expected: the signup response is JSON containing a `token` field; the `/api/me` response is JSON containing `username`, `high_score`, `games_played`, `wins`, `losses`, `friends`, `requests`, `challenges` — not an HTML error page, CORS error, or connection failure. This confirms CloudFront's `/api/*` behavior correctly forwards to the ALB and back with auth headers intact.

- [ ] **Step 2: Confirm the SSE endpoint's headers pass through CloudFront**

```bash
curl -s -D - -m 5 -o /dev/null "$CF_URL/api/events?token=$TOKEN" | grep -i "content-type"
```

Expected: prints a line containing `content-type: text/event-stream` (the `-m 5` timeout is expected to end the connection after 5 seconds since curl doesn't keep reading the stream — a non-zero curl exit code from the timeout is fine here, the header line is what matters).

- [ ] **Step 3: Update `aws-deploy-demo/README.md`**

Change:

```markdown
## Tasks (mirrors Notion)

- [ ] Orient with roadmap.sh/aws (IAM, EC2 vs ECS vs Lambda, S3)
- [x] Deploy the docker-101 container to AWS (ECS Fargate) — Terraform scaffold done, `terraform apply` not yet run
- [ ] Stretch: wire up basic CI (GitHub Actions build/push on commit)

## Status

ECS Fargate chosen over Lambda (persistent MySQL connection + real-time chat
fit a long-running server better than per-invocation functions).

Terraform scaffold for the `docker-101/anagrams-2` API lives in `terraform/`:
VPC (public subnets, no NAT Gateway — security-group-based isolation
instead), ECR, Secrets Manager, RDS MySQL, IAM roles, ECS cluster/task/
service, ALB. Built via subagent-driven-development from
`docs/superpowers/plans/2026-07-09-anagrams-ecs-deploy.md`, each piece
verified with a real `terraform plan` against the live AWS account.
`terraform fmt`/`validate`/`plan` all clean (29 resources to add, 0 errors).
See `terraform/README.md` for setup/apply/verify/teardown steps.

**Not yet done:** `terraform apply` (real AWS spend, deliberately left as a
manual step — see cost notes in `terraform/README.md`), S3 + CloudFront
static deploy for the `am-client` frontend, and the CI stretch goal.

## Notes

(Log AWS gotchas, IAM policy snags, deploy configs here as you go.)
```

to:

```markdown
## Tasks (mirrors Notion)

- [ ] Orient with roadmap.sh/aws (IAM, EC2 vs ECS vs Lambda, S3)
- [x] Deploy the docker-101 container to AWS (ECS Fargate) — Terraform applied, live and verified
- [x] Deploy the am-client frontend (S3 + CloudFront)
- [ ] Stretch: wire up basic CI (GitHub Actions build/push on commit)

## Status

ECS Fargate chosen over Lambda (persistent MySQL connection + real-time chat
fit a long-running server better than per-invocation functions).

Terraform in `terraform/` provisions the full stack: VPC (public subnets, no
NAT Gateway — security-group-based isolation instead), ECR, Secrets Manager,
RDS MySQL, IAM roles, ECS cluster/task/service, ALB, and an S3 bucket +
CloudFront distribution serving `am-client`. Built via
subagent-driven-development from
`docs/superpowers/plans/2026-07-09-anagrams-ecs-deploy.md` (backend) and
`docs/superpowers/plans/2026-07-09-s3-cloudfront-frontend.md` (frontend).
`terraform apply` has been run for both — all resources are live. See
`terraform/README.md` for setup/apply/verify/teardown/redeploy steps.

The API's routes are mounted under `/api` (e.g. `/api/login`, `/api/health`)
so CloudFront can route `/api/*` to the ALB and everything else to S3 from a
single HTTPS hostname, with no custom domain required.

**Not yet done:** the CI stretch goal (GitHub Actions build/push on commit).

## Notes

(Log AWS gotchas, IAM policy snags, deploy configs here as you go.)
```

- [ ] **Step 4: Update `aws-deploy-demo/terraform/README.md` — fix the health check path in Verify**

Change:

```markdown
## Verify

```bash
cd aws-deploy-demo/terraform
curl $(terraform output -raw alb_dns_name)/health
```
Expected: `{"status":"ok"}`
```

to:

```markdown
## Verify

```bash
cd aws-deploy-demo/terraform
curl $(terraform output -raw alb_dns_name)/api/health
```
Expected: `{"status":"ok"}`
```

- [ ] **Step 5: Update `aws-deploy-demo/terraform/README.md` — fix the redeploy instructions and add a client deploy section**

Change:

```markdown
## Redeploy after a code change

```bash
cd docker-101/anagrams-2/server
docker build -t anagrams-api .
docker tag anagrams-api:latest <ecr_repository_url>:latest
docker push <ecr_repository_url>:latest
aws ecs update-service --cluster anagrams-cluster --service anagrams-api --force-new-deployment --region us-east-1
```

## Cost notes
```

to:

```markdown
## Redeploy after a code change

```bash
cd docker-101/anagrams-2/server
docker build --platform linux/amd64 -t anagrams-api .
docker tag anagrams-api:latest <ecr_repository_url>:latest
docker push <ecr_repository_url>:latest
aws ecs update-service --cluster anagrams-cluster --service anagrams-api --force-new-deployment --region us-east-1
```

Note: `--platform linux/amd64` matters when building on Apple Silicon —
Fargate defaults to X86_64 and won't run an arm64 image.

## Deploy the client (S3 + CloudFront)

```bash
cd docker-101/anagrams-2/am-client
VITE_API_URL=/api npm run build
aws s3 sync dist/ s3://$(terraform -chdir=../../../aws-deploy-demo/terraform output -raw client_bucket_name) --delete
aws cloudfront create-invalidation \
  --distribution-id $(terraform -chdir=../../../aws-deploy-demo/terraform output -raw cloudfront_distribution_id) \
  --paths "/*"
```

The app is served from the CloudFront domain, not the ALB — run
`terraform output cloudfront_domain_name` to get the URL. The invalidation
step is required on every redeploy; without it, CloudFront keeps serving
cached (stale) assets to existing visitors.

## Cost notes
```

- [ ] **Step 6: Update `aws-deploy-demo/terraform/README.md` — add the S3/CloudFront cost line**

Change:

```markdown
- No NAT Gateway is provisioned (public-subnet + security-group pattern),
  which avoids its ~$32/mo cost.
```

to:

```markdown
- No NAT Gateway is provisioned (public-subnet + security-group pattern),
  which avoids its ~$32/mo cost.
- S3 + CloudFront (client hosting): well under $1-2/mo at demo-level
  traffic. `price_class = "PriceClass_100"` limits CloudFront to North
  America/Europe edge locations to keep cost down further.
```

- [ ] **Step 7: Commit**

```bash
git add aws-deploy-demo/README.md aws-deploy-demo/terraform/README.md
git commit -m "Document the live S3/CloudFront client deploy and fix stale /health references"
```

---

### Task 8: Fix SSE timeout through CloudFront (added post-Task-7)

Task 7's smoke test found that `/api/events` (Server-Sent Events, used for
real-time friend-request/challenge/score notifications) never delivers body
data through CloudFront: the HTTP/2 stream is killed with `INTERNAL_ERROR`
at almost exactly 30 seconds. Root cause, confirmed with a 40s-timeout curl
probe against the live distribution: CloudFront's default Origin Response
Timeout (30s) races the server's own heartbeat interval (`setInterval(...,
30000)` in `docker-101/anagrams-2/server/src/index.js`) — CloudFront kills
the connection for inactivity at the exact moment the origin would have sent
its first keepalive byte. Direct-to-ALB access is unaffected (confirmed
working in Task 7).

**Files:**
- Modify: `aws-deploy-demo/terraform/s3_cloudfront.tf` (the `alb-api` origin's `custom_origin_config` block)

**Interfaces:**
- Consumes: the existing `origin { domain_name = aws_lb.main.dns_name ... custom_origin_config { ... } }` block added in Task 3
- Produces: no new outputs; the live CloudFront distribution's origin timeout changes on apply

- [ ] **Step 1: Add `origin_read_timeout` to the ALB origin's `custom_origin_config`**

In `aws-deploy-demo/terraform/s3_cloudfront.tf`, change:

```hcl
    custom_origin_config {
      http_port              = 80
      https_port              = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
```

to:

```hcl
    custom_origin_config {
      http_port              = 80
      https_port              = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
      # Default (30s) races the server's own 30s SSE heartbeat interval
      # (server/src/index.js's `setInterval(..., 30000)`), so CloudFront
      # kills the /api/events connection right as the first heartbeat
      # would arrive. 60s is the max allowed without an AWS support
      # quota increase — gives the existing heartbeat cadence 2x margin.
      origin_read_timeout = 60
    }
```

- [ ] **Step 2: Format, validate, and plan (read-only against real state)**

```bash
cd aws-deploy-demo/terraform
terraform fmt
terraform validate
terraform plan -state="/Users/nzhu/Documents/Claude/Projects/link-ventures-prep/aws-deploy-demo/terraform/terraform.tfstate"
```

Expected: `terraform validate` → `Success! The configuration is valid.`; plan shows exactly `Plan: 0 to add, 1 to change, 0 to destroy` (only `aws_cloudfront_distribution.client`'s origin config changes in-place — no resource replacement).

- [ ] **Step 3: Commit**

```bash
git add aws-deploy-demo/terraform/s3_cloudfront.tf
git commit -m "Fix SSE connections dying through CloudFront by raising origin_read_timeout"
```

- [ ] **Step 4: Apply from the main checkout (live infrastructure)**

Same pattern as Task 4 — this runs in `/Users/nzhu/Documents/Claude/Projects/link-ventures-prep/aws-deploy-demo/terraform` (real state), not the worktree.

```bash
cd /Users/nzhu/Documents/Claude/Projects/link-ventures-prep/aws-deploy-demo/terraform
terraform apply -auto-approve
```

Expected: `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.` CloudFront distribution config updates typically propagate in a few minutes (faster than the initial ~3min creation in Task 4, but still not instant) — wait for `Deployed` status:

```bash
DIST_ID=$(terraform output -raw cloudfront_distribution_id)
aws cloudfront wait distribution-deployed --id "$DIST_ID"
```

- [ ] **Step 5: Re-verify SSE survives past 30 seconds**

```bash
CF_URL=$(terraform output -raw cloudfront_domain_name)
# Sign up a fresh throwaway user and grab a token, same pattern as Task 7 Step 1
SIGNUP_RESP=$(curl -s -X POST "$CF_URL/api/signup" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"sse_fix_verify_$(date +%s)\",\"password\":\"testpass123\"}")
TOKEN=$(echo "$SIGNUP_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -sv -m 40 -o /tmp/sse_verify_body.txt -D /tmp/sse_verify_headers.txt \
  "$CF_URL/api/events?token=$TOKEN"
cat /tmp/sse_verify_headers.txt
echo "--- body (expect at least one heartbeat line, ':heartbeat') ---"
cat /tmp/sse_verify_body.txt
```

Expected: the connection survives past the 30-second mark this time (no `INTERNAL_ERROR` stream reset at ~30s), and the body file contains at least one `:heartbeat` line (the server sends one every 30s, so a 40s-timeout curl should catch it). If it still dies at 30s or the body is still empty, the fix didn't work — report BLOCKED with the actual output rather than declaring success.

---

### Task 9: Fix CloudFront swallowing real API 403/404 responses (found in final review)

The final whole-branch review (after Task 8) found a real cross-task bug: Task 3's
`custom_error_response` blocks (added for SPA client-side routing — so refreshing on
`/game` doesn't 404) apply to the **whole CloudFront distribution**, not just the S3
behavior. That means a genuine `403` from the API (`authenticateToken` on an
invalid/expired JWT, `docker-101/anagrams-2/server/src/index.js:94`, hit on every
protected route) or `404` (e.g. "user not found") gets silently rewritten to
`200 + index.html` too. Concretely, `ChallengeCard.jsx:34`'s
`if (res.status === 403) { …force logout… }` branch can never fire in production, and
every other component's `if (!res.ok)` check is bypassed the same way. Not a security
hole (the API still rejects bad tokens server-side) but a real UX correctness bug.

**Fix:** replace the distribution-wide `custom_error_response` rewrite with a
CloudFront Function (viewer-request) attached **only** to the S3 default behavior —
it rewrites extensionless paths to `/index.html` before S3 ever responds, so
`/api/*` traffic (a separate behavior, no function attached there) is never touched.
This is the standard modern pattern for SPA routing on CloudFront.

**Files:**
- Modify: `aws-deploy-demo/terraform/s3_cloudfront.tf` (remove both `custom_error_response` blocks, add a new `aws_cloudfront_function` resource, attach it to `default_cache_behavior`)

**Interfaces:**
- Consumes: the existing `aws_cloudfront_distribution.client` resource from Task 3/8
- Produces: no new outputs; distribution config changes on apply

- [ ] **Step 1: Remove the two `custom_error_response` blocks**

In `aws-deploy-demo/terraform/s3_cloudfront.tf`, delete both blocks entirely:

```hcl
  # SPA client-side routing: react-router-dom paths like /game don't exist
  # as S3 objects, so serve index.html and let the app's router take over.
  # Both codes are handled because S3 can return either for a missing key
  # depending on the request, and OAC-signed requests specifically.
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }
```

- [ ] **Step 2: Add the CloudFront Function resource**

Add this resource anywhere in `s3_cloudfront.tf` (top-level, alongside the other resources):

```hcl
resource "aws_cloudfront_function" "spa_routing" {
  name    = "${var.project_name}-spa-routing"
  runtime = "cloudfront-js-1.0"
  comment = "Rewrite extensionless paths to /index.html for client-side routing (react-router-dom). Only associated with the S3 default behavior, so /api/* traffic is never touched — this replaces the old distribution-wide custom_error_response, which was incorrectly rewriting real API 403/404 responses too."
  publish = true
  code    = <<-EOT
    function handler(event) {
        var request = event.request;
        var uri = request.uri;

        if (!uri.includes('.')) {
            request.uri = '/index.html';
        }

        return request;
    }
  EOT
}
```

- [ ] **Step 3: Attach the function to the S3 default behavior only**

In `aws-deploy-demo/terraform/s3_cloudfront.tf`, change:

```hcl
  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods          = ["GET", "HEAD"]
    target_origin_id        = "s3-client"
    viewer_protocol_policy  = "redirect-to-https"
    # Managed-CachingOptimized
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }
```

to:

```hcl
  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods          = ["GET", "HEAD"]
    target_origin_id        = "s3-client"
    viewer_protocol_policy  = "redirect-to-https"
    # Managed-CachingOptimized
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_routing.arn
    }
  }
```

Do **not** add a `function_association` to the `/api/*` `ordered_cache_behavior` block — leaving it absent there is exactly what keeps API traffic untouched.

- [ ] **Step 4: Format, validate, and plan (read-only against real state)**

```bash
cd aws-deploy-demo/terraform
terraform fmt
terraform validate
terraform plan -state="/Users/nzhu/Documents/Claude/Projects/link-ventures-prep/aws-deploy-demo/terraform/terraform.tfstate"
```

Expected: `terraform validate` → `Success! The configuration is valid.`; plan shows `Plan: 1 to add, 1 to change, 0 to destroy` (the new `aws_cloudfront_function.spa_routing`, plus `aws_cloudfront_distribution.client` updating in-place — removed error responses + new function association — no resource replacement).

- [ ] **Step 5: Commit**

```bash
git add aws-deploy-demo/terraform/s3_cloudfront.tf
git commit -m "Replace distribution-wide SPA error rewrite with a CloudFront Function scoped to S3 only"
```

- [ ] **Step 6: Apply from the main checkout (live infrastructure)**

Same pattern as Task 4/8 — run from `/Users/nzhu/Documents/Claude/Projects/link-ventures-prep/aws-deploy-demo/terraform` (real state), not the worktree. Sync the updated `s3_cloudfront.tf` there first, same as Task 8's Step 4.

```bash
cd /Users/nzhu/Documents/Claude/Projects/link-ventures-prep/aws-deploy-demo/terraform
terraform apply -auto-approve
```

Expected: `Apply complete! Resources: 1 added, 1 changed, 0 destroyed.` Wait for the distribution to reach `Deployed`:

```bash
DIST_ID=$(terraform output -raw cloudfront_distribution_id)
aws cloudfront wait distribution-deployed --id "$DIST_ID"
```

- [ ] **Step 7: Re-verify both the SPA fallback still works AND real API errors now pass through**

```bash
CF_URL=$(terraform output -raw cloudfront_domain_name)

echo "--- SPA fallback still works (expect id=\"root\") ---"
curl -s "$CF_URL/game" | grep -o 'id="root"'

echo "--- real 403 now passes through for an invalid token (expect 403, not 200) ---"
curl -s -o /dev/null -w "%{http_code}\n" "$CF_URL/api/me" -H "Authorization: Bearer not-a-real-token"

echo "--- normal requests still unaffected (expect 200) ---"
curl -s -o /dev/null -w "%{http_code}\n" "$CF_URL/"
```

Expected: `id="root"` printed (SPA fallback intact), `403` for the bad-token request (the actual bug fix — this used to silently return `200`), `200` for the root path. If the bad-token request still returns `200`, the fix didn't work — report BLOCKED with the actual output.

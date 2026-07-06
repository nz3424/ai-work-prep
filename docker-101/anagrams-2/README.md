# anagrams-2 — Docker Compose worked example

A pre-existing full-stack app (React/Vite frontend, Express backend, MySQL
database) containerized as the Day 2 hands-on exercise. See `../README.md`
for the itinerary context and lessons learned.

## Setup

```
cp .env.example .env
cp server/.env.example server/.env
# edit both with real values (a DB password, a JWT secret) before running
```

## Run it

```
docker compose up -d --build
```

- Frontend: http://localhost:5173
- API: http://localhost:3001
- MySQL: exposed on host port 3307 (mapped to avoid clashing with a local MySQL install)

## Stack

| Service | What it is | Port |
|---|---|---|
| `client` | Vite dev server serving the React frontend | 5173 |
| `api` | Express backend, nodemon | 3001 |
| `db` | MySQL 8.4, schema auto-applied from `server/schema.sql` on first boot | 3307 → 3306 |

Dev-mode only: bind-mounted source for hot reload, anonymous `node_modules`
volumes protecting native modules (`bcrypt`) from the bind mount. Not a
production configuration — see `../README.md` notes for the multi-stage
prod-build sketch.

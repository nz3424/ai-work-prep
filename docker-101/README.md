# docker-101

**Maps to:** Itinerary Day 2 (Sat Jul 4) — see `../GOALS.md` for full context.

## Goal

Go from "knows what Docker is" to fluent: images vs. containers, Dockerfiles,
Compose for multi-service local stacks, and pushing/pulling from a registry.

## Tasks (mirrors Notion)

- [ ] Work through a Docker crash course actively (roadmap.sh/docker), typing every command
- [x] Containerize a real script/app of mine (write a Dockerfile, build, run)
- [x] Stand up a multi-service local stack with Docker Compose (frontend + API + database — 3 services, not just 2)
- [ ] Push an image to a registry (Docker Hub or similar) — walked through the commands, haven't actually pushed one yet

## Status

Containerized `anagrams-2` (see `anagrams-2/`) as a 3-service dev-mode Compose
stack: Vite/React frontend, Express/MySQL backend, MySQL database. Verified
end-to-end via a real signup/login flow through the full stack, not just
`curl`. Full step-by-step writeup (with a CLI cheat sheet, a dev-vs-prod
comparison, and broader use cases) is in Notion: [Docker Compose:
Containerizing a Multi-Service Dev
App](https://app.notion.com/p/395490b4d1bb81649662ebe5a84dfb06).

Remaining: registry push, and the crash-course pass.

## Notes

Gotchas hit while building this out (see `anagrams-2/README.md` for the stack
itself):

- `COPY package.json package-lock.json ./` — with multiple source files, the
  destination needs a trailing slash or Docker mis-copies (treats the last
  arg as a specific destination file, not a directory).
- `CMD` is inert at build time — `docker build` succeeding proves nothing
  about whether `CMD` actually works. Always `docker run` a fresh image once.
- Native modules (e.g. `bcrypt`) don't survive a bind mount over
  `node_modules` — add a bare `/app/node_modules` volume entry (anonymous
  volume) to protect the image's own Linux-built deps from the host's.
- That anonymous volume can get stuck with stale content after a dependency
  change + rebuild — force a refresh with `up -d --build -V --force-recreate
  <service>`.
- Vite's dev server binds to `localhost` inside a container by default —
  needs `--host 0.0.0.0` to be reachable from outside.
- `env_file:` and `environment:` are both real (different) mechanisms;
  `environment:` always wins on a key collision. A root-level `.env` is a
  third, separate mechanism — it only fills `${VAR}` tokens written literally
  in `docker-compose.yml`, nothing more.
- `depends_on` controls startup order, not network reachability — any two
  services on the same custom network can already reach each other by name.

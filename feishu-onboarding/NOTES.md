# Feishu Onboarding — Version History

## v1 (2026-06-18)

**Initial draft.** Captured while planning to spin up a second Hermes instance for bot-to-bot testing.

### Sources

- **Authoritative**: local copy of `~/.hermes/hermes-agent/website/docs/user-guide/messaging/feishu.md` (590 lines, complete)
- **Feishu open platform**: `https://open.feishu.cn/document/server-docs/event-subscription-guide/overview.md` (12KB markdown pulled, June 2026 snapshot)
- **Hermes env var reference**: `~/.hermes/hermes-agent/website/docs/reference/environment-variables.md` lines 352-360
- **Real incident data**: 6/17/2026 `bot_removed` event, emily whitelist fix, oc_0d47d1193 group discovery — pulled from session_search

### Verified live before commit

- `systemctl --user is-active hermes-gateway` → active (PID 1079363, running since 13:14)
- `FEISHU_ALLOWED_USERS` = `ou_d1174c3e160c7d96827b5a9c3d3cb495,ou_03aa9dd0a6e65ac2c5a6f58b514a6586`
- `FEISHU_GROUP_POLICY=open`, `FEISHU_REQUIRE_MENTION=false`
- `FEISHU_HOME_CHANNEL=oc_58347a19f387b8948b273f0f8dbf24ef`
- `~/.hermes/feishu_seen_message_ids.json` present (11KB, dedup cache working)
- WebSocket mode active (`FEISHU_CONNECTION_MODE=websocket`)

### Sections

1. Mental model diagram
2. Pre-flight (box-side install)
3. Feishu developer console (5 steps)
4. Hermes configuration (.env + config.yaml split)
5. Connection mode decision (WS vs webhook)
6. Allowlist & authorization (3 layers)
7. Bot-to-bot messaging setup
8. **The `bot_removed` recovery flow** ← unique to our prod, not in official docs
9. Verification smoke test
10. Common pitfalls table
11. Architecture reference (where to look in code)
12. Quick reference card (cheat sheet)
- Appendix A: Event subscription reference
- Appendix B: Source URLs

### What's missing / next iteration

- **Bot-to-bot loop detection** — only sketched, not validated against actual second bot (waiting for new Hermes instance)
- **Webhook mode behind nginx/Caddy** — documented but not tested in our setup
- **Doc comment reply flow** — covered at a high level, full walkthrough deferred
- **Multi-tenant app** — we run internal (自建); ISV app flow not tested

### Maintainer notes

- When Feishu open platform version bumps, re-pull `overview.md` and check for scope/event deprecations
- When `~/.hermes/hermes-agent` is upgraded, diff `website/docs/user-guide/messaging/feishu.md` — Hermes adds new env vars or features
- Keep §8 (`bot_removed` recovery) as the first thing to add to any incident postmortem — this is real, it cost ~2 hours the first time, and the fix is a one-liner that nobody will remember next time
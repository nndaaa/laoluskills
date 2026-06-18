---
name: feishu-onboarding
description: Build a new Hermes Agent instance on a fresh Linux box and connect it to a Feishu (飞书) bot. Covers Feishu developer console setup (app, permissions, events, publish), Hermes configuration (.env + config.yaml), WebSocket vs webhook mode, allowlist policy, bot-to-bot message handling, the known `bot_removed` recovery flow, and 6/17/2026 production incident lessons. Trigger when: user mentions 飞书 / Feishu / Lark, building a new bot, configuring a new Hermes instance, onboarding chat platform, or hits inbound/outbound/permission/auth errors with the Feishu gateway.
---

# Feishu × Hermes Agent — Onboarding Playbook

A complete, **production-tested** guide to setting up a fresh Hermes Agent instance connected to a Feishu (飞书) bot. Distilled from the official Hermes docs (`~/.hermes/hermes-agent/website/docs/user-guide/messaging/feishu.md`), Feishu open platform docs (`open.feishu.cn`), and the live deployment on `dark@home` since 2026-06-17.

The intended reader is **dark's future self** (or another `dark`) spinning up a new Hermes box and wanting zero surprises.

---

## 0. Mental Model — What You're Building

```
┌─────────────────────┐         WebSocket (outbound)        ┌──────────────────┐
│  Feishu Cloud       │  ─────────────────────────────────▶ │  Hermes Gateway  │
│  (events source)    │                                     │  on your box     │
│                     │  ◀───────────────────────────────── │  (this skill)    │
│                     │         REST API (outbound send)    │                  │
└─────────────────────┘                                     └──────────────────┘
        ▲                                                            │
        │                                                            ▼
        │                                                  ┌──────────────────┐
        │                                                  │  Agent Loop      │
        │                                                  │  (LLM + tools)   │
        │                                                  └──────────────────┘
   app_id = cli_xxx
   app_secret = secret_xxx
```

Two channels:
- **Inbound**: Feishu → your box. WebSocket (preferred, no public URL) or Webhook (HTTP POST).
- **Outbound**: your box → Feishu. Always REST `POST /im/v1/messages`. Requires `tenant_access_token`.

The gateway auto-refreshes `tenant_access_token` (2h TTL) by signing with `app_id` + `app_secret`.

---

## 1. Pre-flight (Box-side)

### 1.1 Install Hermes

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.bashrc
hermes --version   # smoke test
```

### 1.2 Systemd user service (auto-start on boot)

Hermes installs a user-mode systemd unit. Verify:

```bash
systemctl --user status hermes-gateway --no-pager
```

If you want **boot persistence** (reconnect after ToDesk/LAN drop), enable lingering:

```bash
sudo loginctl enable-linger dark
```

### 1.3 Required Python deps for Feishu

```bash
pip install lark-oapi    # official Lark SDK
pip install websockets   # WebSocket mode (default)
# pip install aiohttp   # only if you need webhook mode
```

---

## 2. Feishu Developer Console (5 steps, ~10 min)

Open **https://open.feishu.cn/** → "开发者后台" → "创建企业自建应用".

### 2.1 Create the app

- **应用名称**: anything (e.g. `老陆助手-2`)
- **应用描述**: one-liner
- **应用图标**: optional, can skip
- After creation, land on the **基础信息** page.

### 2.2 Copy credentials

From **凭证与基础信息**:

| Field | Example | Goes to env var |
|---|---|---|
| App ID | `cli_aabbccdd11223344` | `FEISHU_APP_ID` |
| App Secret | `xxx…` (32-char hex) | `FEISHU_APP_SECRET` |

**Treat the App Secret like a password.** Don't commit it, don't echo in chat. Hermes auto-quotes secrets via `approvals.mode: smart` — but you should still keep it in `~/.hermes/.env` (chmod 600), not in `config.yaml`.

### 2.3 Enable Bot capability

Sidebar → **应用功能** → **机器人** → toggle ON. Configure:

- **消息卡片请求网址**: leave **empty** if you use WebSocket mode (recommended). Hermes SDK handles card callbacks.
- If you later switch to webhook mode, this URL must be `https://<your-public-host>:8765/feishu/webhook` (see §4).

### 2.4 Permissions

Sidebar → **权限管理** → **API 权限** → click "添加权限" → bulk-paste these scopes:

**Required (chat basics):**

| Scope | Why |
|---|---|
| `im:message` | Receive messages |
| `im:message:send_as_bot` | Send messages as the bot |
| `im:message.group_at_msg:readonly` | Read @-mention events |
| `im:resource` | Download images/files/audio |
| `im:chat` | Read chat metadata |
| `im:chat:readonly` | List chat membership |

**Recommended (for full Hermes features):**

| Scope | Why |
|---|---|
| `im:message.reactions:readonly` | Reaction events (Typing indicator) |
| `admin:app.info:readonly` | Auto-detect bot identity (for @mention gating) |
| `contact:user.id:readonly` | Resolve user IDs against allowlist |
| `application:bot.basic_info:read` | Show peer bot names instead of `ou_xxx` |

**Optional (for Feishu Doc comment intelligent reply):**

| Scope | Why |
|---|---|
| `docs:doc:readonly` | Read doc content for comment threads |
| `drive:drive:readonly` | Read drive metadata |

### 2.5 Events

Sidebar → **事件订阅** → choose connection mode:

**Recommended: 长连接 (WebSocket)**

- Toggle on **使用长连接接收事件**
- **Add events**:
  - `im.message.receive_v1` ← **required** (every inbound message)
  - `card.action.trigger` ← **required** if you want approval buttons (command approval flow)
  - `drive.notice.comment_add_v1` ← only if doing doc-comment replies
  - `vc.bot.meeting_invited_v1` ← only if doing meeting bot
- No URL needed — Hermes SDK opens outbound WS.

**Alternative: Webhook (only if you have a public HTTPS endpoint)**

- Choose **将事件推送至开发者服务器**
- Set **请求网址** = `https://your.domain.com:8765/feishu/webhook`
- Set **加密策略** → generate **Encrypt Key** and **Verification Token** (paste both into `.env`)
- Click "保存" → Feishu will POST a URL verification challenge. Your running gateway handles it automatically (responds with the `challenge` echo).

### 2.6 Publish the app

Sidebar → **版本管理与发布** → "创建版本" → fill in version + description → submit.

**For internal (自建) apps:** auto-approved in ~30 sec, no admin needed.

**For enterprise (ISV) apps:** needs enterprise admin approval. They get a Feishu notification. **Don't skip this step — events won't fire until version is published.**

After publish, add the bot to a chat:

- **1-on-1**: search bot by name → start chat
- **Group**: group settings → "群机器人" → add bot

---

## 3. Hermes Configuration

### 3.1 `.env` (~/.hermes/.env)

```bash
# Feishu credentials
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_DOMAIN=feishu               # or `lark` for international

# Connection mode
FEISHU_CONNECTION_MODE=websocket  # recommended; `webhook` if you have a public URL

# Allowlist — IMPORTANT (see §5)
FEISHU_ALLOWED_USERS=ou_xxx,ou_yyy
FEISHU_ALLOW_ALL_USERS=false      # set true only in dev

# Group behavior
FEISHU_GROUP_POLICY=open          # open | allowlist | disabled
FEISHU_REQUIRE_MENTION=false      # true = bot only replies when @mentioned

# Bot-to-bot messaging (peer bots talking to your bot)
FEISHU_ALLOW_BOTS=mentions        # none | mentions | all

# Home channel (where cron results go)
FEISHU_HOME_CHANNEL=oc_xxx

# Webhook-only (leave empty for WS mode)
FEISHU_WEBHOOK_HOST=0.0.0.0
FEISHU_WEBHOOK_PORT=8765
FEISHU_WEBHOOK_PATH=/feishu/webhook
FEISHU_ENCRYPT_KEY=
FEISHU_VERIFICATION_TOKEN=
```

Then `chmod 600 ~/.hermes/.env`.

### 3.2 `config.yaml` (per-group overrides)

Most things go in `.env`. Use `~/.hermes/config.yaml` for things that can't fit on one line:

```yaml
platforms:
  feishu:
    extra:
      ws_reconnect_interval: 120   # seconds between WS reconnect attempts
      ws_ping_interval: 30         # WS keepalive ping
      default_group_policy: "open" # fallback for groups not in group_rules
      admins:
        - "ou_d1174c3e160c7d96827b5a9c3d3cb495"   # dark's open_id
      group_rules:
        "oc_0d47d1193f81d17c5050b99c0e15dac7":    # "手工与电商"
          policy: "open"
          require_mention: false
        "oc_58347a19f387b8948b273f0f8dbf24ef":    # dark's DM
          policy: "open"
```

**Why split?** `.env` is for secrets + behavior toggles; `config.yaml` is for structured data (lists, nested rules). Don't put `FEISHU_ALLOWED_USERS` in `config.yaml` if you can avoid it (harder to read across machine clones).

---

## 4. Connection Mode Decision

| | WebSocket | Webhook |
|---|---|---|
| **Public URL needed?** | ❌ No | ✅ Yes (HTTPS, reachable from Feishu) |
| **NAT/firewall?** | Outbound only | Inbound must be open |
| **Setup friction** | Low — just install `websockets` | High — need reverse proxy + cert + URL verification |
| **Latency** | ~50-200ms | ~100-500ms |
| **Multi-region Feishu** | Connect from any region | Need region-pinned webhook |
| **Recommendation** | **Use this unless you have a reason** | Only if you already have a public endpoint |

**WebSocket internal flow** (from `gateway/platforms/feishu.py`):
1. SDK opens outbound WS to `wss://open.feishu.cn/anycross/.../connect`
2. Feishu sends events → SDK parses → your gateway dispatches to agent loop
3. Auto-reconnect every `ws_reconnect_interval` (default 120s) on disconnect
4. SDK handles heartbeats (default 30s) — don't disable

**To switch modes** mid-flight: change `FEISHU_CONNECTION_MODE`, restart gateway (`systemctl --user restart hermes-gateway`). Don't run both modes simultaneously.

---

## 5. Allowlist & Authorization (the *easy-to-miss* foot-gun)

### 5.1 The 3 layers of access control

```
Inbound message
   │
   ├─ Layer 1: FEISHU_REQUIRE_MENTION
   │  └─ Group: bot must be @mentioned. DM: always allowed.
   │
   ├─ Layer 2: FEISHU_GROUP_POLICY  (groups only)
   │  ├─ "open"       → any user in the group
   │  ├─ "allowlist"  → user must be in FEISHU_ALLOWED_USERS
   │  └─ "disabled"   → all group messages dropped
   │
   └─ Layer 3: FEISHU_ALLOWED_USERS  (per-user)
      └─ Comma-separated open_id list. Bypassed for DMs by default.
```

**Default behavior is restrictive** — empty allowlist + `allowlist` policy = **nobody can talk to the bot in groups**. This is the #1 cause of "bot is online but never replies".

### 5.2 How to find a user's open_id

Three ways:

**a. Use Hermes' built-in (after they message once and get blocked)**:
```bash
tail -100 ~/.hermes/logs/gateway.log | grep -i "unauthorized\|unknown user\|sender"
# logs the open_id on rejection
```

**b. Group member list API** (curl):
```bash
TOKEN=$(curl -s -X POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal \
  -H "Content-Type: application/json" \
  -d "{\"app_id\":\"$FEISHU_APP_ID\",\"app_secret\":\"$FEISHU_APP_SECRET\"}" \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['tenant_access_token'])")

curl -s "https://open.feishu.cn/open-apis/im/v1/chats/$CHAT_ID/members?member_id_type=open_id" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**c. Have the user DM the bot** — once they send any message, even if rejected, their `open_id` shows up in logs.

### 5.3 Recommended policy for `dark@home` setup

| Group type | `policy` | `require_mention` | Why |
|---|---|---|---|
| Family group (you + wife) | `open` | `false` | Allow free chat without @ |
| Work group | `allowlist` | `true` | Bot only answers when explicitly @ |
| Public group | `blacklist` or `disabled` | — | Don't enable bot |

---

## 6. Bot-to-Bot Messaging (for the planned second bot)

If you want **Hermes A** and **Hermes B** to talk to each other in the same group:

### 6.1 On each bot's side

```bash
# Allow messages from peer bots only when they @mention us
FEISHU_ALLOW_BOTS=mentions   # default is `none` (peer bot messages ignored)
```

### 6.2 Permission grant

Each bot's Feishu app needs `application:bot.basic_info:read` scope to **show the peer bot's name** instead of `ou_xxx`. Without it, peer bots still route correctly but display awkwardly.

### 6.3 Per-group rule

You may want one of:
- **Bot-to-bot only in dedicated groups**: create a group just for the bots, add both, set `group_rules[chat_id].policy: open` so they can message without @.
- **Bot-to-bot in shared group**: leave `require_mention: false` so they see all traffic (heavy on tokens — each bot processes every message).

### 6.4 Loop detection

**Risk:** Bot A replies to Bot B's message; Bot B sees Bot A's reply and replies back; infinite loop.

**Mitigation:** Hermes auto-ignores its own outbound messages from the same session, but **not** from the peer's perspective. If you see runaway loops, either:
1. Set `FEISHU_ALLOW_BOTS=mentions` (peer only replies if @mentioned)
2. Add a per-group rule `blacklist` for the peer bot's open_id

---

## 7. The `bot_removed` Recovery Flow (real bug, 2026-06-17)

This is **not in the official docs** — we hit it on 2026-06-17 and it took ~2 hours to diagnose.

### 7.1 Symptom

- All group messages stop arriving at the gateway
- Direct messages still work
- `hermes gateway status` says active
- `tail -f gateway.log` shows nothing new from groups

### 7.2 Root cause

When a bot gets **removed from a group** (admin action, accidental kick, etc.), Feishu's event subscription **for that specific group** enters an inconsistent state. The bot is still in the group (re-addable), but events aren't pushed until WS reconnects.

Even after re-adding the bot, **existing WS connection doesn't see it** until full reconnect.

### 7.3 Fix (always works)

```bash
systemctl --user restart hermes-gateway
```

Wait ~30s. WS reconnects, re-subscribes to events. Test by sending a message from another account in the group.

### 7.4 Diagnostic commands

```bash
# Is the bot even still in the group?
TOKEN=$(...)
curl -s "https://open.feishu.cn/open-apis/im/v1/chats/$CHAT_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import json,sys;d=json.load(sys.stdin);print('bot_count:',d['data'].get('bot_count'))"

# What's the gateway seeing?
grep -E "Inbound|WARNING|ERROR" ~/.hermes/logs/gateway.log | tail -50

# Has WS reconnected recently?
grep "WebSocket" ~/.hermes/logs/gateway.log | tail -10
```

### 7.5 Prevention

None perfect, but two habits help:

1. **Don't `bot.removed` from groups casually** — the bot's event subscription cache gets dirty.
2. **Set up a daily cron** that pings the bot (dark sends a "heartbeat" message once a day). If you don't get an ack within 5 min, run `systemctl --user restart hermes-gateway`.

---

## 8. Verification — Did It Work?

End-to-end smoke test (do all 4 in order):

### 8.1 Gateway is up

```bash
systemctl --user is-active hermes-gateway  # → active
curl -s http://127.0.0.1:8765/healthz       # → 200 OK (only if webhook mode)
```

### 8.2 DM works

From your phone (Feishu app, dark's account): search bot name → send "ping".

Expected: bot replies "👌 收到" within 1-3 seconds.

If no reply:
```bash
tail -30 ~/.hermes/logs/gateway.log
# Look for "Inbound direct message" — if present, problem is downstream
# If absent, check FEISHU_APP_ID/SECRET
```

### 8.3 Group @mention works

In any group the bot is in: `@bot-name test`.

Expected: bot replies.

If no reply in group (but DM works):
- `FEISHU_GROUP_POLICY` is wrong (should be `open` or user in allowlist)
- `FEISHU_REQUIRE_MENTION=true` and you didn't @mention

### 8.4 Group un-mention works (if `FEISHU_REQUIRE_MENTION=false`)

In group: send "test" (no @).

If bot doesn't reply: confirm `FEISHU_REQUIRE_MENTION=false` in `.env` and **restart gateway** (env changes don't hot-reload).

---

## 9. Common Pitfalls (compiled from real incidents)

| Pitfall | Symptom | Fix |
|---|---|---|
| App not published | Events never arrive | 版本管理与发布 → 创建版本 |
| Wrong app_id/secret | `invalid app_id` in logs | Re-copy from Feishu console |
| Empty allowlist + `allowlist` policy | Nobody in groups can use bot | Either populate allowlist or switch policy to `open` |
| `FEISHU_REQUIRE_MENTION=true` (default) | Bot silent in groups unless @ | Set `false` in `.env`, restart gateway |
| 6/17 `bot_removed` state | All group events stop | `systemctl --user restart hermes-gateway` |
| Forgot to add bot to group | No events at all | Group settings → 群机器人 → 添加 |
| Two Hermeses using same app_id | Second one fails to start | "Another local Hermes gateway is already using this Feishu app_id" |
| Card clicks return error 200340 | Approval buttons silently fail | Need 3 things: subscribe `card.action.trigger`, enable Bot capability's Interactive Card toggle, configure Card Request URL (webhook mode only) |
| Webhook mode but no public URL | Events arrive at localhost only | Either switch to WS or expose port 8765 with HTTPS |
| Recipient on `FEISHU_ALLOWED_USERS` not in group | Their DM works but group messages rejected | Add them to `FEISHU_ALLOWED_USERS` (different from being in group) |

---

## 10. Architecture Reference (where to look in code)

If you need to debug deeply, these files in `~/.hermes/hermes-agent/`:

| File | What it does |
|---|---|
| `gateway/platforms/feishu.py` | Main adapter — WS connection, message dispatch, send_message, allowlist enforcement |
| `gateway/platforms/feishu_comment.py` | Doc-comment intelligent reply handler |
| `gateway/platforms/feishu_comment_rules.py` | Per-doc access control (3-tier: exact → wildcard → top-level) |
| `gateway/platforms/feishu_meeting_invite.py` | Meeting bot (`vc.bot.meeting_invited_v1`) |
| `tools/send_message_tool.py` | LLM-facing tool for sending messages (line ~1720 imports FeishuAdapter) |
| `tools/feishu_doc_tool.py`, `feishu_drive_tool.py` | Doc read + drive comment reply tools |
| `website/docs/user-guide/messaging/feishu.md` | **The source of truth** — regenerate from this if confused |

---

## 11. Quick Reference Card

Save this as `~/.hermes/notes/feishu-cheatsheet.md`:

```bash
# Check bot identity
grep "Bot identity" ~/.hermes/logs/gateway.log | tail -3

# Find all open_ids that recently hit the bot
grep -oE "ou_[a-f0-9]{32}" ~/.hermes/logs/gateway.log | sort -u

# Recent errors
grep -iE "ERROR|WARNING" ~/.hermes/logs/gateway.log | tail -20

# Force restart
systemctl --user restart hermes-gateway

# Reset WS connection only (lighter than full restart)
kill -USR1 $(cat ~/.hermes/gateway.pid)

# Add user to allowlist (then restart)
echo "FEISHU_ALLOWED_USERS=ou_old,ou_new" >> ~/.hermes/.env
# OR edit in-place with sed, then restart

# Tail live gateway log
tail -f ~/.hermes/logs/gateway.log | grep --color=always -E "Inbound|ERROR|WARNING|$"
```

---

## Appendix A: Event Subscription Reference

Pulled from `open.feishu.cn/document/server-docs/event-subscription-guide/overview.md` (2026-06-18 snapshot):

- **Subscription methods**: WebSocket (long connection) or Webhook (HTTP POST). Same events, different transports.
- **v1.0 vs v2.0**: Feishu supports both. Hermes uses v1 (`im.message.receive_v1`) for compatibility.
- **Event ordering**: "有序事件" — Feishu guarantees order for events from the same app+chat combo within 60s. Don't expect global order.
- **Retry policy**: Feishu retries failed deliveries up to 3 times with backoff. Hermes dedups by `message_id` (24h TTL, `~/.hermes/feishu_seen_message_ids.json`).

## Appendix B: Source URLs

- Hermes Feishu guide (authoritative for our setup): `~/.hermes/hermes-agent/website/docs/user-guide/messaging/feishu.md`
- Hermes env var reference: `~/.hermes/hermes-agent/website/docs/reference/environment-variables.md` (lines 352-360 for FEISHU_*)
- Hermes full docs site: https://hermes-agent.nousresearch.com/docs/
- Feishu open platform: https://open.feishu.cn/
- Feishu event subscription overview: https://open.feishu.cn/document/server-docs/event-subscription-guide/overview
- Lark SDK for Python: https://github.com/larksuite/oapi-sdk-python

---

**Last verified**: 2026-06-18 against Hermes Agent v0.x and Feishu open platform v1.2.0.618.
**Owner**: dark@home — this doc is private. If anything changes on Feishu's side (new scopes, deprecations), update here and bump commit.
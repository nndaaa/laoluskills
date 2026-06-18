# Platform Probe Results — 2026-06-18

Raw transcripts from probing Chinese e-commerce data sources from a Linux Mint box. Use these to **avoid re-probing the same dead ends** in future sessions. All probes used `requests` + desktop browser `User-Agent` unless noted.

## 闲鱼 (goofish.com)

### Main site HTML
```
GET https://www.goofish.com/search?q=手工帆布包
→ 200, 10584 bytes
→ Content is SPA shell (title: 闲鱼 - 闲不住？上闲鱼！)
→ window.__baxiaReady (Baxia anti-bot)
→ No product data in HTML — JS-rendered.
```

### H5 subdomain
```
GET https://h5.goofish.com/
→ HTTPSConnectionPool: Failed to resolve 'h5.goofish.com'
→ DNS doesn't resolve from this host. Skip.
```

### MTOP protocol endpoints (all returned 200 with `FAIL_SYS_API_NOT_FOUNDED`)
Probed 5 endpoint patterns, all wrong:
- `mtop.taobao.idle.mainpage.search/1.0/`
- `mtop.taobao.idle.search.idle.search/1.0/`
- `mtop.idle.search.item.search/1.0/`
- `mtop.taobao.idle.search/1.0/`
- `mtop.taobao.idle.pc.search/1.0/`

Response shape:
```json
{"api":"","v":"","ret":["FAIL_SYS_API_NOT_FOUNDED::请求API不存在"],"data":{}}
```

**Endpoint names are obfuscated** (阿里 MTOP convention). Brute-forcing is not productive. Need to either:
- Reverse-engineer from the actual JS bundle (high effort)
- Login session + sign generation (account risk)
- Use Playwright with logged-in cookies

**Verdict: No public data path. Recommend manual-collect (rung 1).**

## 小红书 (xiaohongshu.com)

### Search page HTML
```
GET https://www.xiaohongshu.com/search_result?keyword=手工包&source=web_search_result_notes
→ 200, 766701 bytes
→ window.__INITIAL_STATE__ = {...} present
→ BUT content is app settings, NOT search results.
   Top-level keys: ["global"] — global has appSettings, ICPInfoList, notificationMap, etc.
   No noteList / searchNotes / items / feedList in __INITIAL_STATE__.
→ Search results are JS-rendered after page load.
```

### JSON parse gotcha
`__INITIAL_STATE__` contains `:undefined` literals which are not valid JSON. Replace before parsing:
```python
state_clean = state_raw.replace(':undefined', ':null')
state = json.loads(state_clean)
```

### Search API endpoints (all failed)
- `edith.xiaohongshu.com/api/sns/web/v1/search/notes` → 404
- `www.xiaohongshu.com/api/sns/web/v1/search/notes` → 500 `create invoker failed, service: jarvis-gateway-default`
- `edith.xiaohongshu.com/api/sns/web/v2/search/notes` → 404
- `www.xiaohongshu.com/api/store/v3/search/notes` → 503 `failure to get a peer from the ring-balancer`

**All require X-s / X-t signing (xiaohongshu's request signature).** Public access blocked.

**Verdict: No public data path. Recommend manual-collect (rung 1) or Playwright (rung 3).**

## 慢慢买 (manmanbuy.com)

### Tool API
```
GET https://tool.manmanbuy.com/api/historyLowestPrice.aspx?url=...
→ 500, body has garbled text (likely mis-decoded from non-UTF8)
```

### Search subdomain
```
GET https://search.manmanbuy.com/search.aspx?key=手工帆布包
→ HTTPSConnectionPool: Failed to establish a new connection: Connection refused
→ Subdomain not reachable from this host (DNS OK, port refused).
```

**Verdict: Subdomain not reachable. Skip this source.**

## 什么值得买 (smzdm.com)

### Search
```
GET https://www.smzdm.com/search/?keyword=手工帆布包
→ 404, 57482 bytes (HTML 404 page, not JSON)
→ The /search/ path doesn't exist. Real search is on a different subdomain/path.
```

### Initial probe
```
GET https://search.smzdm.com/?c=home&s=手工帆布包
→ 202, 209 bytes
→ 202 Accepted with no body. Likely a redirect step to a JS-rendered page.
```

**Verdict: Search doesn't work via plain GET. Skip for now.**

## Summary of what was tried and what works

| Platform | Plain HTML | Public API | Notes |
|---|---|---|---|
| 闲鱼 | ❌ SPA, no data | ❌ MTOP obfuscated | Use rung 1 (manual) |
| 小红书 | ❌ SPA, only app config | ❌ X-s/X-t required | Use rung 1 or 3 |
| 慢慢买 | ❌ subdomain refused | ❌ 500 | Skip |
| 什么值得买 | ❌ 404/202 | ❌ unknown | Skip |
| 淘宝 | not probed this session | — | Worth probing in future |
| 京东 | not probed this session | — | Worth probing in future |

## Re-probe checklist for future sessions

Before re-running these probes (since they may go stale), check:
- [ ] Has user upgraded network/proxy? Some of these were DNS or connection-refused errors that might resolve.
- [ ] Did 闲鱼/小红书 add public APIs? (Low probability but possible.)
- [ ] Did `__INITIAL_STATE__` start including search results? (Unlikely but check.)
- [ ] For 淘宝/京东, the 2026-06-18 session didn't probe — start fresh there.

When the user comes back with "let's try 闲鱼 again" or "what about 淘宝?", **load this file first** to know what was already tried.

---
name: chinese-ecommerce-data-harvesting
description: Harvest market data from Chinese e-commerce platforms (闲鱼/小红书/淘宝/京东/慢慢买/什么值得买/头条) from a personal Linux box using only `requests`-class tools (no Playwright, no paid API). Load when the user wants price/competitor/trend data from a Chinese platform and the data needs to come from public web sources, OR when prior attempts at direct scraping failed and you need to know the realistic alternatives, OR when the user wants a deep-dive on a specific category across 6 dimensions (需求/教程/成品/价格/渠道/风险). **As of 2026-06, 头条搜索 is the only public data path that actually works** — see references/toutiao-search-working-path.md and the new rung 1.5 in the escalation ladder.
---

# Chinese E-commerce Data Harvesting (no browser automation)

A playbook for pulling market data from Chinese platforms when you can't (or shouldn't) install Playwright. Assumes the user is on a personal Linux box, can run Python+requests, and the data is for personal research — not large-scale commercial scraping.

## When to load this skill

- User asks for 闲鱼 / 小红书 / 淘宝 / 京东 / 抖音 / 头条 competitor data, price surveys, hot product analysis, or trend tracking.
- A prior scraping attempt on a Chinese platform failed and you need to recognize the failure mode (signing required, endpoint obfuscation, geo-block, etc.) and pick the right fallback.
- User is OK with "I'll go browse on my phone and send you the links" as part of the workflow.
- User wants 选赛道 / 抄标题 / 看买家关注什么 — go straight to rung 1.5 (头条搜索).

## The reality check (state this in the first reply, NOT after planning)

**Free public-data harvesting from Chinese e-commerce platforms is largely blocked.** This is the consistent 2026 reality. Do not promise the user a fully automated pipeline unless you've already verified the specific endpoint works.

The honest up-front scoping is:

> "I can pull [specific working source, e.g. 头条搜索]. For 闲鱼/小红书 search results, the realistic paths are: (1) you collect 5-10 examples on phone and I structure them, (2) install Playwright with X-s risk, (3) pay for [X API]. My recommendation is [rung 1.5] for direction-setting."

**Workflow speed rule (learned the hard way):** if 1-2 probes on a platform fail (signing/MTOP/connection refused), **pivot to the fallback data source in the same reply**. Do not narrate 4-5 failed attempts before pivoting — the user is waiting, and the fallback was already known to be viable. State the failure concisely, recommend the next rung, ask for go-ahead.

**Vision pitfall when the user can see the page too:** if the user is observing the browser (via ToDesk/远程桌面) and you keep posting screenshots for "verification", you're making them wait for image recognition on data you could have parsed directly from the HTML. **Always extract data via DOM (`page.evaluate`), not via `vision_analyze` on screenshots.** Use screenshots only when (a) the data is rendered to a canvas/SVG/image that DOM can't reach, or (b) you're reporting progress to the user. The user's exact words in the 2026-06-18 闲鱼 session: **"截图来确认是不是要经过图片识别,页面html代码直接看数据不好么"** — yes, the HTML is the source of truth, parse it directly.

## Probing order — cheapest first

Run probes in this order, stop when one works:

1. **Plain HTML GET** with desktop browser headers (`User-Agent: Chrome/120`, `Accept-Language: zh-CN`). Some sites still SSR search results.
   - Parse `window.__INITIAL_STATE__ = {...}` or `window.__NEXT_DATA__` from the HTML. Replace `:undefined` → `:null` before `json.loads` (this is the most common JSON parse failure on these sites).
   - **If the data is in `window.T && T.flow({ data: {...} })` calls (头条 pattern)**, you need a bracket-pair parser — see `scripts/json_block_extractor.py`. `re.findall(r'\{.+?\}')` will fail on nested `{}`.
2. **Public REST endpoints** — guess common patterns (`/api/v1/search/...`, `/api/store/v3/...`). Check for `404 page not found` vs `503 service unavailable` vs `FAIL_SYS_API_NOT_FOUNDED` — they mean different things.
3. **MTOP-style platform APIs** (`h5api.m.goofish.com/h5/mtop.*`) — return JSON with `ret: ["FAIL_SYS_API_NOT_FOUNDED::请求API不存在"]` for wrong endpoint. Endpoint names are obfuscated; brute-forcing is not productive. **Skip this step unless the user is technical and the value is high.**
4. **Comparison sites** (慢慢买, 什么值得买) — they aggregate data you can't get from the source. Worth probing but most return 202/302/404 to non-browser requests. **In practice these are dead ends from outside CN — skip unless you have evidence the path works.**

**Stop conditions:**
- Stop at step 1 if `__INITIAL_STATE__` or `T.flow` data blocks contain the structure you need.
- Stop at step 2 if you get real data back (not 404, not 503, not signature error).
- Skip step 3 unless the user is OK with hours of endpoint enumeration.
- **Stop the whole probing loop after 1-2 platforms fail — go to rung 1.5 (头条搜索) or rung 1 (manual-collect).** Don't burn user time on a third or fourth probe.

## Distinguishing "blocked" from "wrong path"

When an API returns a non-data response, the error message tells you what to do next. This table comes from real 2026-06-18 probes:

| Response | Meaning | Next step |
|---|---|---|
| `200 + FAIL_SYS_API_NOT_FOUNDED` | Endpoint path is wrong, server reachable | Skip this MTOP path, try another |
| `200 + {"api":"","v":"","ret":[...]}` (with ret array) | Platform auth gateway, endpoint doesn't exist | Wrong path, server is fine |
| `404` with HTML body | Endpoint doesn't exist | Wrong path or method |
| `503 + "create invoker failed, service: ..."` | Service name/cluster not deployed at this URL | Wrong base URL |
| `500 + garbled text` | Server-side error or wrong Accept header | Try `Accept: text/html` instead of JSON |
| `200 + empty body / JavaScript-required` | SPA, data not in HTML | Switch to API endpoint or Playwright |
| `200 + 1.7MB HTML + 0 data blocks` | **Missing cookie preheat (字节系 pattern)** | Hit `/` first, then search — see `references/toutiao-search-working-path.md` |
| `Connection refused` / `Failed to resolve` | Network-level block, DNS, or geo-fence | Likely needs proxy or won't work from this host |

## The escalation ladder (pick the lowest rung that meets the need)

1. **Manual small sample + structure** (default for "what's selling" with ≤10 items)
   - User browses 10-20 items on phone, sends you titles/prices/links.
   - You structure into a CSV/Markdown table, run analysis.
   - 5-10 items is enough for direction-setting. Don't over-collect.
   - **Cost: 0. Risk: 0. Speed: depends on user.**

1.5. **头条搜索 via requests (with cookie-then-search trick)** ⭐ (default for 选赛道 / 抄标题 / 看趋势)
   - 5-15 keywords across the candidate 赛道s, 2 pages each, ~30 requests total.
   - Returns ~100-200 structured data points with title/engagement/author/datetime.
   - **Critical:** must first `GET https://so.toutiao.com/` to get cookies, THEN search. Bare search returns 0 results.
   - See `references/toutiao-search-working-path.md` for full setup and `scripts/json_block_extractor.py` for the parser.
   - **What it gives you:** 互动量 ranking, 爆款标题 patterns, 高频关键词云, 同类账号. **What it doesn't:** 闲鱼一手销量, 价格, 卖家信誉.
   - **Cost: 0. Risk: 0 (实测零封控). Speed: 2-3 分钟跑全量.**

2. **Slow public scraping with delays** (for price monitoring of a known set of items)
   - `time.sleep(random.uniform(3, 8))` between requests.
   - Rotate User-Agents via `fake-useragent`.
   - Works for known product-detail pages on 京东/淘宝 (which render server-side for SEO), NOT for 闲鱼/小红书 search.
   - **Cost: 0. Risk: medium (IP ban if greedy). Speed: 1 req/5s.**

3. **Playwright + Chromium** (for search-result pages on 闲鱼/小红书) ✅ verified working 2026-06-18
   - Install: `pip install playwright && playwright install chromium` (~200MB).
   - **Login flow that actually works (verified end-to-end on 闲鱼):**
     1. Start a **non-headless** browser on `DISPLAY=:0` (use `xvfb-run` if the host is headless). User must be able to see the window (ToDesk, VNC, etc.) — this is non-negotiable because they need to scan the QR with their phone.
     2. Load `https://www.goofish.com/` (or target platform's login URL). Wait for the QR code element to render.
     3. User opens the **mobile app**, taps scan, confirms login on the device.
     4. Detect login by waiting for the user's nickname in page text (e.g. `darksomee`) or for the "登录" button to disappear. **Don't rely on URL change** — 闲鱼's URL stays on `goofish.com` whether logged in or not, so a URL-based check gives false positives.
     5. Save cookies via `context.cookies()` → JSON. Cookies typically last 7-30 days; re-scan when the first request starts failing.
   - **Account ban risk is real but manageable.** Don't run in parallel; don't run > 1 session at a time; don't auto-act (like/follow/reply); limit to 1-2 platforms max. Always run with `headless=False` (or `xvfb-run` headless-equivalent) so the user can kill the browser if the account gets challenged.
   - **See `references/playwright-xianyu-login-and-scrape.md` for the full worked example: Xvfb setup, stealth config, login detection, search-result HTML structure, the extract-from-`title=`-attribute pattern, the auto-search-via-homepage pattern, the dump-HTML-then-extract-offline debug pattern, the don't-close-browser-during-verification hard rule, and the v11 detail-page extraction (主商品 vs 为你推荐/看了又看 — different DOM, different selectors).**
   - **Cost: 0 but ~200MB disk + setup time. Risk: MEDIUM (with the verification step + headful browser). Speed: 1-2 pages/min when careful.**
   - **Critical scrape-time controls (learned the hard way 2026-06-18):**
     - **Search pages: slow scroll to trigger lazy load.** 闲鱼 search results render ~8 cards/page initially, 24+ on scroll. Without 6-8 scrolls of `window.scrollBy(400-700px)` with 1.5-2.5s gaps between, you'll report 5 items when the page has 24. **This is the opposite of detail pages — see below.**
     - **Detail pages: DO NOT scroll.** The HTML for the main product (title/price/want/seller info) is fully rendered on initial load; no lazy load for the above-the-fold area. Scrolling adds 30s/page, triggers 风控 signals, and extracts only "为你推荐" data you don't want. v12 scraper (verified 2026-06-18) intentionally skips scroll. The user's exact words: *"现在不是图像识别,应该不需要移动页面"*.
     - **Inter-keyword delay 10-18s.** Even with login, hammering 4 keywords in 4 seconds triggers risk-control. Randomize the delay.
     - **Inter-detail-page delay 9s.** Same 风控 concern; v12 uses 9s when going search → detail → detail → detail.
     - **Detect 风控 signals per page:** text contains `验证码`, `滑块`, `访问频繁`, `操作过于频繁` → abort immediately, save what you have, tell the user.
     - **Don't filter "noise" labels without telling the user.** "退坑" / "全新" / "包邮" / "DIY" / "14岁以上" labels are signals, not garbage. The user said it best: **"退坑货其实也可能是吸引人的话术,一起采集"** — if you silently drop them, you'll undercount. Surface the label distribution in the report and let the user decide.
     - **If user is observing via ToDesk, trust their observation if it contradicts your output.** The user said **"我观察到的页面商品数量比你统计的好像要多"** → 99% the time the answer is your scroll was incomplete, not that your parser is wrong. Re-verify by counting `[title="¥"]` elements directly in the browser before debugging the parser.

4. **Paid data APIs** (慢慢买专业版, 蝉妈妈, 新榜)
   - User pays monthly subscription, you integrate the API key.
   - Stable, legal, comprehensive.
   - **Cost: ¥50-500/month. Risk: 0. Speed: depends on plan.**

**Default recommendation for a new task:**
- "选赛道 / 抄标题 / 看趋势" → **rung 1.5** (头条搜索, zero user involvement)
- "看具体某款竞品怎么定价" → rung 1 (manual) or rung 2 (京东慢速爬)
- "长期监控某品类价格" → rung 2 (slow public scraping)
- "需要闲鱼/小红书 24h 热卖榜" → rung 3 (Playwright, with user OK + risk acknowledgment)

Move to higher rungs only when lower rungs prove insufficient.

## Platform-specific notes (as of 2026-06)

| Platform | Public HTML data? | Public API? | Manual-collect? | Best rung |
|---|---|---|---|---|
| 闲鱼 (goofish.com) | No (SPA, no SSR data) | No (MTOP endpoints obfuscated, sign required) | Yes (mobile app) | 1 or 3 |
| 小红书 (xiaohongshu.com) | No (HTML is SPA shell, `__INITIAL_STATE__` has only app config not search results) | No (X-s/X-t signing required) | Yes (mobile app) | 1 or 3 |
| 淘宝 (taobao.com) | Partial (product detail pages SSR for SEO) | No (signing) | Yes | 1 or 2 |
| 京东 (jd.com) | Yes (product pages, search results) | Partial (some price APIs exposed) | Yes | 2 |
| 慢慢买 (manmanbuy.com) | No (`search.manmanbuy.com` connection refused from outside CN sometimes) | Limited tool API | Limited | 4 |
| 什么值得买 (smzdm.com) | No (returns 202/302 to non-browser) | No public API | Yes | 1 |
| **头条搜索 (so.toutiao.com)** | **Yes — see `references/toutiao-search-working-path.md`** | No | N/A | **1.5** ⭐ |

These will go stale. Re-probe in a future session before relying on them.

## Workflow template (use this when the user asks for 闲鱼/小红书/手工市场 data)

1. **First reply: scope honestly.** "I can pull public HTML data and known public APIs. For 闲鱼/小红书 search results, the realistic paths are: (1.5) 头条搜索 — gives 100-200 samples with zero user involvement, used for 选赛道/抄标题, but not 闲鱼一手销量; (1) you collect 5-10 examples on phone and I structure them; (2) install Playwright with X-s risk; (3) pay for [X API]. **For a 选赛道 question, rung 1.5 gives you more signal than rung 1 at zero user cost.**"

2. **Default to rung 1.5 first when the question is direction-setting.** Don't ask "which one do you want to focus on?" before data exists. Use `user-preferences` rule: capture broadly, narrow later.

3. **Don't narrate 4-5 failed probes before pivoting.** State the failure in one line ("3 platforms blocked, pivoting to 头条"), recommend rung 1.5, ask for go-ahead. The user is waiting.

4. **Structure what you got.** Turn the 100-200 data points into a per-赛道 comparison: total samples, related samples, **average engagement** (the key metric for picking a 赛道), Top 3 爆款 titles with summaries, 高频关键词云. **Average engagement can show 50-200x spread between 赛道s** — that's the actionable signal.

5. **Embed the conclusion in the report, not buried in JSON.** "**首选:卡通/钩针 IP,避开:真皮/通勤**" with the numbers. The user shouldn't have to read the data to get the recommendation.

6. **Use markdown dividers and emoji for scannability.** Report goes to 飞书 group chat; the family reads it on mobile.

7. **Always include a 简化版 section for non-technical readers** (e.g. spouse). "只看数字:" with a short bullet summary. The full report is for the technical user; the simplified version is for everyone else.

## Common pitfalls

- **Don't keep probing after 3 endpoint guesses fail.** The endpoint is obfuscated; more guessing won't help. Switch to manual-collect or rung 1.5.
- **Don't write a `curl | python3 -c` one-liner for a single value.** Use `requests` with a clear failure check.
- **Don't claim a JSON parse "worked" without printing the keys.** The trap is parsing the outer object successfully but the actual data being nested under an unexpected key (`searchResult.notes` vs `data.items`). For nested JSON, use a bracket-counter, not `re.findall(r'\{.+?\}')` — see `scripts/json_block_extractor.py`.
- **For 头条, the empty-data response IS the signal:** 1.7MB HTML with 0 data blocks means you forgot the cookie preheat. Don't iterate on the search request; hit the homepage first.
- **Don't install Playwright without explicit user OK and a risk acknowledgment.** The user trusts you with their IP; Playwright on a logged-in 闲鱼 account is the kind of thing that gets accounts banned.
- **Don't narrate failed probes to the user.** "Let me try X" × 5 wastes their time. State failure in one line, recommend next rung.
- **Don't paste raw URLs/commands in the reply** — see `user-preferences` privacy rule. Summarize what you did, let the user ask "贴命令" if they want the literal command.
- **Don't recommend "做 5 赛道" when 1 赛道 has 50-200x more signal.** The data will tell you the answer; trust it. 50x engagement spread is not a marginal difference.
- **⚠️ Time-filter the data before ranking categories — the biggest data-quality trap in Chinese content platforms.** A single 2019 viral article with 1150 互动 can dominate the average for a category and flip the ranking entirely. Always filter by `datetime[:4] >= '2024'` (or whatever cutoff matches "current trend"). The 2026-06-18 v1→v2 case study showed: with all-time data, 卡通钩针包 won; with 2024+ only, 拼豆 won. **The "winners" and "losers" swapped.** See `references/time-filtering-pitfall.md`.
- **Keep the working directory clean — don't accumulate script versions.** When iterating on a parser/scraper, **delete the old versions** once a new one is verified. The 2026-06-18 session accumulated `scrape_xianyu.py`, `v2`, `v3`, `v4`, `v5`, `v6`, `v7`, `v8`, `v9`, `v10` — ten files. The user eventually said **"前面版本不需要保留,只留最新"** (drop the old versions, keep the latest). The convention: **use a single filename per scraper** (e.g. `scrape_xianyu.py`) and overwrite it. If you need a reference to a past version, save it in a git commit or in a `references/` subfolder of the relevant skill, not in the working directory. The 闲鱼 working dir at the end of 2026-06-18 contained: `scrape_xianyu.py` (latest), `login_helper.py` (separate concern), `cookies_xianyu.json` (state), and `dump/` (HTML dumps + logs). That's it.

  **Companion rule: when you have a working script, snapshot it into the skill's `scripts/` directory** so it's not lost when the working directory is cleaned. The skill `scripts/scrape_xianyu_top_n_detail.py` is the v12 scraper; if `~/.hermes/projects/xianyu_research/` gets `rm -rf`'d, the working version survives. Same goes for the extractor (`xianyu_detail_extractor.py`) and any other parser module — keep one canonical copy in the skill, not ten in the working dir.
- **Don't assume Playwright = "fallback that works" for SPA platforms.** Tested 2026-06-18 headless-only: Playwright + headless Chrome + stealth config on 拼多多 and 小红书 both redirected to login pages (拼多多: `mobile.yangkeduo.com/login.html`, 小红书: shows login overlay, 0 note cards). **Headless alone is NOT enough — you need either (a) a non-headless browser visible to the user for QR scan, or (b) saved cookies from a prior login session.** Once you have those, 闲鱼 works reliably. See `references/playwright-xianyu-login-and-scrape.md` for the full pattern.

## Parser techniques for CSS-class-heavy SPAs (v12, 2026-06-18)

Modern SPAs (闲鱼, 小红书, 抖音, 拼多多 web) generate `class="module-name--HASH"` with a fresh hash on every build, but the *prefix* (`module-name`) is stable. Parsing these by hand involves four recurring techniques — get these right and you'll skip 5+ parser iterations:

### 1. Anchor-based slicing beats nested regex

**Don't** do this: `r'<div class="want--X">(.*?)</div>'` with `.*?` non-greedy. It breaks the moment the inner block has nested `<div>`s (the regex matches the *first* closing tag, truncating your data).

**Do** this: locate the *opening* tag's byte position, then read forward until the next known anchor:

```python
# Locate the opening tag
pos_match = re.search(r'<[^>]+class="want--[A-Za-z0-9]+"', html)
if not pos_match:
    return None
start = pos_match.end()
# Read forward until the next major class anchor
next_anchor = re.search(r'<[^>]+class="(?:desc|tips|notLoginContainer|labels?)--', html[start:])
end = start + next_anchor.start() if next_anchor else start + 1000
block = html[start:end]
# Now extract sub-fields from this clean block with simple regex
wm = re.search(r"(\d+)\s*人想要", block)
vm = re.search(r"(\d+)\s*浏览", block)
```

**When to use:** any time your inner data has nested elements of the same tag type (`<div>` inside `<div>`) and your data isn't the first child. The v12 `xianyu_detail_extractor.py` uses this for `desc--` (multi-`<span>` description) and `want--` (multi-`<div>` with `space--` placeholder) blocks.

### 2. Tolerate class-name trailing whitespace

Some Chinese SPA renderers emit `class="price--OEWLbcxC "` with a trailing space before the closing quote (React's `classnames` library does this when styles are conditional). Strict regexes `[A-Za-z0-9]+"` will silently miss the class. Use `\s*`:

```python
# Wrong:
r'class="price--[A-Za-z0-9]+"'
# Right:
r'class="price--[A-Za-z0-9]+\s*"'
```

### 3. Hybrid online+offline extraction (the v12 architecture)

When a Playwright script needs to do complex extraction, **don't write a 100-line `page.evaluate` JS block that mirrors your Python regex**. Instead:

1. Save the rendered HTML to disk in the same run: `Path("dump/x.html").write_text(await page.content())`
2. Call a Python extractor on the local file: `data = extract_detail_from_html(html)`
3. **Single source of truth for parsing logic** — change the regex once, both online and offline paths benefit.

This pattern also unlocks fast iteration: parser bug → edit Python file → re-run extractor on the *already-saved* HTML → no network, no 风控 risk, no 6-second page loads. v12 `scrape_xianyu_top_n_detail.py` is built this way.

### 4. Always include a `抓到 X / 预期 Y` summary

A parser that returns a non-empty list is not necessarily a working parser. End every extraction with a count vs. expected:

```
📊 抓到 1 个 | 预期 4 个  ← clearly broken
📊 抓到 4 个 | 预期 4 个  ← looks right
```

If you can't estimate Y, the count alone is still useful — the user can confirm by eye. The v12 scraper prints this; the v3–v7 versions didn't, which is why the "1/4" bug went undetected for several iterations.

## When the data shows N categories, don't just rank them — score them

A 选赛道 task often surfaces as "rank these N options". Don't stop at the heat ranking. Add a 2-axis overlay:

- **Heat score** (from the engagement data you have)
- **Difficulty score** (manually judge: how many tools/skills/space does it need? 入门=100, 简单=70, 中=40, 难=10)
- **Cost score** (起步投入; <¥100=100, ¥100-300=70, ¥300-500=40, >¥500=10)
- **Composite**: `0.5*heat + 0.3*difficulty + 0.2*cost` (heat dominates but you don't want to recommend a hard-to-start winner)

Then the report shows **TOP 3 with all three numbers**, not just "winner is X". The user gets to pick the trade-off (high heat + hard vs medium heat + easy), not be told a single answer they can't argue with.

This pattern caught a real blind spot in 2026-06-18: 拼豆 (heat 58.9) ranked #1 by heat but was #3 by raw "average" (because 卡通钩针包 had a 542-engagement viral 2024 article pulling its average up); scoring by composite (heat + ease + low cost) put 拼豆 at #1 because the difficulty/cost advantages dominated.

## After the user picks a category: deep-dive expansion

When the user picks one of the TOP 3 (or asks for a specific category), **don't jump straight to "execute on 闲鱼"**. Run a multi-dimensional deep-dive first. Pattern from 2026-06-18 拼豆 deep-dive:

**6 dimensions to cover, ~50 keywords total:**

| Dimension | What you're looking for | Example keywords (拼豆) |
|---|---|---|
| **demand** | 买家人群、动机、场景 | 拼豆, 拼豆为什么火, 拼豆 减压, 拼豆 亲子, 拼豆 上瘾 |
| **tutorial** | 学习路径、教程资源、入门门槛 | 拼豆教程, 拼豆 新手, 拼豆 工具, 拼豆 步骤 |
| **product** | 成品类型(决定你卖什么) | 拼豆挂件, 拼豆钥匙扣, 拼豆冰箱贴, 拼豆相框 |
| **sales** | 原料/工具/价格带 | 拼豆材料包, 拼豆熨斗, 拼豆模板, 拼豆工具套装 |
| **channel** | 销售渠道现状(竞品在哪卖) | 拼豆 闲鱼, 拼豆 淘宝, 拼豆 小红书, 拼豆 抖音 |
| **risk** | 合规/版权/安全雷区 | 拼豆 侵权, 拼豆 版权, 拼豆 儿童 安全, 拼豆 熔点 |

**Why each dimension matters:**

- `demand` — confirms there's a real audience, not just noise
- `tutorial` — tells you how hard the craft is to learn (affects time-to-first-product)
- `product` — narrows down what to make first (don't make everything, make the 3-5 highest-engagement types)
- `sales` — gives you a sense of the supply chain (where to source, what to sell alongside)
- `channel` — shows you where competitors are already selling (follow the crowd or pick an unsaturated channel)
- `risk` — **CRITICAL** — surfaces compliance, safety, copyright issues that could shut you down

**The risk dimension almost always has a hidden gotcha.** In 2026-06-18 it surfaced: 拼豆触电致死、毒气超标、3C 认证严查 — none of which would have been obvious from the demand data alone. Always run the risk dimension.

**Volume: 5-12 keywords per dimension × 6 dimensions = 30-72 keywords. Pages 2-3 each = 100-200 requests. Runs in 5-10 minutes. Time-filter all results to your cutoff (see `references/time-filtering-pitfall.md`).**

The report should end with **"前 10 行动" or "7-day 行动清单"** + **"5 条必看提醒"** — actionable, not abstract.

## After the research: end with 3 concrete next-step options, not open-ended questions

User-corrected pattern (2026-06-18): when the research is done, the user doesn't want a "what should I do?" — they want **3 concrete options to pick from**. Format:

> **下一步 3 选 1:**
> A. [具体动作 1] — [你的预期价值]
> B. [具体动作 2] — [你的预期价值]
> C. [具体动作 3] — [你的预期价值]

Each option should be **executable immediately** (e.g. "我给你列 1688/拼多多具体采购清单(店铺+链接+预算)" — not "let's research 1688"). The user picks one, you execute. This drives decisions forward and avoids the open-ended "I'll do whatever you think" trap.

The 3 options should be **distinct paths**, not variants of the same thing. Common pattern:

- A: **Buy materials and start** (action-oriented, fast feedback)
- B: **Make 1 sample first** (risk-averse, validates skill)
- C: **List on 闲鱼 directly** (skip the learning, go straight to market test)

## When the data shows a hard wall, disclose it plainly + propose fallback

User-validated pattern (2026-06-18): when 闲鱼/淘宝/小红书/拼多多 all blocked public data, the user explicitly asked "这个人工参与太多" after I proposed manual collection. The honest disclosure worked:

> "淘宝/拼多多/小红书公开爬虫全部被风控,我抓不到真实价格。**价格区间基于头条报道 + 行业常识估算。**"

Then propose 2-3 fallback paths (estimate from supply chain, ask user to verify on phone, pay for API). The user accepted the disclosure + the estimate. This **builds trust** because the agent is being straight about limitations instead of faking authoritative numbers.

**Rule:** if a number in the report is not from a real measurement, say so. Format: "⚠️ 注:本数字基于 X 估算,未直接测量。验证方式:Y。"

Don't say "estimated" alone. Say "based on X, validate via Y" — gives the user a way to check.

## Reference files

- `references/platform-probe-results.md` — raw probe transcripts and response shapes from the 2026-06-18 session. Re-use when re-probing these platforms in future sessions.
- `references/xianyu-storage-and-cleanup.md` — **why SQLite over JSON for v12+** (the three questions the user asked: cleanup / format / sustainability, all answered). Covers the schema design choices (item_id UNIQUE, price as TEXT, JSON in TEXT for shipping_tags/images), the three cleanup hooks (delete-on-import, 3-day HTML, 7-day log), the "single source of truth" pattern (online script = thin wrapper around offline extractor), and the operations the user can do with `python3 xianyu_db.py` and `sqlite3 data/xianyu.db`. Read this before deciding storage format for any future Chinese-platform scraper.
- `references/playwright-xianyu-login-and-scrape.md` — **verified rung 3 worked example** for 闲鱼 with Playwright + 扫码登录 via non-headless browser + ToDesk. Includes Xvfb setup, login detection by nickname (not URL), the actual 闲鱼 search-result HTML structure (cards are divs not `<a>`; real container is `feeds-content--<hash>` not `content-container`; title in `row1-wrap-title` `title` attr, price in `price-wrap` `title` or `number`+`decimal` spans, want count in `text--MaM9Cmdn` `title`), the slow-scroll rhythm, the auto-search via homepage input pattern (the old `/p/pc-list/wrap` URL now 404s), the dump-HTML-then-extract-offline pattern (saves network round-trips during parser debugging), and the don't-close-browser-during-verification rule. **Last updated 2026-06-18 v10** with all selectors and patterns verified against the live SPA. Load this the first time you reach for Playwright + a SPA platform with a QR-login.
- `references/toutiao-search-working-path.md` — **the working public data path for 2026** (cookie-then-search trick, parser, fields, noise filter, comparison with manual-collect). Load this whenever the user wants Chinese e-commerce market data.
- `references/time-filtering-pitfall.md` — **CRITICAL**: why you must time-filter ranking data before recommending a 赛道. The 2026-06-18 v1→v2 case study (拼豆 overtook 卡通钩针包 once 2019-2023 viral content was filtered out). Load before any "rank categories" analysis.
- `references/deep-dive-dimensions.md` — the 6-dimension keyword expansion pattern (demand/tutorial/product/sales/channel/risk) used after a category is picked. Worked example: 拼豆 in 2026-06-18. Each dimension has a "why it matters" rationale and a risk-dimension gotcha.

## Scripts

- `scripts/json_block_extractor.py` — bracket-pair JSON parser for SPA-injected data blocks (`window.T && T.flow({ data: {...} })` pattern). Reusable for any nested-JSON extraction from HTML. Has built-in self-tests.
- `scripts/category_scoring.py` — composite heat × difficulty × cost scoring for 选赛道. Run after time-filtering. Worked example uses the 2026-06-18 手工品类 data. Modify the `EXAMPLE_DIFFICULTY` / `EXAMPLE_COST` dicts for your domain.
- `scripts/xianyu_extractor.py` — **search/listing page** extractor. Slice by `[class*="feeds-content"]`, extract title/price/want from `row1-wrap-title` / `price-wrap` / `text--MaM9Cmdn` attributes. Has both `extract_from_html()` (offline) and `extract_from_page()` (online) entry points, with self-tests. **Will not work on detail pages** — use the next script for that.
- `scripts/xianyu_detail_extractor.py` — **detail page** extractor. Extracts the main product (not the "为你推荐" / "看了又看" items at the bottom) by anchoring on classes unique to the main product area: `desc--` (title+description), `price--` (price), `want--` (wants+views), `post--` (shipping tags), `item-user-info-nick--` (seller nick), `item-user-info-level--` (信用等级 from img title), and 5× `item-user-info-label--` (地区/上次登录/注册/成交/好评率 in fixed order). Same offline/online pattern as the search extractor. **Use this when you need 已售数 / 真实价格 / 卖家地区 / 卖家信誉** — the search extractor doesn't reach those. **v12 (2026-06-18) added `images` field** — main product image URLs, filtered by `class*=fadeInImg` + `src*=bao/uploaded` to exclude system icons and ad banners.
- `scripts/xianyu_db.py` — **SQLite storage layer** (added v12+, 2026-06-18). Single table `xianyu_items` with UNIQUE on `item_id`, indexed on `keyword`/`captured_at`/`want`/`price`. `save_items(items, keyword, conn, delete_html_after=True)` does upsert (INSERT … ON CONFLICT UPDATE) so re-running on the same item just updates `want`/`views`/`price` without creating duplicates. `cleanup_old_htmls(dump_dir, keep_days=3)` and `cleanup_old_logs(log_dir, keep_days=7)` keep the working directory from growing unbounded. **`stats(conn)`** returns total / keywords / unique sellers / DB file size. **Run `python3 xianyu_db.py` (no args) to see current DB state + want TOP 5.** SQLite is the right format for this kind of data: ~1KB per row, queries are <10ms even at 100k rows, single file you can `sqlite3 data/xianyu.db` to inspect.
- `scripts/scrape_xianyu_top_n_detail.py` — **the v12 working scraper** end-to-end: login with cookies → auto-search via homepage input (the old `/p/pc-list/wrap` URL now 404s) → grab top N detail pages → **write to SQLite via `xianyu_db.save_items()`** (replaces old JSON dump) → **auto-cleanup** HTML files older than 3 days and logs older than 7 days. Critical runtime rules: **do NOT scroll the detail page** (HTML is fully rendered on load; scrolling triggers anti-bot signals), **wait 9s between detail pages** (faster triggers 风控), **never close the browser** during verification (use `await asyncio.Event().wait()` to hang forever; user closes manually). Reads `KEYWORD`, `TOP_N`, `INTERVAL`, `KEEP_HTML_DAYS`, `KEEP_LOG_DAYS` from constants at top — change those to re-run with different keywords. Output: `dump/xianyu_top4_v12.json` (single-batch debug copy) + `data/xianyu.db` (the real persistent store). **Verified 2026-06-18 on 拼豆挂件**: 4 items, all 13 fields + images captured cleanly into SQLite.

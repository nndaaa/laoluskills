# Playwright + 闲鱼 + 扫码登录 — End-to-End Worked Example (2026-06-18, updated v11)

Verified working on Linux Mint 22, Python 3.11, Playwright 1.x + Chromium 120. The user is reachable via ToDesk (so they can see the browser window) and has the 闲鱼 mobile app installed. This is the **rung 3 escape hatch** when rung 1.5 (头条) is not enough and the user actually needs 闲鱼一手指尖数据.

## ⚠️ HARD RULE: Never close the browser while the user is debugging (v11)

The user has corrected this **three times in one session** ("调试时不要关闭页面", repeated). The first time the page auto-closed mid-verification. The second time the same script re-ran on a different keyword and closed before the user could compare.

**Mandatory pattern for any debugging script:**

```python
# Right:
print("🔵 页面留给你,Ctrl+C 关闭")
await asyncio.Event().wait()  # hangs forever; user closes the browser manually

# Right (with a hard ceiling):
await page.wait_for_timeout(1800_000)  # 30 min ceiling
# Warn the user with HH:MM in the script output so they know when it auto-closes

# WRONG:
await page.wait_for_timeout(60_000)
await browser.close()  # ← never do this during a debug session
```

**Why this rule is hard, not soft:** the user is verifying data by eye. If your script says "got 4 items with these prices" and the user looks at the browser to double-check, they cannot do that after `browser.close()`. They then have to ask you to re-run the script (more network, more 风控 risk, more time) just to do a sanity check.

**What "debugging" means here:** any script the user is observing the output of in real time. The only legitimate bounded close is when (a) the user has explicitly asked for a one-shot run, (b) the script is part of a cron job with no observer, or (c) the user has acknowledged the auto-close. None of those are "let me check the page" debugging.

## When to reach for this

- User has a 闲鱼 account and is OK with us taking over a session (we will only **read** — never post, reply, follow, or modify listings)
- User can see the browser window remotely (ToDesk / VNC / 远程桌面)
- Headline data missing from 头条 is critical: 已售数, 真实价格, 卖家地区, 库存状态
- Time budget: ~15-30 min per run (login + 4-8 keyword searches + cleanup)

## The setup checklist (one-time per host)

```bash
# 1. Install Playwright + Chromium
pip install playwright
playwright install chromium
# ~200MB. May need: playwright install-deps chromium

# 2. Verify Xvfb / display is available
which Xvfb xvfb-run
DISPLAY=:0 xset q | head -2   # should print "Keyboard Control: auto repeat: on..."
```

If you don't have an X display, use `xvfb-run python3 your_script.py` to get a virtual one. The user still needs to see the browser window — pair Xvfb with ToDesk or another remote-desktop tool.

## The login flow (works the first time, every time)

The key insight from 2026-06-18: **URL-based login detection is unreliable on 闲鱼**. The URL stays on `goofish.com` whether you're logged in or not, so checking `if 'login' not in url` gives a false positive on the initial (logged-out) page load. Detect login by looking for the **user's nickname** in the page text instead.

```python
# Save the user's tracknick from the login confirmation as the detection signal
# After scanning, the page contains the nickname; before scanning, it doesn't.

async def wait_for_login(page, expected_nick: str, timeout_s: int = 120):
    """Poll page text for expected_nick or for the '登录' button to vanish."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        text = await page.evaluate('document.body.innerText')
        has_login_btn = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a, button')).some(
                e => e.textContent.trim().replace(/\\s+/g, '') === '登录'
            );
        }""")
        if expected_nick in text and not has_login_btn:
            return True
        # Refresh QR every 60s (it expires)
        if int(time.time()) % 60 < 3:
            await page.reload(wait_until='domcontentloaded')
            await page.wait_for_timeout(3000)
        await page.wait_for_timeout(2000)
    return False
```

After login, save cookies for re-use across sessions:

```python
cookies = await context.cookies()
with open('cookies_xianyu.json', 'w') as f:
    json.dump(cookies, f, ensure_ascii=False, indent=2)
# Cookies are valid 7-30 days. If the first request after reload 401s, re-scan.
```

## The Xianyu HTML structure (the part that bit us 7+ times)

After login, search pages render ~8 cards per viewport but **only 5 cards are in the DOM on initial load**. More load on scroll (lazy). Each card is a nested `<div>` — **NOT an `<a>` tag** — so the natural `a[href*="/detail?"]` selector matches nothing.

**Updated 2026-06-18 v10 (real-world verified):** the v3–v7 patterns below used the wrong card container and reported **1/4 items** instead of 4/4. The corrected container + selector map is what actually works on the live 闲鱼 SPA right now.

Verified selectors and patterns (2026-06-18 v10):

- **Card container:** the 4-column row is wrapped in `<div class="feeds-content--<hash>">` — **NOT** `content-container--<hash>` (that one only matches 1 of 4 items, and only on some pages). The per-row class `row4-wrap-seller--<hash>` is a *child* of `feeds-content`. Use `[class*="feeds-content"]` for card slicing; the per-row class is just the seller block.
- **Title:** lives in the **`title` attribute of `row1-wrap-title--<hash>`**, not the `main-title` span. Example: `<div class="row1-wrap-title--qIlOySTh" title="[现货包邮]星露谷物语手工成品拼豆…"><span class="main-title--sMrtWSJa"><img …>[现货包邮]…</span></div>`. Read the parent's `title` attribute; the span's text may contain `<img>` tags you have to strip.
- **Price:** `price-wrap--<hash>` block contains a `title` attribute **OR** three child spans: `<span class="sign--x6uVdG3X">¥</span><span class="number--NKh1vXWM">19</span><span class="decimal--lSAcITCN">.90</span>`. **Prefer the `title` attribute** — if missing, concat `number` + `decimal` (skip `sign` or you get `¥¥9.90`).
- **"X人想要" (wanted count):** `<div class="text--MaM9Cmdn" title="6971人想要" …>6971人想要</div>`. The class is the same one used for the price in older patterns — the discriminator is the `title` attribute's text.
- **"已售X" (sold count):** rare on the search page; appears on detail pages.
- **"累计降价X%":** `<div class="text--MaM9Cmdn" title="累计降价90%" …>累计降价90%</div>`.

So the extraction pattern is:

1. Slice the page by `[class*="feeds-content"]` (30+ cards per page after lazy scroll).
2. For each card: read `title` attr of `row1-wrap-title` (title), read `title` attr of `price-wrap` OR concat `number`+`decimal` (price), read `title` attr of `text--MaM9Cmdn` and check for `数字人想要` (want count).
3. Title/price/want are 100% in HTML attributes — never needs vision.

The full extract is in `scripts/xianyu_extractor.py` (if you add it later). For now, here's the minimal version that works (v10, all three elements 100% hit rate):

```python
# 1. Slice by [class*="feeds-content"] — the real 4-column card container.
# 2. For each card, read title/price/want from the documented attributes.
# 3. None, missing → 0 (NEVER leave as None; the user wants 0 or a real value).
# 4. Walk up via document.querySelectorAll('*').indexOf(card) is fragile;
#    using a per-card regex against the .outerHTML is more reliable.

import re

async def extract_items(page):
    return await page.evaluate("""
        () => {
            const items = [];
            const cards = document.querySelectorAll('[class*="feeds-content"]');
            for (let i = 0; i < cards.length; i++) {
                const card = cards[i];
                // Title: title attr of row1-wrap-title
                const titleEl = card.querySelector('[class*="row1-wrap-title"]');
                const title = titleEl ? (titleEl.getAttribute('title') || '') : '';
                // Price: prefer price-wrap title attr, fallback to number+decimal
                const priceEl = card.querySelector('[class*="price-wrap"]');
                let price = '';
                if (priceEl && priceEl.getAttribute('title')) {
                    price = priceEl.getAttribute('title');
                } else {
                    const num = card.querySelector('[class*="number--"]');
                    const dec = card.querySelector('[class*="decimal--"]');
                    if (num) price = (num.textContent || '').trim();
                    if (dec) price += (dec.textContent || '').trim();
                }
                // Want: text--MaM9Cmdn with title="数字人想要"
                const wantEl = card.querySelector('[class*="text--MaM9Cmdn"][title*="人想要"]');
                let want = 0;
                if (wantEl) {
                    const m = (wantEl.getAttribute('title') || '').match(/(\\d+)\\s*人想要/);
                    if (m) want = parseInt(m[1]);
                }
                if (title || price || want) {
                    items.push({ title, price, wanted_count: want });
                }
            }
            return items;
        }
    """)
```

## The scrape rhythm (mandatory; 4 mistakes are documented)

For each keyword: 7s wait for initial render, then **8 slow scrolls of `window.scrollBy(400-700px)` with 1.5-2.5s gaps**, then `window.scrollTo(0,0)`, then 2s, then extract. **Without the slow scrolls you get 5 items per page instead of 24.**

Between keywords, sleep **10-18s randomly**. The first version of the scraper that ran all 4 keywords in 4 seconds triggered visible 风控 behavior on the second run.

After every page-load, check for 风控 text. If found, abort, save what you have, tell the user. The risk control words are: `验证码`, `滑块`, `访问频繁`, `操作过于频繁`.

## When scraper output contradicts the user's eyes

If the user is observing the page (ToDesk) and says "I see more items than your output", **trust them**. The most common cause is incomplete scroll (you stopped scrolling before all items lazy-loaded). Diagnose by running this in the browser before debugging your parser:

```javascript
document.querySelectorAll('[title*="¥"]').length   // should match your extracted count
```

If that number is higher than your output, your scroll loop is the bug, not your parser. Increase scroll count, increase delay, retry.

## Pitfalls discovered in this session

1. **The login detection v1 (URL-based) closed the browser after 9 seconds thinking the user was logged in.** Always check the actual login state, not URL.
2. **The first extraction used `a[href*="detail?"]` and got 0 items** because cards are divs, not anchors. Always dump the page HTML and `grep` for class names first.
3. **The first scroll loop used 1-second delays between scrolls, getting 5 items/page.** 8 scrolls with 1.5-2.5s gaps is the minimum for 24+ items/page.
4. **"退坑" is a signal, not noise.** If you filter it out silently, you undercount. Surface the label mix in the report; let the user decide.

## Auto-search via the homepage input (don't go straight to a search URL)

**Verified 2026-06-18 v10:** `https://www.goofish.com/p/pc-list/wrap?keyword=X` now returns **404 Not Found**. The old direct-URL path is dead. The working path is to **navigate to the homepage first, then drive the search input via Playwright**:

```python
async def search_via_homepage(page, keyword):
    # 1. Go to homepage (this also refreshes cookies on the platform's domain)
    await page.goto("https://www.goofish.com/", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    # 2. Find the search input — try a list of likely selectors
    selectors = [
        'input[placeholder*="搜"]',
        'input[placeholder*="想找"]',
        'input[type="search"]',
        'input.search-input',
        'input[class*="search"]',
        'header input',
    ]
    input_el = None
    for sel in selectors:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            input_el = el
            break
    if not input_el:
        # Fall back: list every input and let the user pick
        inputs = await page.query_selector_all("input")
        raise RuntimeError(f"No search input found; page has {len(inputs)} inputs: "
                           + str([(await i.get_attribute('placeholder'),
                                   await i.get_attribute('class')) for i in inputs[:5]]))
    # 3. Type + Enter
    await input_el.click()
    await input_el.fill("")
    await input_el.type(keyword, delay=80)   # humanized per-char delay
    await page.wait_for_timeout(500)
    await input_el.press("Enter")
    # 4. Wait for the URL to change to a search results page
    await page.wait_for_url(
        lambda u: "keyword=" in u or "search" in u or "q=" in u or "list" in u,
        timeout=30000,
    )
    await page.wait_for_timeout(5000)  # let first batch of cards render
```

**Default to full automation, never bounce the search step back to the user.** The user's exact words in 2026-06-18: **"应该是直接到首页,看见数据框后点击后输入关键词…你的脚本应该可以实现查找输入框后点击贴入关键词,而不是我操作"** (it should go to the homepage, find the search box, click and type the keyword — your script should be able to do this, not me). The same preference applies to every other "I could automate this but I'm leaving it to you" step: **default to automating; only ask the user to act when automation truly cannot do it (e.g. QR scan, CAPTCHA, paid login).**

## Dump HTML locally, then extract offline (the local-debug pattern)

**User request 2026-06-18:** *"每次都连网络然后再进行分析修改,效率有点低,是不是在调试阶段中,把页面存下本地,本地对齐后再上网络验证"*. Yes — when debugging a parser, every iteration of `python3 scrape_xianyu.py` costs a full network round-trip and a real 风控 risk. The fix is to **save the rendered page HTML to disk on the same run that does the network fetch**, then iterate on the parser against the local file:

```python
# In the scraping script, on the same page that you just extracted from:
import re
from pathlib import Path
Path("dump").mkdir(exist_ok=True)
html = await page.content()
Path(f"dump/{keyword}_v10.html").write_text(html)
# Now you can iterate the parser in a separate Python session, offline, fast.
```

Offline iteration looks like this:

```python
from pathlib import Path
import re
html = Path("dump/拼豆挂件_v10.html").read_text()
# Slice by [class*="feeds-content"] and run the same regex as the page.evaluate version.
# 100% reproducible, no network, no risk.
```

**Rule for debugging scrapers:**
1. Network fetch ONCE → save HTML locally.
2. Iterate the parser against the local file until it works.
3. Re-fetch only when the live page structure might have changed (i.e. when the parser still fails after N iterations on the same local file).

This 10x's the debug loop and keeps the 风控 risk at one fetch per real-world change, not one per parser iteration.

## Don't close the browser while the user is verifying

**User correction 2026-06-18:** *"页面已经被你关掉了"*. The script had a `page.wait_for_timeout(N)` followed by `browser.close()`. If the user wants to verify the data in the browser window (via ToDesk), the page is gone the moment you close it.

- **Default:** when running a script that ends with a "human verification" window, **drop the `browser.close()`** and let the script hang on `page.wait_for_timeout(...)` indefinitely. The user closes the browser when they're done.
- If the user wants a bounded window, set the wait to a long timeout (10+ min) and put `browser.close()` *after* it — and warn the user in the script output that the browser will close at HH:MM.
- If the user just says "let me check the page" mid-run: do **not** let the script's normal teardown fire. The user can always Ctrl+C the script; the page will close cleanly because Playwright cleans up the child process. The trap is when the script *automatically* closes the page as part of normal flow.

## What to do when v3 / v4 / v5 / v6 / v7 of a parser all return wrong data

The 2026-06-18 session went through **7 parser iterations** before landing on the correct container selector. The pattern that finally broke the loop: **stop iterating on the page.evaluate, dump the page HTML to disk, and grep for the class names actually present in the live page**. Once the real container was visible in the saved HTML, the v10 fix was obvious (the wrong container `content-container` was used 7 times because the original guess happened to match a single, mostly-empty card and the test was "did we get *some* rows" instead of "did we get *all* rows").

- **Always include a count check in the report** (e.g. "got 1/4 cards" vs "got 4/4 cards"). A parser that returns a non-empty list is not necessarily a working parser.
- **Always show a `抓到 X / 预期 Y` summary at the end of the scraper output.** If X < Y, the parser is wrong, not the network.
- **When the user says "数据采集不到,肯定是页面分析有问题"** — they're right. Don't argue; the live DOM is the source of truth. Dump it, inspect it, fix the selector.

## Cost / risk summary

- Setup: ~5 min one-time (Playwright install + display check)
- Per-run: ~10 min for 4 keywords (login + 4× 2-min search + cleanup)
- Storage: ~200MB Chromium download
- **Account risk: MEDIUM, not HIGH, with the controls above.** The 2026-06-18 run with these controls completed without any 风控 trigger or 401.
- Reuse: cookies last 7-30 days. If a request 401s, prompt the user to re-scan.

## Detail-page extraction (v11, verified 2026-06-18)

Search-page selectors above only get you `title / price / wanted_count`. To get **真实销量 (已售) / 卖家信用 / 卖家地区 / 描述 / 卖家昵称**, you have to follow the link into the detail page (`https://www.goofish.com/item?id=...&categoryId=...`). The detail page has a **completely different DOM class structure** from the search page — using the search-page selectors on the detail page yields zeros or wrong data.

### Why naive detail-page extraction fails

The detail page embeds **two extra sections** at the bottom:

- **"为你推荐"** (a row of 5-6 recommended products with the same `number--/decimal--/text--MaM9Cmdn` price/want classes as the search page)
- **"看了又看"** (a grid of related products with the same structure)

If you run the search-page extractor on the detail page, **you extract the recommended items, not the main product**. The main product uses different classes. The 2026-06-18 v11 case: first attempt extracted ¥27.99 / 8人想要 (the first "为你推荐" item) instead of ¥25 / 3人想要 (the real main product).

**Rule:** for detail pages, anchor on classes that are **unique to the main product area** (the seller info section, the tips/price block) — not on classes shared with the recommendations.

### Verified detail-page selectors (v11)

| Field | Class selector | Example value | Notes |
|---|---|---|---|
| Title | `[class*="desc--"]` → first `<span>` text | Hello Kitty像素风拼豆挂件 钓鱼造型 | Strip inner `<img>` if any. |
| Price | `[class*="price--"]` (e.g. `price--OEWLbcxC`) | 25 | **Not** `number--/decimal--` (those are search-page only). The class is stable across builds; the `--XXXX` suffix varies. |
| Wants | `[class*="want--"]` → first `<div>` text | 3人想要 | Format: `数字人想要`. |
| Views | `[class*="want--"]` → second `<div>` text | 95浏览 | Sibling of the wants div. |
| 包邮/自提 tags | `[class*="post--"]` | 包邮, 可自提 | One or more per item. |
| 卖家昵称 | `[class*="item-user-info-nick--"]` | 大黑黑黑 | Single div, no children with text. |
| 卖家地区 | `[class*="item-user-info-label--"]` index [0] | 金华 |  |
| 上次登录 | `[class*="item-user-info-label--"]` index [1] | 4分钟前来过 |  |
| 注册时间 | `[class*="item-user-info-label--"]` index [2] | 来闲鱼9年 |  |
| 卖出件数 | `[class*="item-user-info-label--"]` index [3] | 卖出47件宝贝 |  |
| 好评率 | `[class*="item-user-info-label--"]` index [4] | 好评率100% |  |
| 描述 | `[class*="desc--"]` → all `<span>` texts, joined | (full description) | Multiple `<br>`-separated lines. |
| 信用等级 | `[class*="item-user-info-level--"]` → `<img title>` | 极好 / 良好 / etc. | Image-based, read from the `<img title>` attribute. |

**The 5 seller labels use the same class** (`item-user-info-label--<hash>`). They appear in this fixed order: 地区 → 上次登录 → 注册 → 成交 → 好评率. Index by position; don't try to differentiate by content.

### Working detail-page extraction (v11, all fields hit)

```python
import re
from pathlib import Path

def extract_detail_from_html(html: str) -> dict:
    """Offline extraction from a saved detail-page HTML file.

    Anchors on classes unique to the main product (desc--, price--, want--, item-user-info-*).
    Will NOT pick up recommended/related products at the bottom of the page.
    """
    out = {
        "title": "", "price": "", "want": 0, "views": 0,
        "shipping_tags": [], "seller_nick": "", "seller_level": "",
        "seller_labels": [],  # [地区, 上次登录, 注册, 成交, 好评率]
        "desc": "",
    }

    # Title: desc-- first span
    desc_block = re.search(
        r'<span class="desc--[A-Za-z0-9]+"[^>]*>(.*?)</span>', html, re.DOTALL
    )
    if desc_block:
        # First <span> inside the desc is the title
        inner = re.search(r'<span>(.*?)</span>', desc_block.group(1), re.DOTALL)
        out["title"] = re.sub(r"<[^>]+>", "", inner.group(1) if inner else desc_block.group(1)).strip()

    # Price: price-- div, NOT number--/decimal-- (those are recommendations)
    p = re.search(r'<div class="price--[A-Za-z0-9]+"[^>]*>([^<]+)</div>', html)
    if p:
        out["price"] = p.group(1).strip()

    # Want + Views: want-- divs
    want_block = re.search(
        r'<div class="want--[A-Za-z0-9]+"[^>]*>(.*?)</div>(?=<div|<a)', html, re.DOTALL
    )
    if want_block:
        wm = re.search(r'(\d+)人想要', want_block.group(1))
        vm = re.search(r'(\d+)浏览', want_block.group(1))
        out["want"] = int(wm.group(1)) if wm else 0
        out["views"] = int(vm.group(1)) if vm else 0

    # Shipping tags: post--
    out["shipping_tags"] = re.findall(
        r'<div class="post--[A-Za-z0-9]+"[^>]*>([^<]+)</div>', html
    )

    # Seller nick
    sn = re.search(
        r'<div class="item-user-info-nick--[A-Za-z0-9]+"[^>]*>([^<]+)</div>', html
    )
    out["seller_nick"] = sn.group(1).strip() if sn else ""

    # Seller level (信用极好/良好/etc. from img title)
    sl = re.search(
        r'<div class="item-user-info-level--[A-Za-z0-9]+"[^>]*>.*?title="([^"]+)"',
        html, re.DOTALL,
    )
    out["seller_level"] = sl.group(1).strip() if sl else ""

    # Seller labels (5 of them, in fixed order)
    out["seller_labels"] = re.findall(
        r'<div class="item-user-info-label--[A-Za-z0-9]+"[^>]*>([^<]+)</div>', html
    )

    # Full description: every <span> inside the desc block
    if desc_block:
        spans = re.findall(r'<span>(.*?)</span>', desc_block.group(1), re.DOTALL)
        out["desc"] = " | ".join(re.sub(r"<[^>]+>", "", s).strip() for s in spans)

    return out
```

### The "为你推荐" pitfall — detection pattern

If you ever need to extract BOTH the main product AND the recommended items (e.g. for cross-validation), isolate them by **DOM region**:

- **Main product region:** everything from `<div class="tips--...">` down to the start of `<div class="item-user-info-...">` (the seller block is the marker that you've left the main product area).
- **"为你推荐" region:** the row right after `<text>为你推荐</text>` — items in that row use the search-page class structure (`number--/decimal--/text--MaM9Cmdn`).
- **"看了又看" region:** further down, look for `<text>看了又看</text>`.

A regex that doesn't anchor on these region markers will mix them up.

### Debugging: detail page vs search page

If you save a detail page HTML and your parser returns data that looks like search-page data (e.g. the price has a decimal `.90` from `number--+decimal--` concat), **you parsed the recommendations, not the main product**. Switch to the v11 selectors above.

The single-line check: in the saved HTML, does the substring `class="price--` appear? If yes, you're looking at a detail page. If only `class="number--` and `class="decimal--` appear, you're looking at the search page OR a detail page where you only fetched the recommendations.

### A note on user feedback that drove this section

The user, when seeing the first detail-page extraction report, said: "3人想要, 95浏览, 25元 包邮 可自提 成色: 几乎全新" — i.e. they were reading from the **visible browser** and noticed the parser had said `¥27.99 / 8人想要` (recommendation data) instead of `¥25 / 3人想要` (main product). That mismatch is what surfaced the entire "you must not use search-page classes on detail pages" rule. **When the user's eye contradicts the parser output, the parser is wrong and the live DOM is the source of truth** — same rule as on the search page, applies to the detail page too.

## Detail-page v12 (verified 2026-06-18): no scroll, 9s gap, image extraction

The v11 detail-page extraction worked but **assumed the page was scrolled** to trigger image lazy-load. That triggered 风控 signals on the 2nd run. v12 changed the contract:

### What changed in v12

1. **Do NOT scroll the detail page.** The HTML for title/price/want/seller info is fully rendered on load (the elements are above-the-fold by design). The "为你推荐" recommendations DO need scroll, but you don't need them — you only want the main product. So skipping scroll is **both safer (less 风控) AND faster (no 8-scroll loop).**

2. **Wait 9s between detail pages.** v11 used 5s; on a 4-keyword run this was tight. v12 raised to 9s for safety, with the comment "关键词之间间隔够长 (每商品 8-10 秒)".

3. **Image extraction: `fadeInImg` class + `bao/uploaded` src.** The main product images are rendered in `<img class="fadeInImg--DnykYtf4 fadeInImgActive--..." src="//img.alicdn.com/bao/uploaded/...">`. Both conditions are needed because:
   - `fadeInImg` alone matches system icons (信用等级, 担保交易, 装饰)
   - `bao/uploaded` alone matches product-promotion banners in the bottom area
   - Together they only match the main product's photo carousel.
   
   Verified on 4 real items: 2 / 4 / 7 / 2 images (matches what the user saw in the browser).

4. **Anchor-based slicing instead of nested regex.** v11 used `<span class="desc--X">(.*?)</span>` which breaks when the description has multiple `<span>` children. v12 uses **positional anchoring**: locate the `desc--` opening tag's position, then read forward until the next major class (`labels--` or `tips--` or `notLoginContainer--`). Same trick for `want--` block (read forward until `desc--` or `notLoginContainer--`).

5. **The script's online extraction is now a thin wrapper around `extract_detail_from_html`.** v12 saves HTML to disk, then calls the skill's extractor offline. No more 100-line page.evaluate JS that has to mirror the Python regex. One source of truth.

### The class-with-trailing-space gotcha

闲鱼 renders some classes with a trailing space: `class="price--OEWLbcxC "` (note the space before the closing quote). v11's regex `<div class="price--[A-Za-z0-9]+"[^>]*>` did NOT match this because `[A-Za-z0-9]+` doesn't include the trailing space. v12 uses `\s*` after the class name: `class="price--[A-Za-z0-9]+\s*"`. Same trick in the inner span regex.

### v12 scraper architecture (the working file)

`scripts/scrape_xianyu_top_n_detail.py` — login with cookies → go to homepage → auto-search via search input → grab top N detail page URLs → for each: load, wait 6s, save HTML, call `extract_detail_from_html`, append to list → write JSON.

Constants at the top: `KEYWORD`, `TOP_N`, `INTERVAL` — change those to re-run. Output: `dump/xianyu_top4_v12.json` + per-item `dump/detail_v12_N.html`.

**Verified on 拼豆挂件:** 4 items, all 13 fields + images captured cleanly. Hit rate: 100% on title / price / want / views / 5 seller labels / images. The only fields that can legitimately be 0/empty are `views` (some items have no view count yet, e.g. brand-new listings) and `images` (some text-only listings have no photos).

### The "为什么不滚动" rule (the user said it explicitly)

User correction 2026-06-18: *"(现在不是图像识别,应该不需要移动页面)"*. Yes — because we're extracting structured HTML attributes (`title` attribute of price/want/desc/row1-wrap-title), not running image recognition on the rendered page. The HTML for these fields is in the initial DOM load; no lazy-load is involved for the main product area. Scrolling the page:
- Adds 30+ seconds per page (8 scrolls × 1.5-2.5s delay)
- Triggers 风控 signals (abnormal navigation pattern)
- Has zero benefit for our extraction goals

Drop the scroll. Save the time. Save the account.

### 永远不关浏览器 (re-stated, hard rule)

Same as above — the v12 script ends with `await asyncio.Event().wait()` which hangs forever. The user closes the browser manually via Ctrl+C or by closing the window. Do NOT add `browser.close()` at the end of the script. The user is verifying data live in the browser window; if you close it, they have to ask you to re-run to verify, which is wasted network + 风控 risk.

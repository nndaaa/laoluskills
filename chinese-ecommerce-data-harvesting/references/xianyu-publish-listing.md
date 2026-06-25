# 闲鱼发布闲置(Write-side reference) — 2026-06-25

The complement to `playwright-xianyu-login-and-scrape.md` (read-side). Same stack — Playwright + Chromium headful on `DISPLAY=:0` + saved cookies + ToDesk observation — but going the other direction: fill the publish form, upload product photos, let the user click 发布 themselves.

**Verified end-to-end 2026-06-25 on a handcrafted 头层疯马皮 弯月胸包**: 9 photos uploaded, description (438/1500 chars) + title (auto-extracted from desc[0]) + price ¥358 + original price ¥498 + 包邮 + 宝贝所在地 蓝山上城 all filled, browser stayed open on the 发布 button for the user to click.

## Pre-flight — confirm before opening the browser

| Check | How | If fails |
|---|---|---|
| Cookie exists & recent | `ls -la ~/.hermes/projects/xianyu_research/cookies_xianyu.json` — within 7 days is safe; 8-30 days will *probably* work but expect 1 retry | If >30 days or absent → tell user to 扫码 (open browser headful, render QR, wait for them to scan) |
| DISPLAY available | `pgrep -a Xvfb` + `who \| grep $(whoami)` for `tty7 (:0)` | If headless only → use `xvfb-run -a` |
| Xauthority present | `ls -la ~/.Xauthority` | Set `export XAUTHORITY=/home/$USER/.Xauthority` |
| Photos exist | All `.jpg` in `listings/<sku>/`, sorted by filename (01_xxx, 02_xxx, ...) | Tell user which shots are missing |
| Display mode decided | Ask: "让我看着" (recommended per user profile — dark says "调试时不要关闭页面") vs "你先做,做完叫我" | Default: 让我看着. Set `KEEP_BROWSER_OPEN = True` |

**Don't skip pre-flight.** Each iteration of "browser opened → wrong state → close → reopen" costs 8-15 seconds and a wind-up. Three probes at the form-fill level cost ~30 seconds vs. one 3-second check up front.

## Login detection — the gotcha

**Wrong way (will give false negative on logged-in sessions):**

```python
# ❌ Nav bar always has a "登录" link — count > 2 even when logged in
if html.count("登录") > 2 and not has_avatar:
    print("needs QR scan")
```

The 闲鱼 nav bar's top-right contains a "登录" affordance as the my-account/login shortcut, which fires the count regardless of session state. Verified 2026-06-25 v1 mis-detected darksomee (logged in) as needing QR scan.

**Right way — use TWO signals:**

```python
# ✅ Avatar element + publish-form-specific field presence
nick_marker = await page.evaluate("""() => ({
    hasAvatar: !!document.querySelector(
        '[class*="avatar"], [class*="Avatar"], img[alt*="头像"]'
    ),
    bodyText: document.body.innerText
})""")
# A logged-in user on /publish will have BOTH avatar AND publish-form strings
publish_signals = ['成交额', '一口价', '宝贝所在地', '发布']  # any 2 of these
hits = sum(1 for s in publish_signals if s in nick_marker['bodyText'])
logged_in = nick_marker['hasAvatar'] and hits >= 2
```

If logged_in → proceed. Else → render QR, wait (use `wait_for_function` with `timeout=999999` to avoid the v1 60-second hang — see below), then re-check.

**Don't use `wait_for_function` with a finite timeout when waiting for the user to scan.** A 60s ceiling means: if the user is mid-ToDesk-connection or has the QR but didn't tap yet, the script exits before they finish, browser closes, all state lost. Use `timeout=999999` (effectively infinite) and rely on the user signaling back via 飞书. The "don't close the browser during verification" hard rule (from 2026-06-18) generalizes here too.

## Publish-page DOM (verified 2026-06-25, darksomee account)

| Field | Selector / locator | Notes |
|---|---|---|
| 宝贝图片 input | `input[type="file"]` (the **first** one on the page) | `.set_input_files([...])` accepts a list — uploads all at once |
| 宝贝描述 | `[contenteditable="true"]` div, class prefix `editor--` (e.g. `editor--MtHPS94K`), data-placeholder `描述一下宝贝的品牌型号、货品来源...` | **NOT a `<textarea>`** — Playwright's `locator('textarea')` will time out. Use `locator('[contenteditable]').nth(0)`. `.fill()` works because it dispatches a real input event on contenteditable in modern Playwright |
| 分类 (auto) | System fills this from uploaded images + description text. After uploading 9 photos of a 胸包, the field auto-populated as `男士包` + `款式=胸包` | Don't try to set manually — let the system do it |
| 价格 input | `input[placeholder="0.00"][type="text"]` | **There are 2** of these — first is 价格 (your asking price), second is 原价 (optional strikethrough). Always fill `nth(0)` for price, `nth(1)` for original |
| 原价 | same selector, `nth(1)` | Optional. Setting it makes the listing show "原价¥X → 现价¥Y" which increases perceived value. Use ~1.4x of asking price (e.g. ¥498 vs ¥358 = 28% off) |
| 发货方式 | Radio group: 包邮 / 按距离计费 / 一口价 / 无需邮寄 / 支持自提 (toggle) | Default: 包邮. Already selected on page load. Don't change unless user asks |
| 宝贝所在地 | Input with placeholder `搜索地点`; the page pre-fills it from user profile (verified: 蓝山上城 appeared without me touching it) | If wrong, type a city name and pick from dropdown |
| 发布按钮 | `<button>` with text `=== '发布'` | **Don't click yourself.** See the hard rule below |

**No standalone 标题 input.** The title is extracted from the description's **first line**. Put the title text on line 1 of your description:

```
手作头层疯马皮胸包 弯月大开口 4天手缝     ← becomes the 标题
                                                (≤30 chars works best for SEO)
【材质】 ...                                  ← rest of description
```

The description's character counter shows `438/1500` etc. — keep below 1500 to avoid truncation. Empirically the smart descriptions for handcrafted goods are 350-500 chars.

## Image upload order — the gotcha

**Files uploaded via `set_input_files` get re-ordered by the 闲鱼 server.** Confirmed 2026-06-25: I sent 9 files in order `01_overall.jpg → 02_wearing_157cm.jpg → ... → 09_crescent_shape.jpg`. The page displayed them in a different order — apparently hashed by filename or server-side process. The first displayed image became a non-overall photo (probably the 157cm wearing shot which I wanted as #2).

**Two strategies, pick based on user's patience:**

1. **Accept and edit later.** Upload all, fill the form, stop before 发布. User opens ToDesk, manually drags the thumbnails into the desired order in the browser, then clicks 发布. Fastest path to live. Recommended when user is at the keyboard.

2. **Pre-encode order in filenames** — the server reordering appeared non-deterministic and inconsistent across uploads in this session; there's no stable filename-based trick I found. If order matters and the user is hands-off, recommend (1).

**Recommended order for handcrafted bags (general):**
- `01_overall.jpg` — full bag, neutral background, clean light
- `02_wearing_<height>cm.jpg` — person carrying it (height matters: e.g. 157cm frames the "fits small users" pitch)
- `03_front_pockets.jpg` — internal compartments (functional proof)
- `04_<material>_lining.jpg` — material close-up (麂皮翻毛 etc.)
- `05_stitching_<hardware>.jpg` — seams + hardware brand (YKK etc.)
- `06_<hardware>.jpg` — buckles/feet/rivets close-up
- `07_main_compartment.jpg` — main pocket opening (capacity proof)
- `08_side_view.jpg` — silhouette from side
- `09_shape.jpg` — overall silhouette from front (the "包型" shot)

Don't go over 9 photos — 闲鱼 caps at 9. Spare the count for genuine differentiators.

## The "stop before 发布" hard rule

**Never click 发布 yourself.** Three reasons:
1. **Real-money commitment.** The user wants to eyeball the whole listing one more time before it's live.
2. **ToDesk dependency.** You're seeing the page via `vision_analyze` screenshots; the user is seeing it directly. They will catch things you missed (typos, wrong photo, missing detail).
3. **风控.** Rapid-fire publish attempts in a single session may trigger platform rate limiting. Letting the user click introduces a natural human delay.

After all fields are filled:
```python
# Highlight the button visually so the user can spot it immediately
await page.evaluate("""() => {
    const btn = [...document.querySelectorAll('button')]
        .find(b => b.innerText.trim() === '发布');
    if (btn) {
        btn.scrollIntoView({behavior: 'instant', block: 'center'});
        btn.style.outline = '4px solid red';
    }
}""")
# Take final screenshot
await page.screenshot(path=str(LOG_DIR / "final.png"), full_page=True)
# Keep browser open indefinitely — user signals back via 飞书
await asyncio.sleep(1800)  # 30 min ceiling, then auto-close
```

User's response options:
- "OK 发了" → they clicked it manually, you do post-publish cleanup (check the listing URL, save it)
- "改 XXX" → you edit the field, take new screenshot, wait again
- "停" → you close the browser, leave the form as-is (user will come back)

## Working scripts (canonical, in this skill)

- `scripts/post_xianyu_listing.py` — the fill_form.py pattern, hardened: probes DOM for the contenteditable div (not textarea), uses the two-signal login check, accepts image list and field dicts as args.

## Template: copy-and-customize for new listings

For a new listing, the agent should produce a config block like:

```python
LISTING_CONFIG = {
    "img_dir": "~/.hermes/projects/xianyu_research/listings/<sku>",
    "title": "<≤30 chars, becomes desc[0]>",
    "description_full": "<350-500 chars, starts with title line>",
    "price": "<integer as string>",
    "original_price": "<1.4x price, or empty>",
    "tags": "<optional; system auto-fills from images, usually no need>",
}
```

Then call `post_xianyu_listing.fill(LISTING_CONFIG)`. The script handles everything else.

## Verified worked example (2026-06-25)

**Subject:** Hand-crafted 头层疯马皮 弯月胸包, 4-day handmade, ¥358.

**Final state on publish page:**
- 9 photos uploaded (out of order — user accepted and dragged in ToDesk)
- Description 438/1500 chars, first line = title
- Price ¥358, original ¥498 (划线)
- 系统智能识别分类: 男士包 + 款式=胸包
- 发货: 包邮 (default)
- 宝贝所在地: 蓝山上城 (default)
- Browser stayed open on 发布 button for user to click

**Total runtime:** ~5 minutes including 12s upload wait + 3 失败 iteration loops (textarea lookup → contenteditable lookup → original price selector).

## Pitfalls

- **Don't assume the description is a `<textarea>`.** It's a contenteditable div. `locator('textarea').fill(...)` will time out after 30s every time.
- **Don't use `html.count("登录") > N` for login detection.** See the gotcha above.
- **Don't set `KEEP_BROWSER_OPEN = False` until the user signals they're done with ToDesk.** The original v11 hang pattern came from auto-closing during observation.
- **Don't click 发布 yourself.** Hard rule. The user clicks.
- **Don't paste raw URLs to images or commands in the 飞书 reply.** Privacy rule from user profile. Send screenshots via `MEDIA:/abs/path` if needed.
- **Don't iterate on 4+ scraper versions in the working dir.** v1→v2→v3→v4→v5 cleanup rule from 2026-06-18 still applies. When you have a working fill_form.py, snapshot it to the skill's `scripts/` directory.

## Companion scripts

- `scripts/post_xianyu_listing.py` — the working fill_form.py pattern, hardened against the gotchas above.
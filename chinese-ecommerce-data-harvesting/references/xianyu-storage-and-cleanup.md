# 闲鱼抓取数据存储层 — Why SQLite, How It Evolved (2026-06-18 v12+)

The first 8 versions of the 闲鱼 scraper all wrote JSON files to disk — one JSON per run, or one JSON per keyword, accumulating into `data/xianyu_real_v5.json`, `v6.json`, `v7.json`, `data/xianyu_real_all.json`, etc. By 2026-06-18 the user explicitly asked: **"脚本里历史html有没有做清理,如果不清理,会占用月来越多的空间,第二,现在保存的是什么格式的数据,是json还是sqllite,能支持多久和多大的数据量"** — three questions, all pointing at the same problem: **the working directory was growing unbounded, and there was no clear answer for how much data was sustainable**.

This doc captures the storage decision and the supporting design rules.

## The three questions the user asked, and the answers

| Question | Answer | Source |
|---|---|---|
| Does the script clean up historical HTML? | **No, it didn't.** v12 added `cleanup_old_htmls(keep_days=3)` and `cleanup_old_logs(keep_days=7)`, plus `delete_html_after_import=True` so each batch's HTML is deleted the moment its data lands in SQLite. | xianyu_db.py |
| What format is the data stored in? | **v1-v11: JSON files.** **v12+: SQLite (`data/xianyu.db`).** Single file, indexed, queryable. | xianyu_db.py |
| How much data and how long can it sustain? | **JSON:** ~1KB per row, no indexing, files accumulate linearly (~2.5MB/day for 4 keywords). **SQLite:** ~1KB per row, indexed, queries stay <10ms up to 100k+ rows; theoretical limit is 281TB per database. | SQLite docs |

## Why SQLite, not JSON, for this kind of data

JSON works for **"I have 4 items and want to print them"**. It stops working the moment you want any of these:

- **Re-running against the same items to update want/views counts** (the v12 use case — re-scrape the same 拼豆挂件 keywords next week, see if want count went up)
- **Cross-keyword queries** ("show me all 拼豆 items with want > 50 across every keyword I've ever scraped")
- **Time-series** ("how did 拼豆's median price change over the last 4 weeks")
- **Deduplication** ("give me each unique item once, even if it appeared in 3 different keyword searches")
- **Long-term storage without file proliferation** (v11 left 12 JSON files in `data/`)

SQLite gives you all of these for free. It also has these properties that make it the right default for "personal Linux box, single user, scraping scale":

- **Zero-config**: no server, no daemon, no auth. Single `.db` file you can `cp` or `sqlite3 data/xianyu.db` to inspect.
- **Crash-safe**: writes are transactional. If the script crashes mid-scrape, the DB is consistent.
- **Compressed-ish**: SQLite stores integers as 1-8 bytes, strings with deduplication. For the 闲鱼 schema, 100k rows fits in ~10MB.
- **Queryable from anywhere**: Python (`sqlite3` stdlib), the `sqlite3` CLI, Jupyter (`%sql` magic), DuckDB (read-only), even `pandas.read_sql`.

**Use JSON only when**: you have a tiny number of items (<100), you never need to query across them, and you're handing the data to a human who'll read the file once.

## The v12 storage design (concrete)

Schema: `scripts/xianyu_db.py`:

```sql
CREATE TABLE xianyu_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT UNIQUE NOT NULL,        -- 闲鱼商品 id (从 URL 提取)
    keyword TEXT,                         -- 搜索关键词
    captured_at TEXT NOT NULL,            -- 抓取时间 ISO
    title TEXT, price TEXT,
    want INTEGER DEFAULT 0, views INTEGER DEFAULT 0,
    shipping_tags TEXT,                   -- JSON 数组字符串
    seller_nick TEXT, seller_level TEXT,
    seller_location TEXT, seller_last_seen TEXT, seller_age TEXT,
    seller_sold_count TEXT, seller_positive_rate TEXT,
    description TEXT,                     -- | 分隔的多行
    images TEXT,                          -- JSON 数组字符串
    image_count INTEGER DEFAULT 0,
    url TEXT, raw_html_path TEXT
)
CREATE INDEX idx_keyword ON xianyu_items(keyword)
CREATE INDEX idx_captured ON xianyu_items(captured_at)
CREATE INDEX idx_want ON xianyu_items(want)
CREATE INDEX idx_price_num ON xianyu_items(CAST(price AS REAL))
```

**Key design choices:**

1. **`item_id` is UNIQUE.** Re-running the same scrape upserts on conflict — `want`/`views`/`price` get updated, `captured_at` gets refreshed, no duplicates. This is the answer to "how do I track changes over time without keeping 50 copies of the same item".

2. **`price` is TEXT, not REAL.** Because the data is messy: `¥19.9 - 39.9` (range), `¥25`, `¥27.99`, `¥价格联系卖家` (no number). Storing as text + a derived numeric index `CAST(price AS REAL)` lets you range-query on what IS numeric while preserving the original messy string for display.

3. **`shipping_tags` and `images` are JSON strings in TEXT columns.** SQLite has a JSON1 extension but for this use case, storing as text is fine — we never query inside the JSON, we just round-trip the list. If you start querying "show me all items with image_count > 5", add a real `image_count INTEGER` column (done) and index it.

4. **`raw_html_path` is set to NULL after import.** This signals "HTML was here, but it's been deleted". If you want to keep some HTMLs (e.g. the latest N for debugging), keep this column populated and only delete files that aren't referenced.

5. **No separate `images` table.** Items have 1-7 images, max. A normalized schema would have `xianyu_item_images(item_id, url, position)`. For ≤7 images per item, denormalized is fine and the query is simpler. **If you start scraping items with 50+ images each** (some 闲鱼 listings do this), revisit this.

## The cleanup contract (v12)

Three cleanup hooks, called at the end of each scrape:

```python
# 1. Delete the current batch's HTML (data is now in DB)
n = save_items(items, keyword, conn, delete_html_after=True)
# This removes dump/detail_v12_*.html for items in the current batch

# 2. Clean up old HTML from prior batches (anything not deleted in step 1)
n_html = cleanup_old_htmls(DUMP_DIR, keep_days=3)
# This removes dump/*.html older than 3 days

# 3. Clean up old logs
n_logs = cleanup_old_logs(Path("logs"), keep_days=7)
# This removes logs/*.log older than 7 days
```

**Why 3 days for HTML?** Long enough that the user can still go back and look at a problematic extraction if it turns out the data was wrong. Short enough that the working directory doesn't grow. Adjust based on how often the user asks "show me the raw HTML for that weird item".

**Why 7 days for logs?** Same idea, but logs are smaller (~5KB each vs ~300KB for HTML), and they help debug intermittent issues that might take a few days to surface. 7 days = 1 week of run history, which is usually enough.

## The "single source of truth" pattern (architecture decision)

Before v12, the scraper script had a 100-line `page.evaluate()` JS block that mirrored the Python regex in `xianyu_detail_extractor.py`. Every time the extractor regex changed, you had to remember to update the JS too. **Two sources of truth for one extraction rule**.

v12 fixed this by making the script's extraction path a thin wrapper:

```python
# WRONG (v11):
item = await page.evaluate("""() => { /* 100 lines of JS regex */ }""")

# RIGHT (v12):
html = await page.content()
data = extract_detail_from_html(html)  # The skill's Python function
item = {
    "title": data["title"],
    "price": data["price"],
    # ... 12 more fields, just renaming
}
```

Now there's **one** extraction rule. The script doesn't know how to extract; it just calls the extractor. The extractor is the single source of truth, has a `--test` self-check, and is unit-testable offline.

**Rule for any future scraper**: the network-fetching script should be a thin caller of the offline extractor. The extractor should have self-tests. The script should not duplicate extraction logic.

This pattern works because:
- The HTML is **fully rendered on page load** (v12's "no scroll" insight). So `page.content()` gives you the same string whether you extract online or offline.
- The extractor is **pure**: input is a string, output is a dict. No I/O, no async. Testable in milliseconds.
- The script's only job is: navigate, wait, save HTML, call extractor, persist result.

If you ever need to re-extract from saved HTMLs (e.g. the extractor regex got an update and you want to refresh all past data), you can do it offline with zero network:

```bash
# Example: re-extract all 100 saved HTMLs with the new regex
for f in dump/*.html; do
    python3 -c "from xianyu_detail_extractor import *; print(extract_detail_from_html(open('$f').read()))"
done
```

## Operations the user can do with this storage

```bash
# 1. What's in the DB right now?
python3 ~/.hermes/skills/devops/chinese-ecommerce-data-harvesting/scripts/xianyu_db.py
# → prints total / keywords / unique sellers / DB size / want TOP 5

# 2. Run a custom query
sqlite3 data/xianyu.db "SELECT title, want, price FROM xianyu_items WHERE want > 100"

# 3. See all items from one keyword
sqlite3 data/xianyu.db "SELECT * FROM xianyu_items WHERE keyword = '拼豆挂件' ORDER BY want DESC"

# 4. Re-extract a saved HTML (after updating the extractor regex)
python3 -c "from xianyu_detail_extractor import extract_detail_from_html; import json; print(json.dumps(extract_detail_from_html(open('dump/detail_v12_2.html').read()), ensure_ascii=False, indent=2))"

# 5. Backup the DB (one file)
cp data/xianyu.db /path/to/backup-$(date +%Y%m%d).db

# 6. See what the most active sellers are
sqlite3 data/xianyu.db "SELECT seller_nick, COUNT(*) as items, MAX(captured_at) as last_seen FROM xianyu_items GROUP BY seller_nick ORDER BY items DESC LIMIT 10"
```

## When NOT to use SQLite (rare, but real)

- **You only have 4-5 items, all from one run, and you want a portable file to email.** JSON wins.
- **You need to share the data with someone who can't run sqlite3.** JSON wins.
- **The data has variable schema per item** (e.g. some items have a `color` field, others don't). JSON's natural flexibility beats SQLite's rigid schema. For 闲鱼, the schema is fixed, so SQLite is fine.
- **The data volume is < 100 items and you never re-query.** JSON wins on simplicity.

For everything else: SQLite, with `xianyu_db.py` as the starter.

## The user's role in the design decision

The user asked the three questions in one message, in order: cleanup, format, sustainability. They didn't ask "should I add cleanup" or "what's the right DB"; they asked the questions that matter operationally. **The right response is to answer all three, propose a concrete stack (SQLite + auto-cleanup + auto-delete on import), and ship it in one turn.** The user is technical enough to verify; the time to deliberate is short.

When the user asks an architectural question like this, **don't ask back "do you want JSON or SQLite?" — pick the right one and explain why**. The user is technical; they want the agent to make the call and ship.

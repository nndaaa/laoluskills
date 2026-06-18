#!/usr/bin/env python3
"""v12 - 前 4 个商品详情页抓取
- 不滚动页面(避免反爬)
- 关键词之间间隔 8-10 秒
- 永远不关浏览器
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from playwright.async_api import async_playwright

# 引入同包内的 extractor,保证脚本和 skill 选择器一致
sys.path.insert(0, str(Path(__file__).parent / ".hermes/skills/devops/chinese-ecommerce-data-harvesting/scripts"))
try:
    from xianyu_detail_extractor import extract_detail_from_html
    from xianyu_db import init_db, save_items, cleanup_old_htmls, cleanup_old_logs, stats
except ImportError:
    # 兜底: 用项目根目录的 skill 路径
    skill_path = Path.home() / ".hermes/skills/devops/chinese-ecommerce-data-harvesting/scripts"
    if skill_path.exists():
        sys.path.insert(0, str(skill_path))
        from xianyu_detail_extractor import extract_detail_from_html
        from xianyu_db import init_db, save_items, cleanup_old_htmls, cleanup_old_logs, stats

# 配置
KEEP_HTML_DAYS = 3   # HTML 文件保留天数(数据入库后,这个天数前的 HTML 自动删)
KEEP_LOG_DAYS = 7    # 日志保留天数
SAVE_HTML_AFTER_IMPORT = True  # 入库后立即删当前批次的 HTML
KEEP_BROWSER_OPEN = False  # 跑完后是否留页面给 ToDesk 看(默认关,避免进程不退出)

KEYWORD = "拼豆套装"
TOP_N = 4  # 前 4 个
INTERVAL = 9  # 间隔秒
DUMP_DIR = Path("dump")
DUMP_DIR.mkdir(exist_ok=True)
COOKIES_FILE = Path("cookies_xianyu.json")


async def main():
    with open(COOKIES_FILE) as f:
        cookies = json.load(f)
    print(f"✅ 加载 {len(cookies)} 个 cookie", flush=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        )
        await ctx.add_cookies(cookies)
        page = await ctx.new_page()

        # 1. 首页
        print("🌐 打开闲鱼首页 ...", flush=True)
        await page.goto("https://www.goofish.com/", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)

        # 2. 搜
        print(f"🔍 搜: {KEYWORD}", flush=True)
        input_el = await page.query_selector('input[class*="search"]')
        if not input_el:
            print("❌ 找不到搜索框", flush=True)
            await asyncio.Event().wait()
            return
        await input_el.click()
        await input_el.fill("")
        await input_el.type(KEYWORD, delay=80)
        await input_el.press("Enter")
        await page.wait_for_timeout(8000)
        print(f"📍 搜索 URL: {page.url}", flush=True)

        # 3. 存搜索页 HTML (调试用)
        search_html = await page.content()
        (DUMP_DIR / f"{KEYWORD}_search.html").write_text(search_html)
        print(f"💾 搜索页 HTML 已存", flush=True)

        # 4. 找前 4 个商品链接
        links = await page.evaluate(
            """() => {
            const arr = [];
            document.querySelectorAll('a[href*="/item?id="]').forEach(a => {
                if (arr.length < 4) arr.push(a.href);
            });
            return arr;
        }"""
        )

        if not links:
            print("❌ 找不到商品链接", flush=True)
            await asyncio.Event().wait()
            return

        print(f"✅ 找到 {len(links)} 个商品链接,逐个抓详情 ...\n", flush=True)

        all_items = []

        for idx, link in enumerate(links[:TOP_N], 1):
            print(f"\n{'='*60}", flush=True)
            print(f"📄 [{idx}/{TOP_N}] 抓详情: {link}", flush=True)
            print(f"{'='*60}", flush=True)

            await page.goto(link, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(6000)
            # 不滚动!

            # 存详情页 HTML
            detail_html = await page.content()
            detail_file = DUMP_DIR / f"detail_v12_{idx}.html"
            detail_file.write_text(detail_html)
            print(f"💾 HTML: {detail_file} ({len(detail_html)} 字符)", flush=True)

            # 抓所有字段 - 调 skill 里的 extractor (HTML 已存到磁盘)
            data = extract_detail_from_html(detail_html)
            item = {
                "_idx": idx,  # 给 db 用,确定 HTML 路径
                "url": link,
                "title": data["title"],
                "price": data["price"],
                "want": data["want"],
                "views": data["views"],
                "posts": data["shipping_tags"],
                "seller": data["seller_nick"],
                "location": data["seller_location"],
                "last_visit": data["seller_last_seen"],
                "register_age": data["seller_age"],
                "sold_count": data["seller_sold_count"],
                "good_rate": data["seller_positive_rate"],
                "desc": data["desc"],
                "images": data["images"],
            }

            all_items.append(item)

            print(f"\n📌 标题:    {item['title'][:80]}", flush=True)
            print(f"💰 价格:    ¥{item['price']}", flush=True)
            print(f"❤️  想要:    {item['want']} 人", flush=True)
            print(f"👁  浏览:    {item['views']}", flush=True)
            print(f"📦 邮/提:    {item['posts']}", flush=True)
            print(f"👤 卖家:    {item['seller']}", flush=True)
            print(f"📍 地点:    {item['location']}", flush=True)
            print(f"⏰ 上次:    {item['last_visit']}", flush=True)
            print(f"📅 注册:    {item['register_age']}", flush=True)
            print(f"📦 成交:    {item['sold_count']}", flush=True)
            print(f"⭐ 好评率:  {item['good_rate']}", flush=True)
            print(f"🖼  图片数:  {len(item['images'])}", flush=True)

            # 间隔
            if idx < TOP_N:
                print(f"\n⏳ 等 {INTERVAL} 秒再抓下一个...", flush=True)
                await page.wait_for_timeout(INTERVAL * 1000)

        # 存到 SQLite (替换旧的 JSON 写入)
        conn = init_db()
        n = save_items(all_items, keyword=KEYWORD, conn=conn,
                       delete_html_after=SAVE_HTML_AFTER_IMPORT)
        conn.close()

        # 清理历史 HTML/日志
        n_html = cleanup_old_htmls(DUMP_DIR, keep_days=KEEP_HTML_DAYS)
        n_logs = cleanup_old_logs(Path("logs"), keep_days=KEEP_LOG_DAYS)
        if n_html or n_logs:
            print(f"🧹 历史清理: {n_html} 个 HTML, {n_logs} 个日志", flush=True)

        # 同时存一份最近批次 JSON(调试用,下次运行会被覆盖)
        output = DUMP_DIR / "xianyu_top4_v12.json"
        output.write_text(json.dumps(all_items, ensure_ascii=False, indent=2))

        print(f"\n\n💾 已写入 SQLite: data/xianyu.db ({n} 条)", flush=True)
        print(f"📊 共 {len(all_items)} 个商品", flush=True)

        # 显示数据库统计
        conn = init_db()
        s = stats(conn)
        print(f"\n📈 数据库统计: 总 {s['total']} 条 | {s['db_size_mb']} MB | 关键词 {s['keywords']}", flush=True)
        conn.close()

        print(f"\n{'='*60}", flush=True)
        if KEEP_BROWSER_OPEN:
            print(f"🔵 浏览器留 5 分钟 (KEEP_BROWSER_OPEN=True)", flush=True)
            await page.wait_for_timeout(300_000)
        else:
            print(f"✅ 全部完成,关浏览器退出", flush=True)

        await browser.close()


asyncio.run(main())
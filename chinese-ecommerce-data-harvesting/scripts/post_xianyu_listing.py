"""
post_xianyu_listing.py — 闲鱼发布闲置填充脚本 (2026-06-25, v5 pattern)

填字段顺序: 上传图片 → 描述(contenteditable div) → 价格 → 原价
不停在"发布"按钮前,让用户自己点。

用法:
    from post_xianyu_listing import fill
    fill({
        "img_dir": "/path/to/listings/<sku>",
        "title": "手作头层疯马皮胸包 弯月大开口 4天手缝",
        "description_full": "<350-500 chars, first line = title>",
        "price": "358",
        "original_price": "498",
        "cookies_file": "/path/to/cookies_xianyu.json",  # optional, defaults below
    })

或者直接运行:
    python3 post_xianyu_listing.py
    (会从环境变量读取 CONFIG_PATH 指向的 JSON)

Verified 2026-06-25 on darksomee account, handcrafted 疯马皮 弯月胸包, ¥358.
"""

import asyncio, os, sys, json
from pathlib import Path
from playwright.async_api import async_playwright

DEFAULT_COOKIES = Path.home() / ".hermes/projects/xianyu_research/cookies_xianyu.json"
PUBLISH_URL = "https://www.goofish.com/publish"

# 登录检测 — 用双信号(头像 + 发布页字段)
LOGIN_CHECK_JS = """() => {
    const hasAvatar = !!document.querySelector('[class*="avatar"], [class*="Avatar"], img[alt*="头像"]');
    const bodyText = document.body.innerText;
    const signals = ['成交额', '一口价', '宝贝所在地', '发布'];
    const hits = signals.filter(s => bodyText.includes(s)).length;
    return { hasAvatar, hits, logged_in: hasAvatar && hits >= 2 };
}"""

# 探测 DOM 结构(contenteditable vs textarea)
PROBE_JS = """() => {
    const result = { textareas: [], contenteditable: [] };
    document.querySelectorAll('textarea').forEach((t, i) => {
        if (t.offsetParent !== null) {
            result.textareas.push({ i, placeholder: t.placeholder });
        }
    });
    document.querySelectorAll('[contenteditable="true"]').forEach((c, i) => {
        if (c.offsetParent !== null) {
            result.contenteditable.push({
                i,
                placeholder: c.getAttribute('data-placeholder') || '',
                tag: c.tagName,
                cls: c.className.slice(0, 60)
            });
        }
    });
    return result;
}"""

# 高亮发布按钮
HIGHLIGHT_JS = """() => {
    const btn = [...document.querySelectorAll('button')]
        .find(b => b.innerText.trim() === '发布');
    if (btn) {
        btn.scrollIntoView({behavior: 'instant', block: 'center'});
        btn.style.outline = '4px solid red';
        return true;
    }
    return false;
}"""


async def fill(config: dict, headless: bool = False):
    """Fill the publish form. Stays on 发布 button, does not click it."""
    img_dir = Path(config["img_dir"]).expanduser()
    img_files = sorted([f for f in img_dir.glob("*.jpg") if "screenshot" not in str(f)])
    log_dir = img_dir / "screenshots"
    log_dir.mkdir(exist_ok=True)
    cookies_file = Path(config.get("cookies_file", DEFAULT_COOKIES)).expanduser()
    title = config["title"]
    description_full = config["description_full"]
    price = str(config["price"])
    original_price = str(config.get("original_price", ""))

    print(f"📦 {len(img_files)} 张图")
    print(f"📝 标题(将放描述第一行): {title}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0"
        )
        if cookies_file.exists():
            cookies = json.loads(cookies_file.read_text())
            await context.add_cookies(cookies)
            print(f"✅ 加载 {len(cookies)} cookie")

        page = await context.new_page()
        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # 登录检查 — 双信号
        login_state = await page.evaluate(LOGIN_CHECK_JS)
        print(f"🔍 登录状态: avatar={login_state['hasAvatar']}, signals={login_state['hits']}/4")
        if not login_state["logged_in"]:
            print("❌ 未登录 — cookie 失效,需要用户扫码")
            return False

        # 探测描述框
        probe = await page.evaluate(PROBE_JS)
        print(f"🔍 描述框探测: textareas={len(probe['textareas'])}, contenteditable={len(probe['contenteditable'])}")
        if probe['contenteditable']:
            desc_locator = page.locator('[contenteditable="true"]').first
        elif probe['textareas']:
            desc_locator = page.locator('textarea').first
        else:
            print("❌ 没找到描述框")
            return False

        # 1. 上传图片
        print(f"\n>>> [1/3] 上传 {len(img_files)} 张图")
        file_input = page.locator('input[type="file"]').first
        await file_input.set_input_files([str(f) for f in img_files])
        print("  ⏳ 等上传完成...")
        await asyncio.sleep(12)
        await page.screenshot(path=str(log_dir / "01_uploaded.png"), full_page=True)

        # 2. 填描述(标题放第一行)
        print(">>> [2/3] 填描述")
        full_desc = f"{title}\n\n{description_full}"
        await desc_locator.fill(full_desc)
        print(f"  ✅ {len(full_desc)} 字")

        # 3. 填价格
        print(">>> [3/3] 填价格")
        price_inputs = page.locator('input[placeholder="0.00"]')
        cnt = await price_inputs.count()
        if cnt >= 1:
            await price_inputs.nth(0).fill(price)
            print(f"  ✅ 价格: ¥{price}")
        if cnt >= 2 and original_price:
            await price_inputs.nth(1).fill(original_price)
            print(f"  ✅ 原价: ¥{original_price}(划线)")

        # 4. 高亮发布按钮 + 截图
        await asyncio.sleep(2)
        await page.evaluate(HIGHLIGHT_JS)
        await asyncio.sleep(1)
        await page.screenshot(path=str(log_dir / "final.png"), full_page=True)
        print(f"\n📸 {log_dir}/final.png ← 看这张")

        # 5. 状态
        status = {
            "title": title,
            "description_len": len(full_desc),
            "price": price,
            "original_price": original_price,
            "images_uploaded": len(img_files),
            "page_state": "ready_to_publish",
            "next_action": "user_clicks_publish"
        }
        (img_dir / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2))

        print(f"\n⏸️  浏览器保持开着,等用户在飞书回 'OK 发了' / '改 XXX' / '停'")
        print(f"   30 分钟后自动关闭")

        await asyncio.sleep(1800)  # 30 min ceiling
        await browser.close()
        return True


if __name__ == "__main__":
    config_path = os.environ.get("CONFIG_PATH")
    if not config_path:
        # Demo config for testing
        config = {
            "img_dir": str(Path.home() / ".hermes/projects/xianyu_research/listings/chest_bag_v1"),
            "title": "手作头层疯马皮胸包 弯月大开口 4天手缝",
            "description_full": """【材质】 整包头层疯马皮(植鞣革),深巧克棕。皮面会随使用养出油润包浆,有自然划痕变色,越用越有味道。

【工艺】 4天纯手缝,双线加粗,针脚沿包边一圈走齐。

【五金】 YKK铜拉链 + 实心黄铜龙虾扣/D环/5孔调节扣/铜铆钉。

【包型】 弯月形设计,主仓大开口,小个子也能背。

【结构】 主仓大开口 / 前仓3卡位+1独立拉链袋 / 内里麂皮翻毛 / 肩带可拆卸。

【瑕疵说明】 手工制作,皮面有自然毛孔纹理和色差,介意者慎拍。

【关于我】 自己做的手工皮具,一周只做1-2只,买一只少一只。""",
            "price": "358",
            "original_price": "498",
        }
    else:
        config = json.loads(Path(config_path).read_text())

    asyncio.run(fill(config))
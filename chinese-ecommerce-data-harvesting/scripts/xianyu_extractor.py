#!/usr/bin/env python3
"""闲鱼 商品卡片提取器 (v10, verified 2026-06-18)

从 Playwright 渲染后的闲鱼搜索结果页提取商品卡片 (标题/价格/想要数)。
- 卡片容器: [class*="feeds-content"] (4 列行容器,30+ 卡片/页 after lazy scroll)
- 标题: [class*="row1-wrap-title"] 的 title 属性 (不是 main-title span)
- 价格: [class*="price-wrap"] 的 title 属性;若无,拼接 number+decimal (跳过 sign 避免 ¥¥)
- 想要数: [class*="text--MaM9Cmdn"][title*="人想要"] 的 title 属性,正则取数字

输出: 列表 [{title, price, want}, ...]

两种用法:
1. 离线 (推荐 - 调试快,无网络风险):
   html = Path("dump/拼豆挂件_v10.html").read_text()
   items = extract_from_html(html)

2. 在线 (在 Playwright page 里):
   items = await extract_from_page(page)
"""
import re
from pathlib import Path
from typing import List, Dict, Optional


def extract_from_html(html: str) -> List[Dict]:
    """从本地 HTML 提取商品卡片 (离线,用于调试)

    Args:
        html: 完整 HTML 字符串
    Returns:
        [{title, price, want}, ...] - 找不到的字段就是空字符串或 0
    """
    items = []
    # 切片: [class*="feeds-content"] 容器
    pattern = r'<div class="feeds-content--[A-Za-z0-9]+"[^>]*>(.*?)(?=<div class="feeds-content|<div class="feeds-page|<footer|$)'
    cards = re.findall(pattern, html, re.DOTALL)

    for i, card in enumerate(cards, 1):
        # 标题: row1-wrap-title 的 title 属性
        title_match = re.search(
            r'<div class="row1-wrap-title--[A-Za-z0-9]+"[^>]*?title="([^"]*)"',
            card,
        )
        title = title_match.group(1) if title_match else ""

        # 备用: main-title span 的文本 (去掉内部 <img> 标签)
        if not title:
            mt = re.search(
                r'<span class="main-title--[A-Za-z0-9]+"[^>]*?>(.*?)</span>',
                card,
                re.DOTALL,
            )
            if mt:
                title = re.sub(r"<[^>]+>", "", mt.group(1)).strip()

        # 价格: 优先 price-wrap 的 title 属性
        pw_title = re.search(
            r'<div class="price-wrap--[A-Za-z0-9]+"[^>]*?title="([^"]*)"',
            card,
        )
        if pw_title:
            price = pw_title.group(1)
        else:
            # 备用: 拼接 number + decimal (跳过 sign 避免 ¥¥)
            num = re.search(
                r'<span class="number--[A-Za-z0-9]+">([^<]+)</span>',
                card,
            )
            dec = re.search(
                r'<span class="decimal--[A-Za-z0-9]+">([^<]+)</span>',
                card,
            )
            price = ""
            if num:
                price = num.group(1).strip()
            if dec:
                price += dec.group(1).strip()

        # 想要数: text--MaM9Cmdn 的 title 属性
        want_match = re.search(
            r'<div class="text--MaM9Cmdn"[^>]*?title="(\d+)人想要"',
            card,
        )
        want = int(want_match.group(1)) if want_match else 0

        items.append({"index": i, "title": title, "price": price, "want": want})

    return items


async def extract_from_page(page) -> List[Dict]:
    """从 Playwright page 提取商品卡片 (在线)

    跟 extract_from_html 等价,但走 page.evaluate 拿 DOM 而不是从 HTML 字符串解析。
    在 dump 本地 HTML 后,优先用 extract_from_html 离线调试。
    """
    return await page.evaluate(
        """
        () => {
            const items = [];
            const cards = document.querySelectorAll('[class*="feeds-content"]');
            for (let i = 0; i < cards.length; i++) {
                const card = cards[i];
                const titleEl = card.querySelector('[class*="row1-wrap-title"]');
                const title = titleEl ? (titleEl.getAttribute('title') || '') : '';
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
        """
    )


# --- 自我测试 ---
if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("用法: python3 xianyu_extractor.py <dump/xxx.html>")
        print("      python3 xianyu_extractor.py --test")
        sys.exit(1)

    if sys.argv[1] == "--test":
        # 用一段人造 HTML 测试正则
        sample = """
        <div class="feeds-content--abcd">
            <div class="row1-wrap-title--xx" title="Hello Kitty 拼豆挂件 ¥25.9 包邮">
                <span class="main-title--xx">Hello Kitty 拼豆挂件 ¥25.9 包邮</span>
            </div>
            <div class="row3-wrap-price--yy">
                <div class="price-wrap--zz" title="¥25">
                    <span class="sign--x6u">¥</span>
                    <span class="number--Nk">25</span>
                </div>
                <div class="text--MaM9Cmdn" title="3人想要">3人想要</div>
            </div>
        </div>
        <div class="feeds-content--efgh">
            <div class="row1-wrap-title--aa" title="[预售]金铲铲之战 拼豆挂件">
                <span class="main-title--aa">[预售]金铲铲之战 拼豆挂件</span>
            </div>
            <div class="price-wrap--bb">
                <span class="sign--x6u">¥</span>
                <span class="number--Nk">39</span>
                <span class="decimal--ls">.99</span>
            </div>
            <div class="text--MaM9Cmdn" title="54人想要">54人想要</div>
        </div>
        """
        items = extract_from_html(sample)
        print("测试样本提取结果:")
        print(json.dumps(items, ensure_ascii=False, indent=2))
        assert len(items) == 2, f"期望 2 个,得到 {len(items)}"
        assert items[0]["title"] == "Hello Kitty 拼豆挂件 ¥25.9 包邮"
        assert items[0]["price"] == "¥25", f"价格应是 ¥25,实际: {items[0]['price']!r}"
        assert items[0]["want"] == 3
        assert items[1]["price"] == "39.99", f"价格应是 39.99,实际: {items[1]['price']!r}"
        assert items[1]["want"] == 54
        print("✅ 全部断言通过")
    else:
        html_path = Path(sys.argv[1])
        if not html_path.exists():
            print(f"❌ 文件不存在: {html_path}")
            sys.exit(1)
        html = html_path.read_text()
        items = extract_from_html(html)
        print(f"📦 {html_path} → 提取 {len(items)} 个商品")
        for it in items:
            print(f"  #{it['index']:2d}  {it['title'][:60]:<60s}  ¥{it['price']:<8s}  {it['want']} 人想要")

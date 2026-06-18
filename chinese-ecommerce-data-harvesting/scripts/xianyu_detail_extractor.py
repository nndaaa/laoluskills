#!/usr/bin/env python3
"""闲鱼 详情页提取器 (v11, verified 2026-06-18)

从 Playwright 渲染后的闲鱼商品详情页提取主商品数据。
**不要** 用这个提取器去解析搜索结果页 — 那个用 xianyu_extractor.py。

关键陷阱: 详情页底部有"为你推荐"和"看了又看"两个推荐区,
它们用的是搜索页的 class 结构 (number--/decimal--/text--MaM9Cmdn),
跟主商品用的一组完全不同的 class。 用搜索页的提取器在详情页
上会拿到推荐商品的数据,不是主商品的。

主商品专属 class 锚点:
- title: [class*="desc--"] 第一个 <span> 文本
- price: [class*="price--"] (e.g. price--OEWLbcxC)
- want:  [class*="want--"]  第一个 <div> 文本 (格式: N人想要)
- views: [class*="want--"]  第二个 <div> 文本 (格式: N浏览)
- 包邮/自提: [class*="post--"] 多个
- 卖家昵称: [class*="item-user-info-nick--"]
- 信用等级: [class*="item-user-info-level--"] <img title>
- 卖家信息: [class*="item-user-info-label--"] 5 个,按顺序:
    [0]地区 [1]上次登录 [2]注册 [3]成交 [4]好评率
- 描述: [class*="desc--"] 所有 <span> 文本拼接
- **图片 (v12 新增):** `<img>` 标签 `class` 含 `fadeInImg` + `src` 含 `bao/uploaded`
  - 用 `fadeInImg` 排除系统图标(信用等级/担保交易/装饰),用 `bao/uploaded` 排除商品宣传 banner
  - URL 通常带 `_220x10000Q90.jpg_.webp` 后缀,是闲鱼压缩图;去掉后缀可拿原图
  - 主商品图通常 2-7 张(套装/盲盒 1-2 张,IP 款 4-7 张)

两种用法:
1. 离线 (推荐 - 调试快,无网络风险):
   html = Path("dump/detail_v11.html").read_text()
   data = extract_detail_from_html(html)

2. 在线 (在 Playwright page 里):
   data = await extract_detail_from_page(page)
"""
import re
from pathlib import Path
from typing import Dict, List


def _clean(text: str) -> str:
    """剥 HTML 标签,合并空白"""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_detail_from_html(html: str) -> Dict:
    """从本地详情页 HTML 提取主商品数据 (离线,用于调试)

    Args:
        html: 完整 HTML 字符串
    Returns:
        {
            "title": str,
            "price": str,
            "want": int,
            "views": int,
            "shipping_tags": List[str],
            "seller_nick": str,
            "seller_level": str,
            "seller_location": str,
            "seller_last_seen": str,
            "seller_age": str,        # 注册时间,如 "来闲鱼9年"
            "seller_sold_count": str, # 卖出件数,如 "卖出47件宝贝"
            "seller_positive_rate": str, # 好评率,如 "好评率100%"
            "desc": str,              # 完整描述 (| 分隔的多行)
        }
        找不到的字段就是空字符串或 0
    """
    out: Dict = {
        "title": "",
        "price": "",
        "want": 0,
        "views": 0,
        "shipping_tags": [],
        "seller_nick": "",
        "seller_level": "",
        "seller_location": "",
        "seller_last_seen": "",
        "seller_age": "",
        "seller_sold_count": "",
        "seller_positive_rate": "",
        "desc": "",
        "images": [],  # v12: 主商品图片 URL 列表
    }

    # === 描述块: 找 desc-- 的所有 span 文本 ===
    # v12: 用锚点定位 desc-- 位置,往后扫到 labels-- 锚点
    desc_pos = re.search(r'<[^>]+class="desc--[A-Za-z0-9]+"[^>]*>', html)
    if desc_pos:
        start = desc_pos.end()
        # 锚点: labels-- 是描述后的下一个元素
        next_anchor = re.search(r'<[^>]+class="labels?--', html[start:])
        end = start + next_anchor.start() if next_anchor else start + 3000
        inner = html[start:end]
        # 第一个 <span> 是标题
        first_span = re.search(r"<span>(.*?)</span>", inner, re.DOTALL)
        out["title"] = _clean(first_span.group(1) if first_span else inner)
        # 全部 <span> 拼成完整描述
        all_spans = re.findall(r"<span>(.*?)</span>", inner, re.DOTALL)
        out["desc"] = " | ".join(_clean(s) for s in all_spans if _clean(s))

    # === 价格: price-- div (不是 number--/decimal-- 那些是搜索页/推荐位的) ===
    # v12 注意: class 名后可能有空格 (e.g. class="price--OEWLbcxC "),正则要宽容
    p = re.search(r'<div class="price--[A-Za-z0-9]+\s*"[^>]*>([^<]+)</div>', html)
    if p:
        out["price"] = p.group(1).strip()

    # === 想要 + 浏览: want-- 块 ===
    # v12: 块内含多个 div (含 space-- 占位),先定位 want-- 类位置,再往后扫到下一个 desc 锚点
    want_pos = re.search(r'<[^>]+class="want--[A-Za-z0-9]+"', html)
    if want_pos:
        start = want_pos.end()
        # 找下一个关键锚点: desc-- 或 价格块后
        next_anchor = re.search(r'<[^>]+class="(?:desc|price|tips|notLoginContainer)--', html[start:])
        end = start + next_anchor.start() if next_anchor else start + 1000
        inner = html[start:end]
        wm = re.search(r"(\d+)\s*人想要", inner)
        vm = re.search(r"(\d+)\s*浏览", inner)
        out["want"] = int(wm.group(1)) if wm else 0
        out["views"] = int(vm.group(1)) if vm else 0

    # === 包邮/自提 标签: post-- ===
    out["shipping_tags"] = re.findall(
        r'<div class="post--[A-Za-z0-9]+"[^>]*>([^<]+)</div>', html
    )

    # === 卖家昵称 ===
    sn = re.search(
        r'<div class="item-user-info-nick--[A-Za-z0-9]+"[^>]*>([^<]+)</div>', html
    )
    out["seller_nick"] = sn.group(1).strip() if sn else ""

    # === 信用等级: 等级图片的 title 属性 ===
    sl = re.search(
        r'<div class="item-user-info-level--[A-Za-z0-9]+"[^>]*>.*?title="([^"]+)"',
        html,
        re.DOTALL,
    )
    out["seller_level"] = sl.group(1).strip() if sl else ""

    # === 卖家 5 个标签: 地区 / 上次 / 注册 / 成交 / 好评率 ===
    labels = re.findall(
        r'<div class="item-user-info-label--[A-Za-z0-9]+"[^>]*>([^<]+)</div>', html
    )
    if len(labels) >= 1:
        out["seller_location"] = labels[0].strip()
    if len(labels) >= 2:
        out["seller_last_seen"] = labels[1].strip()
    if len(labels) >= 3:
        out["seller_age"] = labels[2].strip()
    if len(labels) >= 4:
        out["seller_sold_count"] = labels[3].strip()
    if len(labels) >= 5:
        out["seller_positive_rate"] = labels[4].strip()

    # === 图片: fadeInImg + bao/uploaded (v12 新增) ===
    out["images"] = re.findall(
        r'<img[^>]+class="[^"]*fadeInImg[^"]*"[^>]+src="([^"]*bao/uploaded[^"]+)"',
        html,
    )

    return out


async def extract_detail_from_page(page) -> Dict:
    """从 Playwright page 提取主商品数据 (在线)

    跟 extract_detail_from_html 等价,但走 page.evaluate 拿 DOM。
    离线调试时优先用 extract_detail_from_html。
    """
    return await page.evaluate(
        """
        () => {
            const out = {
                title: '', price: '', want: 0, views: 0,
                shipping_tags: [], seller_nick: '', seller_level: '',
                seller_location: '', seller_last_seen: '',
                seller_age: '', seller_sold_count: '',
                seller_positive_rate: '', desc: ''
            };
            const clean = (s) => (s || '').replace(/<[^>]+>/g, '').replace(/\\s+/g, ' ').trim();

            // Title + desc
            const descEl = document.querySelector('[class*="desc--"]');
            if (descEl) {
                const spans = descEl.querySelectorAll('span');
                if (spans.length > 0) out.title = clean(spans[0].innerHTML);
                out.desc = Array.from(spans).map(s => clean(s.innerHTML)).filter(Boolean).join(' | ');
            }
            // Price
            const priceEl = document.querySelector('[class*="price--"]');
            if (priceEl) out.price = priceEl.textContent.trim();
            // Want + views
            const wantEl = document.querySelector('[class*="want--"]');
            if (wantEl) {
                const inner = wantEl.textContent;
                const wm = inner.match(/(\\d+)\\s*人想要/);
                const vm = inner.match(/(\\d+)\\s*浏览/);
                if (wm) out.want = parseInt(wm[1]);
                if (vm) out.views = parseInt(vm[1]);
            }
            // Shipping tags
            out.shipping_tags = Array.from(document.querySelectorAll('[class*="post--"]'))
                .map(e => e.textContent.trim()).filter(Boolean);
            // Seller
            const nickEl = document.querySelector('[class*="item-user-info-nick--"]');
            if (nickEl) out.seller_nick = nickEl.textContent.trim();
            const levelEl = document.querySelector('[class*="item-user-info-level--"] img[title]');
            if (levelEl) out.seller_level = levelEl.getAttribute('title');
            const labels = document.querySelectorAll('[class*="item-user-info-label--"]');
            if (labels.length >= 1) out.seller_location = labels[0].textContent.trim();
            if (labels.length >= 2) out.seller_last_seen = labels[1].textContent.trim();
            if (labels.length >= 3) out.seller_age = labels[2].textContent.trim();
            if (labels.length >= 4) out.seller_sold_count = labels[3].textContent.trim();
            if (labels.length >= 5) out.seller_positive_rate = labels[4].textContent.trim();

            return out;
        }
        """
    )


# --- 自我测试 ---
if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("用法: python3 xianyu_detail_extractor.py <dump/detail_xxx.html>")
        print("      python3 xianyu_detail_extractor.py --test")
        sys.exit(1)

    if sys.argv[1] == "--test":
        # 用一段人造 HTML 测试 (模拟 v12 真实结构,2026-06-18 真实样本)
        # 注: 实际抓取时 desc--/want-- 是 <span> 不是 <div>,已按真实样本更新
        sample = """
        <div class="tips--bJdC_yBS">
            <div class="value--EyQBSInp">
                <div class="symbol--DK_64UaK">¥</div>
                <div class="price--OEWLbcxC">25</div>
                <div class="post--eemp1Mym">包邮</div>
                <div class="post--eemp1Mym">可自提</div>
            </div>
        </div>
        <span class="want--ecByv3Sr"><div>3人想要</div><div class="space--ezBlybDX"></div><div> 95浏览</div></span>
        <span class="desc--GaIUKUQY"><span><span>Hello Kitty像素风拼豆挂件 钓鱼造型</span></span><br><span><span>纯手工拼的 成色几乎全新</span></span></span>
        <div class="labels--ndhPFgp8"><div class="item">成色</div></div>
        <div class="item-user-info-nick--rtpDhkmQ">大黑黑黑</div>
        <div class="item-user-info-level--oDS9KYgx">
            <img title="信用极好" />
        </div>
        <div class="item-user-info-label--NLTMHARN">金华</div>
        <div class="item-user-info-label--NLTMHARN">4分钟前来过</div>
        <div class="item-user-info-label--NLTMHARN">来闲鱼9年</div>
        <div class="item-user-info-label--NLTMHARN">卖出47件宝贝</div>
        <div class="item-user-info-label--NLTMHARN">好评率100%</div>
        """
        data = extract_detail_from_html(sample)
        print("测试样本提取结果:")
        print(json.dumps(data, ensure_ascii=False, indent=2))

        assert data["title"] == "Hello Kitty像素风拼豆挂件 钓鱼造型", f"title 错: {data['title']!r}"
        assert data["price"] == "25", f"price 错: {data['price']!r}"
        assert data["want"] == 3, f"want 错: {data['want']}"
        assert data["views"] == 95, f"views 错: {data['views']}"
        assert "包邮" in data["shipping_tags"] and "可自提" in data["shipping_tags"]
        assert data["seller_nick"] == "大黑黑黑", f"昵称错: {data['seller_nick']!r}"
        assert data["seller_level"] == "信用极好", f"等级错: {data['seller_level']!r}"
        assert data["seller_location"] == "金华"
        assert data["seller_last_seen"] == "4分钟前来过"
        assert data["seller_age"] == "来闲鱼9年"
        assert data["seller_sold_count"] == "卖出47件宝贝"
        assert data["seller_positive_rate"] == "好评率100%"
        print("✅ 全部断言通过 (13 个字段)")

    else:
        html_path = Path(sys.argv[1])
        if not html_path.exists():
            print(f"❌ 文件不存在: {html_path}")
            sys.exit(1)
        html = html_path.read_text()
        data = extract_detail_from_html(html)
        print(f"📄 {html_path} → 主商品数据:")
        print(json.dumps(data, ensure_ascii=False, indent=2))

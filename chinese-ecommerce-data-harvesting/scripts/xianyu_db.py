#!/usr/bin/env python3
"""SQLite 存储层 - 闲鱼详情页数据
- 单一表 xianyu_items
- 启动时建表/加字段
- 提供 save_items / query / dedup
- HTML 文件在导入数据后自动删(可配)
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional

DB_PATH = Path("data/xianyu.db")
DUMP_DIR = Path("dump")


SCHEMA = """
CREATE TABLE IF NOT EXISTS xianyu_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT UNIQUE NOT NULL,        -- 闲鱼商品 id (从 URL 提取)
    keyword TEXT,                         -- 搜索关键词
    captured_at TEXT NOT NULL,            -- 抓取时间 ISO

    -- 主商品字段
    title TEXT,
    price TEXT,
    want INTEGER DEFAULT 0,
    views INTEGER DEFAULT 0,

    -- 邮/提
    shipping_tags TEXT,                   -- JSON 数组字符串

    -- 卖家
    seller_nick TEXT,
    seller_level TEXT,
    seller_location TEXT,
    seller_last_seen TEXT,
    seller_age TEXT,
    seller_sold_count TEXT,
    seller_positive_rate TEXT,

    -- 描述/图片
    description TEXT,                     -- | 分隔的多行
    images TEXT,                          -- JSON 数组字符串
    image_count INTEGER DEFAULT 0,

    -- 元数据
    url TEXT,
    raw_html_path TEXT                    -- 导入后 HTML 被删,这个字段变 NULL
)
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_keyword ON xianyu_items(keyword)",
    "CREATE INDEX IF NOT EXISTS idx_captured ON xianyu_items(captured_at)",
    "CREATE INDEX IF NOT EXISTS idx_want ON xianyu_items(want)",
    "CREATE INDEX IF NOT EXISTS idx_price_num ON xianyu_items(CAST(price AS REAL))",
]


def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """初始化数据库(建表+建索引)"""
    db_path.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    for idx in INDEXES:
        conn.execute(idx)
    conn.commit()
    return conn


def extract_item_id(url: str) -> str:
    """从 URL 提取闲鱼 item_id
    https://www.goofish.com/item?id=1056512605324&categoryId=... → 1056512605324
    """
    import re
    if not url:
        return ""
    m = re.search(r"id=(\d+)", url)
    return m.group(1) if m else url


def save_items(items: List[Dict], keyword: str, conn: Optional[sqlite3.Connection] = None,
               delete_html_after: bool = True) -> int:
    """保存商品到数据库

    Args:
        items: 从 extract_detail_from_html 得到的列表
        keyword: 搜索关键词
        conn: 已有的连接,None 则新建
        delete_html_after: 是否在保存后删除 raw_html_path 指向的文件

    Returns:
        实际写入/更新的行数
    """
    if conn is None:
        conn = init_db()

    now = datetime.now().isoformat()
    written = 0

    for item in items:
        item_id = extract_item_id(item.get("url", ""))
        url = item.get("url", "")
        shipping = json.dumps(item.get("posts", []), ensure_ascii=False)
        images = json.dumps(item.get("images", []), ensure_ascii=False)
        desc = item.get("desc", "")
        image_count = len(item.get("images", []))

        # raw_html_path: 从 detail_v12_N.html 命名约定推断
        idx = item.get("_idx")  # 抓取时的序号(1-based)
        raw_html = f"dump/detail_v12_{idx}.html" if idx else None

        conn.execute(
            """
            INSERT INTO xianyu_items (
                item_id, keyword, captured_at,
                title, price, want, views,
                shipping_tags,
                seller_nick, seller_level, seller_location,
                seller_last_seen, seller_age,
                seller_sold_count, seller_positive_rate,
                description, images, image_count,
                url, raw_html_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET
                captured_at = excluded.captured_at,
                want = excluded.want,
                views = excluded.views,
                price = excluded.price,
                title = excluded.title,
                description = excluded.description,
                images = excluded.images,
                image_count = excluded.image_count,
                seller_sold_count = excluded.seller_sold_count
            """,
            (
                item_id, keyword, now,
                item.get("title"), item.get("price"),
                item.get("want", 0), item.get("views", 0),
                shipping,
                item.get("seller"), item.get("seller_level", ""), item.get("location"),
                item.get("last_visit"), item.get("register_age"),
                item.get("sold_count"), item.get("good_rate"),
                desc, images, image_count,
                url, raw_html,
            ),
        )
        written += 1

    conn.commit()

    # 删除已导入的 HTML 文件
    if delete_html_after:
        deleted = 0
        for item in items:
            raw = item.get("raw_html_path") or (
                f"dump/detail_v12_{item.get('_idx')}.html" if item.get("_idx") else None
            )
            if raw and Path(raw).exists():
                Path(raw).unlink()
                deleted += 1
        if deleted:
            print(f"🧹 已清理 {deleted} 个 HTML 文件", flush=True)

    return written


def cleanup_old_htmls(dump_dir: Path = DUMP_DIR, keep_days: int = 3):
    """清理 dump/ 下超过 keep_days 天的 HTML
    不删 JSON (那是数据库视图)
    """
    if not dump_dir.exists():
        return 0
    cutoff = datetime.now() - timedelta(days=keep_days)
    deleted = 0
    for f in dump_dir.glob("*.html"):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            f.unlink()
            deleted += 1
    return deleted


def cleanup_old_logs(log_dir: Path = Path("logs"), keep_days: int = 7):
    """清理 logs/ 下超过 keep_days 天的日志"""
    if not log_dir.exists():
        return 0
    cutoff = datetime.now() - timedelta(days=keep_days)
    deleted = 0
    for f in log_dir.glob("*.log"):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            f.unlink()
            deleted += 1
    return deleted


def query(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> List[Dict]:
    """通用查询,返回 dict 列表"""
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def stats(conn: sqlite3.Connection) -> Dict:
    """数据库统计"""
    out = {}
    out["total"] = conn.execute("SELECT COUNT(*) FROM xianyu_items").fetchone()[0]
    out["keywords"] = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT keyword FROM xianyu_items WHERE keyword IS NOT NULL"
        ).fetchall()
    ]
    out["sellers"] = conn.execute("SELECT COUNT(DISTINCT seller_nick) FROM xianyu_items").fetchone()[0]
    out["first_at"] = conn.execute("SELECT MIN(captured_at) FROM xianyu_items").fetchone()[0]
    out["last_at"] = conn.execute("SELECT MAX(captured_at) FROM xianyu_items").fetchone()[0]
    out["db_size_mb"] = round(Path(DB_PATH).stat().st_size / 1024 / 1024, 3) if DB_PATH.exists() else 0
    return out


# --- 自我测试 ---
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # 用 v12 抓的数据测试
        test_items = [
            {
                "_idx": 1, "url": "https://www.goofish.com/item?id=TEST001",
                "title": "测试商品 1", "price": "25.9", "want": 3, "views": 97,
                "posts": ["包邮", "可自提"],
                "seller": "测试卖家", "seller_level": "信用极好",
                "location": "金华", "last_visit": "2分钟前来过",
                "register_age": "来闲鱼9年", "sold_count": "卖出47件宝贝",
                "good_rate": "好评率100%",
                "desc": "测试商品 | 描述1 | 描述2",
                "images": ["url1", "url2", "url3", "url4"],
            }
        ]

        # 用临时 db
        test_db = Path("/tmp/test_xianyu.db")
        if test_db.exists():
            test_db.unlink()

        conn = init_db(test_db)
        n = save_items(test_items, keyword="测试关键词", conn=conn, delete_html_after=False)
        print(f"✅ 写入 {n} 条")

        # 再跑一次同样的(测试 ON CONFLICT 更新)
        n2 = save_items(test_items, keyword="测试关键词", conn=conn, delete_html_after=False)
        print(f"✅ 重复写入 {n2} 条(应该更新)")

        # 查询
        rows = query(conn, "SELECT item_id, title, want, views, price FROM xianyu_items")
        print(f"\n📊 查询结果 ({len(rows)} 条):")
        for r in rows:
            print(f"   {r}")

        # 统计
        s = stats(conn)
        print(f"\n📈 数据库统计: {s}")

        # 清理
        conn.close()
        test_db.unlink()
        print("\n✅ 测试通过 (db 已清理)")

    else:
        # 默认: 打印数据库状态
        conn = init_db()
        s = stats(conn)
        print(f"📊 数据库: {DB_PATH}")
        print(f"   总条数: {s['total']}")
        print(f"   关键词: {s['keywords']}")
        print(f"   独立卖家: {s['sellers']}")
        print(f"   首次抓取: {s['first_at']}")
        print(f"   最近抓取: {s['last_at']}")
        print(f"   文件大小: {s['db_size_mb']} MB")

        if s["total"] > 0:
            print(f"\n🔝 want TOP 5:")
            top = query(conn, "SELECT title, want, views, price, seller_nick FROM xianyu_items ORDER BY want DESC LIMIT 5")
            for r in top:
                print(f"   {r['want']:>6} 想要 | ¥{r['price']:<10} | {r['title'][:40]} | {r['seller_nick']}")
        conn.close()
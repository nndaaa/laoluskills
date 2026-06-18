# 头条 / 字节系搜索 — 可用的公开数据路径(2026-06-18 实战)

**结论先说:** 在 闲鱼/淘宝/小红书/拼多多 公开 API 全部被风控的 2026 年,**头条搜索是唯一一个能用 `requests` + 简单 cookie 技巧拿到的中文内容平台数据源**。它不直接告诉你闲鱼销量,但能告诉你**买家关注什么、什么细分在升温、爆款标题套路**。对于"选赛道"和"抄标题"这两个核心需求,头条搜索的 ROI 远高于手动采集。

## 关键技巧:Cookie 预热,再搜

头条搜索直接 `GET /search?keyword=...` **返回空数据**(HTML 1.7MB 但 search results 在 JSON 块里全是 0 条)。**必须先访问主页拿 cookie,再搜**才有数据。

```python
import requests

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

s = requests.Session()
s.headers.update({
    'User-Agent': UA,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Upgrade-Insecure-Requests': '1',
})

# 第 1 步:访问主页,头条会下发 cookie
s.get('https://so.toutiao.com/', timeout=10)

# 第 2 步:再搜 - 现在能拿到数据了
r = s.get('https://so.toutiao.com/search', params={
    'keyword': '手工帆布包',
    'pd': 'information',  # 关键参数:表示搜资讯(还有其他值:video/aweme)
    'source': 'input',
}, timeout=15)
```

**对比:**
- 直接搜(不预热):HTML 1.7MB,但 `T.flow` 数据块 0 个
- 预热后搜:HTML 1.7MB,`T.flow` 数据块 9-10 个/页

## 数据提取:T.flow 嵌套 JSON

头条把搜索结果嵌在 `window.T && T.flow({ data: {...}})` 调用里,每个调用是一个完整的搜索结果,**JSON 有 2-3 层嵌套**。普通的 `re.findall(r'\{.+?\}', html)` 会**在第一个 `}` 处提前终止**,只抓到外层。

**正确做法:用括号配对计数器手动解析。**(脚本见 `scripts/toutiao_extract.py`)

```python
def extract_balanced(text, start_pos):
    """从 { 开始配对找匹配 }"""
    if text[start_pos] != '{':
        return None, start_pos
    depth, i = 0, start_pos
    in_str, escape = False, False
    while i < len(text):
        c = text[i]
        if escape:
            escape = False
        elif c == '\\':
            escape = True
        elif c == '"':
            in_str = not in_str
        elif not in_str:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return text[start_pos:i+1], i+1
        i += 1
    return None, i
```

## 关键字段(标准化后)

| 字段 | 含义 | 用法 |
|---|---|---|
| `title` | 标题(去 `<em>` 标签) | 抄标题套路 |
| `abstract` | 摘要 | 抓买家关注点关键词 |
| `comment_count` | 评论数 | 互动量计算 |
| `repin_count` | 收藏数 | 互动量计算(权重最高) |
| `forward_count` | 转发数 | 互动量计算 |
| `digg_count` | 点赞数 | 互动量计算 |
| `media_name` | 发布者 | 找同类账号学习 |
| `datetime` | 发布时间(YYYY-MM-DD HH:MM:SS) | 趋势分析 |
| `group_id` | 文章 ID | 去重 key |
| `article_url` | 文章链接 | 跟进具体爆款 |
| `tags` | 标签列表 | 关键词扩展 |
| `media_type` | 类型(2=图文) | 筛选有效内容 |

**互动量公式:** `engagement = comment + repin*2 + forward + digg`(收藏权重最高,因为代表"我想做")

## 分页与速率

- 每页 ~9-10 条(头条搜索分页就这么多,不是 bug)
- 2 页/关键词足够(再多边际收益低,头条会限流)
- 关键词间加 `time.sleep(random.uniform(2.5, 5.0))` 秒延迟
- 实测跑 5 赛道 × 3 关键词 × 2 页 = 30 次请求,无任何封控

## 数据噪声过滤(标题/摘要关键词粗筛)

头条搜"手工包"返回的 9 条里通常有 4-5 条是电视剧/明星/无关内容。用关键词评分粗筛:

```python
KW_TRUE = ['手工', 'diy', 'DIY', '自制', '手作', '手缝', '钩针', '编织', '缝制']
KW_FALSE_STRICT = ['演员', '电视剧', '综艺', '明星', '爱马仕', 'LV', 'GUCCI', '翻红', '代言']

score = sum(2 for k in KW_TRUE if k in text)  # 命中加分
if any(k in text for k in KW_FALSE_STRICT):
    score -= 5  # 明确是其他话题减分
is_relevant = score > 0
```

实战:9 条 → 6 条相关,4 个垃圾条目被去掉。

## 后续可用的字节系搜索入口

头条这个 cookie-then-search 技巧**很可能也适用于**:
- `so.toutiao.com` ✅ 资讯(本 session 验证)
- 西瓜视频搜索(待验证)
- 抖音网页搜索(待验证,可能风控更严)

字节系共享登录态和搜索后端,cookie 预热后应该都能拿到结构化数据。

## 与手动采集对比:什么时候用哪个

| 场景 | 推荐 |
|---|---|
| 选赛道,需要看 5+ 个细分方向 | **头条搜索(本路径)** |
| 验证某个具体爆款(已知链接) | 手动采集 |
| 长期监控某品类价格 | 京东/淘宝商品详情页慢速爬 |
| 闲鱼 24 小时热卖榜 | **头条搜索 + 手动浏览闲鱼辅助** |

## 实测案例(2026-06-18)

**任务:** 选 5 个手工包赛道,定方向。

**操作:** 头条搜 15 个关键词(5 赛道 × 3 词),每词 2 页。30 个请求,~2 分钟完成,零封控。

**输出:** 130 条去重数据,49 条相关。**发现:** 卡通/钩针 IP 赛道平均互动量 241,是其他赛道 50-200 倍,直接定了方向。

**对比:** 同样的问题如果走"用户手动采 5-10 个爆款"路径,用户得在闲鱼逛 15-20 分钟,样本只有 5-10 条。头条路径样本大 10-20 倍,**且用户零参与**。

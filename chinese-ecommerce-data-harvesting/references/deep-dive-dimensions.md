# 6-Dimension Deep-Dive Pattern — After the User Picks a Category

**Use this when the user has selected a 赛道 from your 选赛道 report and wants to "go deeper" before executing.** Pattern from 2026-06-18 拼豆 deep-dive.

## Why a deep-dive is needed

The first-pass 选赛道 report answers "which 赛道 is hottest". A deep-dive answers:

- **Who** is buying (buyer profile)
- **How hard** is it to learn (tutorial path)
- **What** should I make first (product types)
- **Where** do I source materials and what do they cost (sales / supply chain)
- **Where** should I sell (channel)
- **What could go wrong** (compliance / safety / IP risk)

Skipping any of these = blind spots. In 2026-06-18, the `risk` dimension alone surfaced 5 specific gotchas (3C 认证, 触电事故, 毒气超标, IP 侵权, 儿童安全) that would have torpedoed a launch.

## The 6 dimensions

| # | Dimension | What you learn | Example keywords (拼豆) |
|---|---|---|---|
| 1 | **demand** | Buyer's pain, motivation, occasion | `拼豆`, `拼豆为什么火`, `拼豆 减压`, `拼豆 亲子`, `拼豆 送礼物`, `拼豆 治愈`, `拼豆 上瘾` |
| 2 | **tutorial** | Learning curve, tools, time-to-first-product | `拼豆教程`, `拼豆 新手`, `拼豆 入门`, `拼豆 工具`, `拼豆 步骤`, `拼豆 烫画技巧` |
| 3 | **product** | SKU types (what to make) | `拼豆挂件`, `拼豆钥匙扣`, `拼豆杯垫`, `拼豆冰箱贴`, `拼豆相框`, `拼豆胸针`, `拼豆手机壳` |
| 4 | **sales** | Supply chain, pricing, wholesale options | `拼豆材料包`, `拼豆套装`, `拼豆模板`, `拼豆熨斗`, `拼豆工具套装` |
| 5 | **channel** | Where competitors already sell (and unsaturated channels) | `拼豆 闲鱼`, `拼豆 淘宝`, `拼豆 小红书`, `拼豆 抖音`, `拼豆 拼多多` |
| 6 | **risk** | Compliance, safety, IP, certification | `拼豆 侵权`, `拼豆 版权`, `拼豆 儿童 安全`, `拼豆 熔点`, `拼豆 拼接 安全` |

## Sizing the crawl

- **5-12 keywords per dimension** (start with 5, expand if data is thin)
- **2-3 pages per keyword** (more pages give diminishing returns)
- **Time-filter all results to your cutoff** (default: 2024+ for "current trend")
- **Total: 30-72 keywords × 2-3 pages = 100-200 requests**
- **Runtime: 5-10 minutes** on a single Python session
- **Risk-dimension MUST be ≥5 keywords** — the gotchas are the whole point

## How each dimension informs the report

- `demand` → fills the **"买家画像"** section of the report (4 buyer archetypes with %)
- `tutorial` → fills the **"教程与学习路径"** section (5-step beginner path, 7-day plan)
- `product` → fills the **"选品清单"** table (8 SKU types with cost / sell price / margin)
- `sales` → fills the **"原料成本"** table (wholesale vs retail pricing)
- `channel` → fills the **"销售渠道对比"** table (7 channels, which to pick first)
- `risk` → fills the **"合规与安全风险"** section (CRITICAL — always include this)

## Risk dimension gotchas (real examples from 2026-06-18 拼豆)

These all came from the `risk` dimension. None of them would have surfaced from the `demand` data alone:

1. **3C 认证** (China Compulsory Certification) — required for children's toys. Some cheap 拼豆 kits have no certification; selling to kids is illegal and dangerous.
2. **触电致死事故** — multiple news reports of children electrocuted by the mini iron. **MUST** ship with safety warning, must be USB low-voltage.
3. **毒气超标** — plastic beads release toxic fumes when heated above melting point. EVA material + ventilation is mandatory.
4. **版权雷区** — Disney, Pokémon, Sanrio characters cannot be made without license. Use "original pixel patterns" only.
5. **儿童年龄限制** — 3-14 岁 only suitable for **non-heated** 拼豆 (cold-set). Heated version is for 14+ or with adult supervision.

**Always include these as a 风险清单 table in the report**, with 严重度 column (高/中/低) and 应对 column.

## Output structure (the report the user actually wants)

After the deep-dive, the report should have **9 sections in this order**:

1. 市场规模与热度 (numbers from data + headlines)
2. 买家画像 (4 archetypes with single-price ranges)
3. 原料成本与产业链 (wholesale vs retail)
4. 教程与学习路径 (5-step beginner)
5. 销售渠道对比 (7 channels)
6. **合规与安全风险** (don't skip)
7. **闲鱼上手方案** (选品清单 + 标题模板 + 描述模板 + 风险话术)
8. 7 天行动清单
9. 5 条必看提醒

## The 4-table core (always include in section 7)

The "上手方案" section should always have these 4 tables, ready for the user to copy:

1. **选品清单** (8 SKU types, 编号/品类/进价/售价/利润率/备注)
2. **标题模板** (10 reusable titles, structure: [emoji][品类][差异化][钩子])
3. **商品描述模板** (3 段式: 为什么买 / 细节 / 关于我)
4. **风险应对话术** (4 常见问题 + 标准答复, 给非技术用户复制粘贴用)

The 风险话术 table is **especially important for the spouse** — pre-written answers to "你家豆子安全吗?" / "3 岁孩子能玩吗?" / "能做迪士尼吗?" / "能用多久?" etc.

## End with 3 concrete options (NOT open-ended "what next?")

After the report, the message ends with 3 distinct executable choices:

> A. **立刻买材料开始做** — 我给你列 1688/拼多多具体采购清单(店铺+链接+预算)
> B. **先做 1 件样品试水** — 我帮你列前 10 个最容易上手的图案
> C. **直接进闲鱼** — 套用标题模板,生成首批 5-8 款具体商品

A = action-oriented (fast feedback), B = risk-averse (validates skill), C = market-test-first (skip learning). Distinct paths, not variants. User picks one, you execute.

## 拼豆 deep-dive 实战数据 (2026-06-18)

For reference, the actual session produced:

- 52 keywords × 3 pages = 156 requests
- 1236 raw items → 266 unique after dedup
- All 6 dimensions populated
- 266 items with full T.flow data (title, datetime, engagement, author, etc.)
- Time-filtered to 2024+ before ranking
- Final report: 12.8KB markdown, sent to 飞书 家庭 group chat

The `risk` dimension alone had 34 items — enough to surface all 5 gotchas listed above. **This is why the risk dimension must be ≥5 keywords.**

## Common mistakes

- **Skipping the risk dimension** — "I'm just selling crafts, what could go wrong?" → a lot. Always run it.
- **Using 1 keyword per dimension** — 1 keyword = 1 perspective. Need 5-12 to surface the full picture.
- **Not time-filtering the deep-dive results** — same trap as 选赛道. The 5-year-old 拼豆 tutorial is still valid but the 5-year-old 拼豆 价格 reference is wildly outdated.
- **Writing the report before crawling** — let the data drive. If the risk dimension shows no real risk, drop the section. If it shows 5 gotchas, expand it.
- **Putting the report in 飞书 with markdown but no 简化版** — the spouse reads 飞书. The 简化版 (5 bullets, "只看重点") is for them. The full report is for the technical user.

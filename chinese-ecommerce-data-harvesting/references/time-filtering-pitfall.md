# Time-Filtering Pitfall — Why You MUST Filter by Datetime Before Ranking Categories

**The single most important data-quality lesson from the 2026-06-18 选赛道 session.** Save yourself the embarrassment of recommending the wrong category because of one viral article from 2019.

## What happened

The user asked: "5 candidate bag 赛道s, pick the best to invest in." I scraped 270 items from 头条搜索, computed per-赛道 average engagement, and reported:

> **首选:卡通/钩针 IP** (avg engagement 241)  
> 次选:复古中式 (21)  
> 避开:真皮手工 (6.6), 通勤极简 (5.1)

User then said: "确定这些数据的时间和有效性" — i.e. "validate the data's time and validity".

I checked the time distribution and found:
- 79/130 (61%) of items were 2026 (recent ✓)
- 46/130 (35%) were 2014-2023 (old viral artifacts ✗)
- The 卡通钩针包 category had 9 items with engagement 1150, 1043, 832, 442, 335, 212 — all from 2019-2023
- These 9 old items alone pulled the category average from "decent" to "240+"

**I was ranking decades-old viral content on the same scale as 2026 fresh data.** Of course 卡通钩针包 won — a 2019 article had 3 years to accumulate 互动.

## Re-ran with `datetime[:4] >= '2024'` filter

| Category | v1 (all-time) avg | v2 (2024+) avg | v2 sample size | v2 winner? |
|---|---|---|---|---|
| 卡通钩针包 | 241 | 99.3 (6 items) | 6 | no (small sample) |
| 复古拼布包 | 71.2 (4 items) | 71.2 | 4 | tie |
| **拼豆** | **78** | **58.9 (33 items)** | **33** | **yes — by far** |
| 帆布棉麻包 | 17.0 | 17.0 | 5 | no |
| 通勤极简包 | 0.2 | 0.2 | 4 | no |

When properly time-filtered:
- **拼豆 was the clear winner** with 33 fresh 2024+ samples averaging 58.9 互动, including a 北京日报 article with 784 互动
- 卡通钩针包 dropped from #1 to #2 (and was a small sample so its "99.3" is volatile)
- 真皮/通勤 stayed cold

**The conclusion flipped.** The user got actionable direction instead of "make 卡通钩针包 like it was 2019".

## Why this trap is so easy to fall into

1. **头条 doesn't expose a "sort by time" param that works.** You can pass time filters in the UI but the search API doesn't honor them. You have to filter post-hoc.
2. **Engagement metrics are cumulative.** A 2019 article with 1150 互动 has 7 years to accumulate. A 2026 article with 58 互动 is 3 weeks old. The 5x gap in averages is not "5x more popular" — it's "5x older".
3. **Headline metric "average engagement" hides this.** If you report `avg(engagement)` without time-decomposition, the reader has no way to know 60% of the volume is from old data.
4. **Categories with evergreen content (编织/钩针 tutorials) accumulate more old data than trending categories (拼豆).** This systematically biases "evergreen" categories upward, hiding the actually-trending ones.

## The rule (encode this in every 选赛道 workflow)

**Before any "rank categories" analysis, ALWAYS:**

1. Check time distribution: `Counter([r['datetime'][:4] for r in data])`
2. Print the year histogram. If >30% of data is from before your "current trend" cutoff, warn explicitly.
3. Pick a cutoff that matches the user's intent:
   - "现在什么火" → last 12-18 months
   - "长期投入哪个赛道" → last 24-36 months
   - "经典长期品类" → all time, but be explicit
4. Re-run the ranking on the filtered data.
5. If sample size per category drops below 5 after filtering, **flag it as low-confidence** — don't let a single viral article dominate.
6. Compare v1 (all-time) vs v2 (filtered) side by side in the report. Let the user see the swing.

## Cutoff heuristic

| User intent | Recommended cutoff | Why |
|---|---|---|
| "现在什么火" | 18 months from "now" | Trends shift quarterly; older is noise |
| "想投入做副业" | 24 months | Need to see sustainability, not just spike |
| "长期品类哪个好" | 36 months | Filter out fads, keep the trend |
| "看有没有蓝海机会" | 6 months | New categories emerge fast |
| "我做的这个品类整体怎么样" | all time + age-decomposition | Show the trajectory |

## What to put in the report

A clean way to show this is a v1/v2 comparison table:

```
| 排名 | v1 全期数据 | v2 近 24 月数据 |
| 1 | 卡通钩针包 (241) | 拼豆 (58.9) |
| 2 | 复古中式 (21) | 卡通钩针包 (99.3, 样本 6 条) |
| 3 | 帆布棉麻 (4.5) | 复古拼布 (71.2) |
```

Then a one-paragraph honest statement:
> "v1 数据被 2019-2022 的老爆款拉高了平均(单条 1150 互动)。v2 过滤 2024 年后,**真正当下火的是拼豆**。v1 误把『曾经的爆款』当成了『现在的趋势`。"

This is the kind of self-correction that builds trust — "I had it wrong, here's the right number, here's why."

## Don't make this mistake twice

This trap is universal. Any time you have time-series data and you're computing averages to rank categories, ask:
- "Is the older data systematically different from newer?"
- "Could one or two high-engagement items be skewing the average?"

The check is cheap (a few lines of Python). The cost of skipping it is recommending the wrong category to someone making real investment decisions.

"""
Category scoring template — convert a flat engagement-ranking
into a heat × difficulty × cost composite score.

Use this AFTER time-filtering the data (see references/time-filtering-pitfall.md).

Workflow:
1. Load the JSON you got from crawler_v3.py (or equivalent)
2. Filter by datetime cutoff (the agent's job; this script assumes filtered input)
3. Group by category, compute avg engagement + max engagement
4. Manually fill in DIFFICULTY and COST_START dicts based on your knowledge of the categories
5. Run score_categories() and print the TOP 3
"""
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


def engagement(item: dict) -> int:
    """Standard engagement formula for 头条 data."""
    return (
        (item.get('comment_count', 0) or 0) +
        (item.get('repin_count', 0) or 0) +
        (item.get('forward_count', 0) or 0) +
        (item.get('digg_count', 0) or 0)
    )


def difficulty_score(label: str) -> int:
    """
    Map difficulty label to 0-100 score (higher = easier to start).
    Customize labels for your domain.
    """
    return {
        '入门': 100,
        '极简': 100,
        '简单': 70,
        '中': 40,
        '难': 10,
    }.get(label, 50)


def cost_score(startup_cost_str: str) -> int:
    """
    Parse a Chinese cost string like "300-500(毛线+工具)" into a 0-100 score.
    Higher score = lower cost (better for new entrants).
    Extracts the first number, uses as a proxy.
    """
    import re
    nums = re.findall(r'\d+', startup_cost_str)
    if not nums:
        return 50
    # Use the lower bound of the range
    cost = int(nums[0])
    if cost < 100:
        return 100
    if cost < 300:
        return 70
    if cost < 500:
        return 40
    return 10


def score_categories(
    items: List[dict],
    category_field: str,
    difficulty_map: Dict[str, str],
    cost_map: Dict[str, str],
    heat_weight: float = 0.5,
    difficulty_weight: float = 0.3,
    cost_weight: float = 0.2,
) -> List[dict]:
    """
    Score categories by heat × difficulty × cost composite.

    Args:
        items: list of dicts, each must have `category_field` key and engagement fields
        category_field: key name for category (e.g. 'category', 'track')
        difficulty_map: {category: difficulty_label}  e.g. {'拼豆': '极简'}
        cost_map: {category: cost_string}  e.g. {'拼豆': '50-100(豆子+模板)'}
        weights: how to weight the three axes (must sum to 1.0)

    Returns: list of {category, count, avg, max, heat, difficulty, cost, composite}
             sorted by composite descending
    """
    assert abs(heat_weight + difficulty_weight + cost_weight - 1.0) < 1e-6, \
        "weights must sum to 1.0"

    by_cat = defaultdict(list)
    for item in items:
        cat = item.get(category_field)
        if cat:
            by_cat[cat].append(item)

    results = []
    for cat, cat_items in by_cat.items():
        if not cat_items:
            continue

        avg_eng = sum(engagement(i) for i in cat_items) / len(cat_items)
        max_eng = max(engagement(i) for i in cat_items)

        # Heat: scale so 100 engagement = 100 score, capped at 100
        heat = min(100, avg_eng * 2)

        diff = difficulty_score(difficulty_map.get(cat, '中'))
        cost = cost_score(cost_map.get(cat, '500'))

        composite = (
            heat * heat_weight +
            diff * difficulty_weight +
            cost * cost_weight
        )

        results.append({
            'category': cat,
            'count': len(cat_items),
            'avg_eng': avg_eng,
            'max_eng': max_eng,
            'heat': round(heat, 1),
            'difficulty': diff,
            'cost': cost,
            'composite': round(composite, 1),
        })

    results.sort(key=lambda x: x['composite'], reverse=True)
    return results


# ============================================================
# Worked example from 2026-06-18 (手工品类)
# ============================================================
EXAMPLE_DIFFICULTY = {
    'craft_拼豆豆': '极简',
    'bag_卡通钩针': '中',
    'bag_复古拼布': '简单',
    'craft_钩织玩偶': '中',
    'bag_帆布棉麻': '中',
    'craft_绳结中国结': '简单',
    'craft_羊毛毡': '简单',
    'craft_陶艺黏土': '中',
    'craft_刺绣布艺': '中',
    'craft_串珠饰品': '简单',
    'craft_滴胶UV胶': '简单',
    'craft_香薰蜡烛': '简单',
    'craft_干花压花': '简单',
    'bag_通勤极简': '中',
    'bag_真皮革': '难',
}

EXAMPLE_COST = {
    'craft_拼豆豆': '50-100(豆子+模板+熨斗)',
    'bag_卡通钩针': '300-500(毛线+工具)',
    'bag_复古拼布': '100-200(旧衣+针线)',
    'craft_钩织玩偶': '150-300(毛线+钩针)',
    'bag_帆布棉麻': '200-400(布料+缝纫机)',
    'craft_绳结中国结': '50-100(绳子即可)',
    'craft_羊毛毡': '150-300(羊毛+戳针)',
    'craft_陶艺黏土': '200-500(黏土+工具)',
    'craft_刺绣布艺': '100-200(布料+针线)',
    'craft_串珠饰品': '200-500(珠子+配件)',
    'craft_滴胶UV胶': '200-400(胶水+模具)',
    'craft_香薰蜡烛': '200-400(蜡+香精+模具)',
    'craft_干花压花': '100-300(干花+相框)',
    'bag_通勤极简': '500-800(专业工具)',
    'bag_真皮革': '1500-3000(皮革+专业工具)',
}


def run_example():
    """Demo on the real 2026-06-18 v2 data file."""
    data_dir = Path.home() / '.hermes' / 'projects' / 'xianyu_research' / 'data'
    json_files = sorted(data_dir.glob('toutiao_v3_*.json'), reverse=True)
    if not json_files:
        print("No v3 data file found. Run crawler_v3.py first.")
        return

    with open(json_files[0], 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Time-filter to 2024+
    filtered = [r for r in data if r.get('datetime', '')[:4] >= '2024']
    print(f"Loaded {len(data)} items, {len(filtered)} after 2024 filter\n")

    scored = score_categories(
        items=filtered,
        category_field='category',
        difficulty_map=EXAMPLE_DIFFICULTY,
        cost_map=EXAMPLE_COST,
    )

    print(f"{'Rank':<5} {'Category':<25} {'n':>4} {'avg':>6} {'max':>5} "
          f"{'heat':>5} {'diff':>5} {'cost':>5} {'composite':>10}")
    print("-" * 85)
    for i, row in enumerate(scored, 1):
        print(f"{i:<5} {row['category']:<25} {row['count']:>4} {row['avg_eng']:>6.1f} "
              f"{row['max_eng']:>5} {row['heat']:>5.0f} {row['difficulty']:>5} "
              f"{row['cost']:>5} {row['composite']:>10.1f}")


if __name__ == '__main__':
    run_example()

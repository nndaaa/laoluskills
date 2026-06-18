"""
JSON 嵌套解析工具集 — 用于从含 window.T/T.flow/类似 SPA 注入的 HTML 中
提取结构化数据块,绕过 re.findall(r'\{.+?\}') 在嵌套 {} 处提前终止的问题。

适用场景:中文电商平台(头条/西瓜/抖音/快手 等字节系站点)把搜索结果
以 `window.T && T.flow({ data: {...} })` 形式注入 HTML,JSON 有 2-3 层嵌套。

复用方式: 任何需要从 HTML 提取"一组带嵌套的 JSON 对象"时,直接 import。
"""
import re, json
from typing import List, Dict, Any, Optional, Tuple


def extract_balanced(text: str, start_pos: int) -> Tuple[Optional[str], int]:
    """
    从 start_pos(应是 '{')开始,配对找到匹配的 '}',返回子串和结束位置。

    正确处理:
    - 字符串内的 { } 不计入深度
    - 转义字符 \\" 不视为字符串边界
    - 嵌套任意层数都能正确配对

    Returns: (matched_substring, end_position) 或 (None, end_position)
    """
    if start_pos >= len(text) or text[start_pos] != '{':
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


def extract_all_json_blocks(text: str, anchor_pattern: str) -> List[Dict[str, Any]]:
    """
    找到所有 anchor_pattern 出现的位置,anchor 之后第一个 { 开始,
    配对到对应的 },json.loads 解析。

    Args:
        text: HTML 全文
        anchor_pattern: 例如 'window.T && T.flow({ data:'

    Returns: 解析成功的 dict 列表
    """
    results = []
    pos = 0
    while True:
        idx = text.find(anchor_pattern, pos)
        if idx == -1:
            break
        brace_start = text.find('{', idx + len(anchor_pattern))
        if brace_start == -1:
            break
        obj_text, end = extract_balanced(text, brace_start)
        if obj_text:
            try:
                obj = json.loads(obj_text)
                if isinstance(obj, dict):
                    results.append(obj)
            except json.JSONDecodeError:
                pass
        pos = end
    return results


# ============================================================
# 头条搜索专用封装
# ============================================================
TOUTIAO_ANCHOR = 'window.T && T.flow({ data:'


def parse_toutiao_results(html: str) -> List[Dict[str, Any]]:
    """从头条搜索页 HTML 提取所有搜索结果对象"""
    return extract_all_json_blocks(html, TOUTIAO_ANCHOR)


def normalize_toutiao_item(obj: Dict[str, Any], keyword: str = '') -> Dict[str, Any]:
    """把头条原始数据块标准化为通用 schema"""
    title = (obj.get('title') or '').replace('<em>', '').replace('</em>', '')
    abstract = (obj.get('abstract') or '').replace('<em>', '').replace('</em>', '')
    return {
        'keyword': keyword,
        'title': title,
        'media_type': obj.get('media_type', ''),
        'datetime': obj.get('datetime', ''),
        'display_time': obj.get('display_time', ''),
        'comment_count': obj.get('comment_count', 0) or 0,
        'forward_count': obj.get('forward_count', 0) or 0,
        'repin_count': obj.get('repin_count', 0) or 0,
        'digg_count': obj.get('digg_count', 0) or 0,
        'read_count': obj.get('read_count', 0) or 0,
        'author_id': obj.get('user_id', ''),
        'media_name': obj.get('media_name', '') or obj.get('source', ''),
        'group_id': obj.get('group_id', '') or obj.get('id', ''),
        'article_url': obj.get('article_url', '') or obj.get('item_source_url', ''),
        'abstract': abstract[:200],
        'image_url': obj.get('large_image_url', '') or obj.get('middle_image_url', ''),
        'tags': ','.join([t.get('text', '') if isinstance(t, dict) else str(t)
                         for t in (obj.get('tags') or [])]),
    }


# ============================================================
# 相关性粗筛(标题/摘要含特定关键词)
# ============================================================
def relevance_score(text: str, true_kws: List[str], false_kws: List[str] = None) -> int:
    """
    简单的相关性评分:命中 true_kws 加分,命中 false_kws 大幅减分。
    Returns: 整数分数(0 表示不相关,>0 表示相关)
    """
    score = sum(2 for k in true_kws if k in text)
    if false_kws:
        score -= sum(5 for k in false_kws if k in text)
    return score


# ============================================================
# 自测
# ============================================================
if __name__ == '__main__':
    # 单元测试:嵌套 JSON
    test = '{ data: { "title": "test { nested { deep } }", "n": 1 } }'
    result, _ = extract_balanced(test, test.find('{'))
    print(f"测试 1: {result}")
    assert 'deep' in result, "嵌套解析失败"

    # 字符串内的 { } 不应计入
    test2 = '{ data: "value with { and } inside" }'
    result, _ = extract_balanced(test2, 0)
    print(f"测试 2: {result}")
    assert result == test2

    print("✅ 所有自测通过")

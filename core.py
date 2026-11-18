"""
核心业务逻辑：菜谱数据加载与匹配。
app.py / cli.py / agent.py 共用，避免重复实现。

数据源：recipe_store（SQLite 主库，首次访问自动导入种子 JSON）。
菜谱食材为 [{"name": str, "amount": str}] 结构（旧的纯字符串在导入时已归一化）。
"""
import re

from recipe_store import ensure_db, load_all

_cache = None

# 用量合并：数字 + 可选单位（如 "2个"、"300克"、"1.5勺"）
_AMOUNT_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(.*?)\s*$")


def load_recipes():
    """加载菜谱数据（模块级缓存，进程内只读一次库）"""
    global _cache
    if _cache is None:
        ensure_db()
        _cache = load_all()
    return _cache


def reload_recipes():
    """强制重新读库（导入新数据后调用）"""
    global _cache
    ensure_db()
    _cache = load_all()
    return _cache


def _ingredient_names(recipe):
    return [i["name"] for i in recipe["main_ingredients"]]


def _taste_match(recipe_tastes, taste):
    """口味匹配：taste 可以是字符串（兼容旧调用）或列表（任一命中即可）"""
    if not taste:
        return True
    wanted = taste if isinstance(taste, (list, tuple)) else [taste]
    return any(any(w in rt or rt in w for w in wanted) for rt in recipe_tastes)


def find_matching_recipes(recipes, ingredients=None, taste=None, category=None, difficulty=None):
    """查找匹配的菜谱，按得分降序返回"""
    results = []

    for recipe in recipes:
        score = 0
        names = _ingredient_names(recipe)

        # 食材匹配（双向子串，命中 +10，一个都没有则淘汰）
        if ingredients:
            matched = sum(
                1 for ing in ingredients
                if any(ing in n or n in ing for n in names)
            )
            if matched > 0:
                score += matched * 10
            else:
                continue

        # 口味匹配（命中 +5，不命中淘汰）
        if taste:
            if _taste_match(recipe["taste"], taste):
                score += 5
            else:
                continue

        # 分类 / 难度：硬过滤
        if category and recipe["category"] != category:
            continue
        if difficulty and recipe["difficulty"] != difficulty:
            continue

        if score > 0 or (not ingredients and not taste):
            results.append((score, recipe))

    results.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in results]


def get_recipe_by_name(recipes, name):
    """按菜名精确查找菜谱"""
    return next((r for r in recipes if r["name"] == name), None)


def merge_amounts(amounts):
    """
    合并同一食材的多个用量：
      ["2个", "1个"]     -> "3个"      （数字+同单位可加）
      ["2个", "1根"]     -> "2个、1根"  （单位不同，罗列）
      ["2个", "1个", "1根"] -> "3个、1根"
      ["适量", "适量"]    -> "适量"     （非数字，去重罗列）
      ["", "2个"]        -> "2个"
    """
    parsed = []  # (value, unit) 或 (None, raw)
    for a in amounts:
        a = (a or "").strip()
        if not a:
            continue
        m = _AMOUNT_RE.match(a)
        if m and m.group(1):
            parsed.append((float(m.group(1)), m.group(2).strip()))
        else:
            parsed.append((None, a))

    if not parsed:
        return ""

    # 按单位分组累加数字项；非数字项单独去重
    sums = {}       # unit -> total
    non_numeric = []  # 保序去重的原始串
    for value, unit in parsed:
        if value is None:
            if unit not in non_numeric:
                non_numeric.append(unit)
        else:
            sums[unit] = sums.get(unit, 0.0) + value

    parts = []
    for unit, total in sums.items():
        num = int(total) if total == int(total) else round(total, 2)
        parts.append(f"{num}{unit}")
    parts.extend(non_numeric)
    return "、".join(parts)


def generate_shopping_list(recipes, owned_ingredients):
    """
    生成购物清单：主料 + 调料中你还没有的。
    返回 {食材名: {"dishes": 出现的菜数, "amount": 合并后的用量}}
    """
    needed = {}
    for recipe in recipes:
        for item in recipe["main_ingredients"] + recipe["seasonings"]:
            name = item["name"]
            if not any(own in name or name in own for own in owned_ingredients):
                entry = needed.setdefault(name, {"dishes": 0, "amounts": []})
                entry["dishes"] += 1
                if item.get("amount"):
                    entry["amounts"].append(item["amount"])

    return {
        name: {"dishes": info["dishes"], "amount": merge_amounts(info["amounts"])}
        for name, info in needed.items()
    }


def get_category(ingredient, categories):
    """获取食材分类"""
    for cat, items in categories.items():
        if ingredient in items:
            return cat
    return "其他"


def format_ingredients(items):
    """把 [{"name","amount"}] 格式化成展示字符串：'番茄 2个, 鸡蛋 3个'"""
    parts = []
    for it in items:
        name = it["name"] if isinstance(it, dict) else str(it)
        amount = (it.get("amount", "") if isinstance(it, dict) else "").strip()
        parts.append(f"{name} {amount}" if amount else name)
    return ", ".join(parts)

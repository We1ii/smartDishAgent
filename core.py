"""
核心业务逻辑：菜谱数据加载与匹配。
app.py / agent.py 共用，避免重复实现。
"""
import json
import os

DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".mimocode", "skills", "recipe-assistant", "recipes.json",
)

_cache = None


def load_recipes():
    """加载菜谱数据（带模块级缓存）"""
    global _cache
    if _cache is None:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _cache = (data["recipes"], data["ingredient_categories"])
    return _cache


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

        # 食材匹配（双向子串，命中 +10，一个都没有则淘汰）
        if ingredients:
            matched = sum(
                1 for ing in ingredients
                if any(ing in rIng or rIng in ing for rIng in recipe["main_ingredients"])
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


def generate_shopping_list(recipes, owned_ingredients):
    """生成购物清单：主料 + 调料中你还没有的，按出现次数计数"""
    needed = {}
    for recipe in recipes:
        for ing in recipe["main_ingredients"] + recipe["seasonings"]:
            if not any(own in ing or ing in own for own in owned_ingredients):
                needed[ing] = needed.get(ing, 0) + 1
    return needed


def get_category(ingredient, categories):
    """获取食材分类"""
    for cat, items in categories.items():
        if ingredient in items:
            return cat
    return "其他"

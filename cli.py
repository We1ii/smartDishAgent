"""
智能菜谱助手 - 命令行版本
运行: python cli.py
"""
import json
import os


def load_recipes():
    json_path = os.path.join(os.path.dirname(__file__), ".mimocode", "skills", "recipe-assistant", "recipes.json")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["recipes"], data["ingredient_categories"]


def find_recipes(recipes, ingredients=None, taste=None):
    results = []
    for recipe in recipes:
        score = 0
        if ingredients:
            matched = sum(1 for ing in ingredients
                        if any(ing in rIng or rIng in ing for rIng in recipe["main_ingredients"]))
            if matched == 0:
                continue
            score += matched * 10
        if taste:
            if not any(taste in t for t in recipe["taste"]):
                continue
            score += 5
        results.append((score, recipe))
    results.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in results]


def print_recipe(recipe):
    print(f"\n{'='*50}")
    print(f"  {recipe['name']}")
    print(f"  分类: {recipe['category']} | 难度: {recipe['difficulty']} | 时间: {recipe['time']}")
    print(f"  口味: {', '.join(recipe['taste'])}")
    print(f"{'='*50}")
    print(f"\n  食材:")
    print(f"    主料: {', '.join(recipe['main_ingredients'])}")
    print(f"    调料: {', '.join(recipe['seasonings'])}")
    print(f"\n  做法:")
    for i, step in enumerate(recipe["steps"], 1):
        print(f"    {i}. {step}")
    print(f"\n  标签: {', '.join(recipe['tags'])}")


def shopping_list(recipes, owned):
    needed = {}
    for recipe in recipes:
        for ing in recipe["main_ingredients"] + recipe["seasonings"]:
            if not any(own in ing or ing in own for own in owned):
                needed[ing] = needed.get(ing, 0) + 1
    return needed


def main():
    recipes, categories = load_recipes()

    print("\n" + "="*50)
    print("        🍳 智能菜谱助手")
    print("="*50)
    print("\n  功能:")
    print("    1. 按食材找菜")
    print("    2. 按口味找菜")
    print("    3. 生成购物清单")
    print("    4. 查看所有菜谱")
    print("    5. 退出")

    while True:
        print("\n" + "-"*50)
        choice = input("请选择功能 (1-5): ").strip()

        if choice == "1":
            print("\n输入你有的食材（用逗号分隔）:")
            ingredients = [x.strip() for x in input().split(",") if x.strip()]
            if ingredients:
                results = find_recipes(recipes, ingredients=ingredients)
                if results:
                    print(f"\n找到 {len(results)} 道匹配的菜谱:")
                    for r in results[:5]:
                        print(f"\n  • {r['name']} - {r['difficulty']} | {r['time']}")
                        print(f"    口味: {', '.join(r['taste'])}")
                    detail = input("\n输入菜名查看详情，或回车返回: ").strip()
                    if detail:
                        recipe = next((r for r in recipes if r["name"] == detail), None)
                        if recipe:
                            print_recipe(recipe)
                        else:
                            print("未找到该菜谱")
                else:
                    print("没有找到匹配的菜谱")

        elif choice == "2":
            print("\n选择口味: 酸甜/麻辣/清淡/咸鲜/微辣/爽脆/蒜香")
            taste = input("输入口味: ").strip()
            if taste:
                results = find_recipes(recipes, taste=taste)
                if results:
                    print(f"\n找到 {len(results)} 道匹配的菜谱:")
                    for r in results:
                        print(f"\n  • {r['name']} - {r['difficulty']} | {r['time']}")
                        print(f"    主料: {', '.join(r['main_ingredients'])}")
                else:
                    print("没有找到匹配的菜谱")

        elif choice == "3":
            print("\n选择菜谱（输入编号，多个用逗号分隔）:")
            for i, r in enumerate(recipes, 1):
                print(f"  {i}. {r['name']}")
            nums = input("\n输入编号: ").split(",")
            try:
                selected = [recipes[int(n.strip())-1] for n in nums if n.strip()]
            except (ValueError, IndexError):
                print("输入有误")
                continue

            print("\n输入你已有的食材（用逗号分隔，可留空）:")
            owned = [x.strip() for x in input().split(",") if x.strip()]

            if selected:
                needed = shopping_list(selected, owned)
                if needed:
                    print(f"\n购物清单 ({len(needed)}项):")
                    for ing, count in sorted(needed.items()):
                        suffix = f" ×{count}道菜" if count > 1 else ""
                        print(f"  □ {ing}{suffix}")
                else:
                    print("\n✅ 你已经拥有所有需要的食材！")

        elif choice == "4":
            print(f"\n所有菜谱 ({len(recipes)}道):")
            for r in recipes:
                print(f"\n  • {r['name']} - {r['category']} | {r['difficulty']} | {r['time']}")
                print(f"    主料: {', '.join(r['main_ingredients'])}")

        elif choice == "5":
            print("\n再见！")
            break

        else:
            print("无效选择，请输入 1-5")


if __name__ == "__main__":
    main()

"""
智能菜谱助手 - 命令行版本
运行: python cli.py

数据与匹配逻辑复用 core.py（SQLite 主库，首次运行自动导入种子）。
"""
from core import (
    load_recipes,
    find_matching_recipes,
    generate_shopping_list,
    format_ingredients,
)


def print_recipe(recipe):
    print(f"\n{'='*50}")
    print(f"  {recipe['name']}")
    print(f"  分类: {recipe['category']} | 难度: {recipe['difficulty']} | 时间: {recipe['time']}")
    print(f"  份量: {recipe.get('servings', 2)}人份 | 口味: {', '.join(recipe['taste'])}")
    print(f"{'='*50}")
    print("\n  食材:")
    print(f"    主料: {format_ingredients(recipe['main_ingredients'])}")
    print(f"    调料: {format_ingredients(recipe['seasonings'])}")
    print("\n  做法:")
    for i, step in enumerate(recipe["steps"], 1):
        print(f"    {i}. {step}")
    print(f"\n  标签: {', '.join(recipe['tags'])}")


def main():
    recipes, categories = load_recipes()

    print("\n" + "="*50)
    print("        🍳 智能菜谱助手")
    print("="*50)
    print(f"\n  收录菜谱: {len(recipes)} 道")
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
                results = find_matching_recipes(recipes, ingredients=ingredients)
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
            print("\n选择口味: 酸甜/麻辣/清淡/咸鲜/微辣/爽脆/蒜香/咖喱香")
            taste = input("输入口味: ").strip()
            if taste:
                results = find_matching_recipes(recipes, taste=taste)
                if results:
                    print(f"\n找到 {len(results)} 道匹配的菜谱:")
                    for r in results:
                        print(f"\n  • {r['name']} - {r['difficulty']} | {r['time']}")
                        print(f"    主料: {format_ingredients(r['main_ingredients'])}")
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
                needed = generate_shopping_list(selected, owned)
                if needed:
                    print(f"\n购物清单 ({len(needed)}项):")
                    for ing, info in sorted(needed.items()):
                        amount = f" {info['amount']}" if info["amount"] else ""
                        suffix = f" ×{info['dishes']}道菜" if info["dishes"] > 1 else ""
                        print(f"  □ {ing}{amount}{suffix}")
                else:
                    print("\n✅ 你已经拥有所有需要的食材！")

        elif choice == "4":
            print(f"\n所有菜谱 ({len(recipes)}道):")
            for r in recipes:
                print(f"\n  • {r['name']} - {r['category']} | {r['difficulty']} | {r['time']}")
                print(f"    主料: {format_ingredients(r['main_ingredients'])}")

        elif choice == "5":
            print("\n再见！")
            break

        else:
            print("无效选择，请输入 1-5")


if __name__ == "__main__":
    main()

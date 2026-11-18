#!/usr/bin/env python3
"""
菜谱数据导入工具。

用法：
  python scripts/import_recipes.py                    # 导入全部种子（增量、幂等）
  python scripts/import_recipes.py path/to/new.json   # 导入指定文件
  python scripts/import_recipes.py --rebuild          # 编辑过种子后删库重建
  python scripts/import_recipes.py --stats            # 只看库内统计

seed 文件格式（与 .mimocode/.../recipes.json 相同，食材支持带用量）：
{
  "recipes": [
    {
      "id": 101,
      "name": "鱼香茄子",
      "category": "家常菜",              # 家常菜/川菜/素菜/海鲜/凉菜/汤类/主食
      "taste": ["咸鲜", "微辣"],
      "difficulty": "中等",              # 简单/中等/较难
      "time": "30分钟",
      "servings": 2,                     # 份量（可选，默认 2）
      "main_ingredients": [
        {"name": "茄子", "amount": "2根"},   # 也兼容旧写法 "茄子"
        {"name": "猪肉末", "amount": "100克"}
      ],
      "seasonings": [{"name": "豆瓣酱", "amount": "1勺"}],
      "steps": ["...", "..."],
      "tags": ["下饭菜"]
    }
  ],
  "ingredient_categories": {"蔬菜": ["茄子"]}   # 新食材记得补分类，购物清单靠它分组
}
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import recipe_store  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="菜谱数据导入工具")
    parser.add_argument("files", nargs="*", help="要导入的 seed JSON 文件（默认导入全部种子）")
    parser.add_argument("--rebuild", action="store_true", help="删库重建（编辑种子后刷新用）")
    parser.add_argument("--stats", action="store_true", help="只显示库内统计")
    parser.add_argument("--quiet", action="store_true", help="只显示汇总")
    args = parser.parse_args()

    if args.stats:
        s = recipe_store.stats()
        print(f"库内共 {s['recipes']} 道菜谱，{s['ingredients']} 种食材分类")
        for cat, n in s["by_category"].items():
            print(f"  {cat}: {n} 道")
        return 0

    if args.rebuild:
        result = recipe_store.rebuild()
        print("已删库重建。")
    elif args.files:
        result = {"files": 0, "imported": 0, "updated": 0, "failed": 0, "errors": []}
        for path in args.files:
            s = recipe_store.import_file(path)
            result["files"] += 1
            result["imported"] += s["imported"]
            result["updated"] += s["updated"]
            result["failed"] += s["failed"]
            result["errors"].extend(s["errors"])
    else:
        result = recipe_store.import_all()

    if not args.quiet:
        for err in result["errors"]:
            print(f"  ❌ {err}")

    print(
        f"导入完成：{result['files']} 个文件 | "
        f"新增 {result['imported']} | 更新 {result['updated']} | 失败 {result['failed']}"
    )

    s = recipe_store.stats()
    print(
        f"库内共 {s['recipes']} 道菜谱 | "
        + " | ".join(f"{k} {v}" for k, v in s["by_category"].items())
    )

    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())

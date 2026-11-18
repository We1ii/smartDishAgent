"""
菜谱存储层：SQLite 主库 + 种子 JSON 导入。

数据流：
  种子文件 ──import──> data/recipes.db ──load_all──> core.load_recipes()
    ├─ .mimocode/skills/recipe-assistant/recipes.json   （原始 20 道）
    └─ data/seed/*.json                                （批量生成 / 外部数据集）

设计：
  - 主库 data/recipes.db 是生成产物，.gitignore 忽略（data/*.db）；种子 JSON 入库
  - 首次访问自动导入全部种子（ensure_db），日常使用无需手动步骤
  - 每条菜谱经 Pydantic 校验；食材归一化为 {"name", "amount"} 对象（兼容旧的纯字符串）
  - 按 name 主键 upsert——重复导入幂等，新种子文件随时可增量加
"""
import json
import os
import sqlite3
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 可用环境变量覆盖库路径（测试隔离 / 自定义数据目录用）
DB_PATH = os.environ.get("RECIPE_DB_PATH") or os.path.join(BASE_DIR, "data", "recipes.db")
ORIGINAL_SEED = os.path.join(
    BASE_DIR, ".mimocode", "skills", "recipe-assistant", "recipes.json"
)
SEED_DIR = os.path.join(BASE_DIR, "data", "seed")

# 与 UI 筛选器保持一致的枚举——导入时严格校验，脏数据进不来
KNOWN_CATEGORIES = ["家常菜", "川菜", "素菜", "海鲜", "凉菜", "汤类", "主食"]
KNOWN_DIFFICULTIES = ["简单", "中等", "较难"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id                INTEGER,
    name              TEXT PRIMARY KEY,
    category          TEXT NOT NULL,
    taste             TEXT NOT NULL DEFAULT '[]',
    difficulty        TEXT NOT NULL,
    time              TEXT NOT NULL,
    servings          INTEGER NOT NULL DEFAULT 2,
    main_ingredients  TEXT NOT NULL DEFAULT '[]',
    seasonings        TEXT NOT NULL DEFAULT '[]',
    steps             TEXT NOT NULL DEFAULT '[]',
    tags              TEXT NOT NULL DEFAULT '[]',
    source            TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS ingredient_categories (
    category   TEXT NOT NULL,
    ingredient TEXT NOT NULL,
    PRIMARY KEY (category, ingredient)
);
"""


# ---------- 数据模型 ----------

class Recipe(BaseModel):
    """单条菜谱的校验模型（seed 文件里 main_ingredients 可以是字符串或对象，导入时统一归一化）"""
    id: Optional[int] = None
    name: str = Field(..., min_length=1, max_length=50)
    category: str
    taste: list[str] = []
    difficulty: Literal["简单", "中等", "较难"]
    time: str = Field(..., min_length=1, max_length=30)
    servings: int = Field(2, ge=1, le=20)
    main_ingredients: list[Union[str, dict]] = []
    seasonings: list[Union[str, dict]] = []
    steps: list[str] = []
    tags: list[str] = []


def normalize_ingredients(raw):
    """把食材归一化为 [{"name": str, "amount": str}]；兼容旧 schema 的纯字符串"""
    out = []
    for item in raw or []:
        if isinstance(item, str):
            name = item.strip()
            if name:
                out.append({"name": name, "amount": ""})
        elif isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            if name:
                amount = str(item.get("amount", "") or "").strip()
                out.append({"name": name, "amount": amount})
    return out


# ---------- 存储操作 ----------

def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _validate(data, source):
    """校验单条菜谱，返回 (recipe_dict, None) 或 (None, 错误描述)"""
    try:
        recipe = Recipe.model_validate(data)
    except Exception as e:
        return None, f"{source}: 《{data.get('name', '?')}》 校验失败 -> {e}"

    if recipe.category not in KNOWN_CATEGORIES:
        return None, f"{source}: 《{recipe.name}》 未知分类 {recipe.category!r}（允许: {KNOWN_CATEGORIES}）"
    if not recipe.steps:
        return None, f"{source}: 《{recipe.name}》 缺少做法步骤"
    if not recipe.main_ingredients:
        return None, f"{source}: 《{recipe.name}》 缺少主料"

    return {
        "id": recipe.id,
        "name": recipe.name,
        "category": recipe.category,
        "taste": list(recipe.taste),
        "difficulty": recipe.difficulty,
        "time": recipe.time,
        "servings": recipe.servings,
        "main_ingredients": normalize_ingredients(recipe.main_ingredients),
        "seasonings": normalize_ingredients(recipe.seasonings),
        "steps": list(recipe.steps),
        "tags": list(recipe.tags),
    }, None


def import_file(path, source=None):
    """
    导入一个种子 JSON 文件（幂等，按 name upsert）。
    返回 {"file", "imported", "updated", "failed", "errors": [...]}
    """
    source = source or os.path.basename(path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    recipes = data.get("recipes", [])
    categories = data.get("ingredient_categories", {})

    stats = {"file": source, "imported": 0, "updated": 0, "failed": 0, "errors": []}

    with _connect() as conn:
        # 先看 name 是否已存在，统计 imported/updated
        for entry in recipes:
            recipe, err = _validate(entry, source)
            if err:
                stats["failed"] += 1
                stats["errors"].append(err)
                continue

            exists = conn.execute(
                "SELECT 1 FROM recipes WHERE name = ?", (recipe["name"],)
            ).fetchone()
            conn.execute(
                "INSERT INTO recipes (id, name, category, taste, difficulty, time, servings,"
                " main_ingredients, seasonings, steps, tags, source)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(name) DO UPDATE SET"
                "  id=excluded.id, category=excluded.category, taste=excluded.taste,"
                "  difficulty=excluded.difficulty, time=excluded.time, servings=excluded.servings,"
                "  main_ingredients=excluded.main_ingredients, seasonings=excluded.seasonings,"
                "  steps=excluded.steps, tags=excluded.tags, source=excluded.source",
                (
                    recipe["id"], recipe["name"], recipe["category"],
                    json.dumps(recipe["taste"], ensure_ascii=False),
                    recipe["difficulty"], recipe["time"], recipe["servings"],
                    json.dumps(recipe["main_ingredients"], ensure_ascii=False),
                    json.dumps(recipe["seasonings"], ensure_ascii=False),
                    json.dumps(recipe["steps"], ensure_ascii=False),
                    json.dumps(recipe["tags"], ensure_ascii=False),
                    source,
                ),
            )
            stats["updated" if exists else "imported"] += 1

        # 食材分类合并（union）
        for cat, items in categories.items():
            for ing in items or []:
                conn.execute(
                    "INSERT OR IGNORE INTO ingredient_categories (category, ingredient)"
                    " VALUES (?, ?)",
                    (cat, str(ing).strip()),
                )

    return stats


def seed_files():
    """全部种子文件：原始 20 道 + data/seed/*.json（按文件名排序保证确定性）"""
    files = []
    if os.path.exists(ORIGINAL_SEED):
        files.append(ORIGINAL_SEED)
    if os.path.isdir(SEED_DIR):
        files.extend(
            os.path.join(SEED_DIR, f)
            for f in sorted(os.listdir(SEED_DIR))
            if f.endswith(".json")
        )
    return files


def ensure_db():
    """主库不存在或为空时，自动导入全部种子"""
    if os.path.exists(DB_PATH):
        with _connect() as conn:
            if conn.execute("SELECT COUNT(*) AS n FROM recipes").fetchone()["n"] > 0:
                return
    import_all()


def import_all():
    """导入全部种子文件，返回汇总统计"""
    all_stats = {"files": 0, "imported": 0, "updated": 0, "failed": 0, "errors": []}
    for path in seed_files():
        s = import_file(path)
        all_stats["files"] += 1
        all_stats["imported"] += s["imported"]
        all_stats["updated"] += s["updated"]
        all_stats["failed"] += s["failed"]
        all_stats["errors"].extend(s["errors"])
    return all_stats


def rebuild():
    """删库重建（编辑种子后用它刷新）"""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    return import_all()


def load_all():
    """读出全部菜谱与食材分类，返回 (recipes, categories)——core.load_recipes 的数据源"""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM recipes ORDER BY rowid").fetchall()
        cat_rows = conn.execute(
            "SELECT category, ingredient FROM ingredient_categories"
        ).fetchall()

    recipes = []
    for r in rows:
        recipes.append(
            {
                "id": r["id"],
                "name": r["name"],
                "category": r["category"],
                "taste": json.loads(r["taste"]),
                "difficulty": r["difficulty"],
                "time": r["time"],
                "servings": r["servings"],
                "main_ingredients": json.loads(r["main_ingredients"]),
                "seasonings": json.loads(r["seasonings"]),
                "steps": json.loads(r["steps"]),
                "tags": json.loads(r["tags"]),
            }
        )

    categories = {}
    for r in cat_rows:
        categories.setdefault(r["category"], []).append(r["ingredient"])

    return recipes, categories


def stats():
    """给 CLI/脚本用的库内统计"""
    with _connect() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM recipes").fetchone()["n"]
        by_cat = {
            r["category"]: r["c"]
            for r in conn.execute(
                "SELECT category, COUNT(*) AS c FROM recipes GROUP BY category ORDER BY c DESC"
            )
        }
        n_ings = conn.execute(
            "SELECT COUNT(*) AS n FROM ingredient_categories"
        ).fetchone()["n"]
    return {"recipes": n, "by_category": by_cat, "ingredients": n_ings}

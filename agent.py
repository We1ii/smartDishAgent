"""
AI Agent：基于 OpenAI 兼容接口 + Function Calling 的菜谱助手。

架构：
  用户输入 -> LLM（决定调用哪个工具）-> 工具执行（core.py 规则引擎）
           -> 结果回填给 LLM -> ...（最多 MAX_TURNS 轮）-> 最终自然语言回答

环境变量（推荐写在项目根目录的 .env 文件里，该文件已被 .gitignore 忽略）：
  LLM_API_KEY   必填，API Key（也兼容 OPENAI_API_KEY）
  LLM_BASE_URL  选填，默认 https://api.xiaomimimo.com/v1（小米 MiMo）
  LLM_MODEL     选填，默认 mimo-v2.6-flash

用法（生成器，产出事件供 UI 渲染）：
  for event in run_agent("我有鸡蛋和番茄能做什么", history):
      event == {"type": "tool", "name", "args", "brief"}   # 工具调用过程
      event == {"type": "answer", "content": "..."}         # 最终回答
"""
import json
import os

# 优先读取项目根目录的 .env（不上传 GitHub），环境变量已存在时不会被覆盖
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

from core import (
    load_recipes,
    find_matching_recipes,
    get_recipe_by_name,
    generate_shopping_list,
    get_category,
)

DEFAULT_BASE_URL = "https://api.xiaomimimo.com/v1"
DEFAULT_MODEL = "mimo-v2.6-flash"
MAX_TURNS = 6  # 最多连续调用工具的轮数，防止死循环

SYSTEM_PROMPT = """你是「智能菜谱助手」的 AI 主厨，帮助用户根据现有食材推荐菜谱、查看做法、生成购物清单。

你有三个工具可用：
- search_recipes：按食材/口味/分类/难度搜索菜谱（返回简要列表）
- get_recipe_detail：获取某道菜的完整食材和做法步骤
- generate_shopping_list：根据选中的菜和用户已有的食材，生成购物清单

规则：
1. 用户给出食材或口味偏好时，先调用 search_recipes，不要凭记忆报菜名。
2. 用户问某道菜怎么做时，先调用 get_recipe_detail 再回答。
3. 用户要购物清单时，调用 generate_shopping_list；如果没给菜名，先用 search_recipes 推荐再问用户确认。
4. 所有菜名必须来自工具返回结果，禁止编造菜谱。
5. 工具没有命中时，如实告知并给出放宽条件的建议。
6. 用中文回答，语气亲切简洁，适当使用 emoji。
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_recipes",
            "description": "按食材、口味、分类、难度搜索菜谱，返回匹配菜谱的简要列表（名称、分类、难度、时间、口味）。用户给出食材或口味偏好时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ingredients": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "用户现有的食材，如 [\"鸡蛋\", \"番茄\"]",
                    },
                    "tastes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "口味偏好，如 [\"酸甜\", \"麻辣\"]",
                    },
                    "category": {
                        "type": "string",
                        "description": "分类筛选：家常菜/川菜/素菜/海鲜/凉菜/汤类/主食，可选",
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["简单", "中等", "较难"],
                        "description": "难度筛选，可选",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最多返回条数，默认 10",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recipe_detail",
            "description": "按菜名获取某道菜的完整信息，包括主料、调料、口味、做法步骤。用户想知道某道菜怎么做时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "菜名，必须来自 search_recipes 的返回结果"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_shopping_list",
            "description": "根据用户选中的菜谱和已有的食材，生成需要购买的食材清单，并按食材分类分组。",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipe_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要做的菜名列表，必须来自 search_recipes 的返回结果",
                    },
                    "owned_ingredients": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "用户已经有的食材，没有则传空数组",
                    },
                },
                "required": ["recipe_names"],
            },
        },
    },
]


def is_configured():
    """检查 API 配置是否完整，返回 (ok, error_message)"""
    if not (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")):
        return False, (
            "未配置 API Key。请在项目根目录创建 `.env` 文件（已默认忽略上传）：\n\n"
            "```bash\n"
            "copy .env.example .env   # 复制模板\n"
            "```\n\n"
            "然后把 `.env` 里的 `LLM_API_KEY=你的APIKey填这里` 改成真实 Key，重启应用即可。\n\n"
            "（也可以设置系统环境变量 `LLM_API_KEY`，优先级与 `.env` 相同）"
        )
    return True, ""


def _get_client():
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("缺少 openai 依赖，请先执行：pip install openai")
    return OpenAI(
        api_key=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL") or DEFAULT_BASE_URL,
    )


def _tool_brief(name, args):
    """工具调用的单行摘要，用于 UI 展示"""
    if name == "search_recipes":
        parts = []
        if args.get("ingredients"):
            parts.append("食材=" + "、".join(args["ingredients"]))
        if args.get("tastes"):
            parts.append("口味=" + "、".join(args["tastes"]))
        if args.get("category"):
            parts.append("分类=" + args["category"])
        if args.get("difficulty"):
            parts.append("难度=" + args["difficulty"])
        return " ".join(parts) or "全量搜索"
    if name == "get_recipe_detail":
        return f"菜名={args.get('name', '')}"
    if name == "generate_shopping_list":
        return "菜=" + "、".join(args.get("recipe_names") or [])
    return ""


def execute_tool(name, args):
    """执行工具并返回可 JSON 序列化的结果"""
    recipes, categories = load_recipes()

    if name == "search_recipes":
        results = find_matching_recipes(
            recipes,
            ingredients=args.get("ingredients"),
            taste=args.get("tastes"),
            category=args.get("category"),
            difficulty=args.get("difficulty"),
        )
        max_n = int(args.get("max_results") or 10)
        brief = [
            {
                "name": r["name"],
                "category": r["category"],
                "difficulty": r["difficulty"],
                "time": r["time"],
                "taste": r["taste"],
            }
            for r in results[:max_n]
        ]
        return {"total": len(results), "recipes": brief}

    if name == "get_recipe_detail":
        recipe = get_recipe_by_name(recipes, args.get("name", ""))
        if not recipe:
            return {
                "error": f"未找到菜谱：{args.get('name')}",
                "hint": "请先调用 search_recipes 获取准确菜名",
            }
        return recipe

    if name == "generate_shopping_list":
        names = args.get("recipe_names") or []
        selected = [r for r in recipes if r["name"] in names]
        not_found = [n for n in names if n not in {r["name"] for r in selected}]
        needed = generate_shopping_list(selected, args.get("owned_ingredients") or [])

        grouped = {}
        for ing, count in needed.items():
            cat = get_category(ing, categories)
            grouped.setdefault(cat, []).append({"ingredient": ing, "dishes": count})

        out = {
            "selected_recipes": [r["name"] for r in selected],
            "shopping_list": grouped,
        }
        if not_found:
            out["not_found"] = not_found
        if not needed:
            out["note"] = "已有食材齐全，无需购买"
        return out

    return {"error": f"未知工具: {name}"}


def run_agent(user_message, history=None):
    """
    Agent 主循环：LLM <-> 工具，最多 MAX_TURNS 轮。

    history: [{"role": "user"|"assistant", "content": str}, ...] 之前的对话
    产出事件：{"type": "tool", ...} / {"type": "answer", ...}
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in (history or [])[-10:]:  # 只保留最近 10 轮，控制上下文长度
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})

    client = _get_client()
    model = os.getenv("LLM_MODEL") or DEFAULT_MODEL

    for _ in range(MAX_TURNS):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            temperature=0.7,
        )
        msg = resp.choices[0].message

        # 没有工具调用 -> 最终回答
        if not msg.tool_calls:
            yield {"type": "answer", "content": msg.content or ""}
            return

        # 先把 assistant 消息（含 tool_calls）回填
        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        # 逐个执行工具并回填结果
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            yield {
                "type": "tool",
                "name": tc.function.name,
                "args": args,
                "brief": _tool_brief(tc.function.name, args),
            }

            try:
                result = execute_tool(tc.function.name, args)
            except Exception as e:  # 工具执行失败不让整个对话崩掉
                result = {"error": str(e)}

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

    # 轮数耗尽兜底
    yield {"type": "answer", "content": "抱歉，这次思考的步骤太多了，请换个更具体的问法再试试～"}

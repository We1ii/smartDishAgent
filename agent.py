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
      event == {"type": "delta", "content": "..."}                  # 流式 token 增量
      event == {"type": "tool", "name", "args", "brief"}            # 工具调用过程
      event == {"type": "answer", "content", "usage"}               # 最终回答（含 token 统计）
      event == {"type": "answer", "content", "error": True}         # 调用失败的用户提示

可靠性保障：
  - 入参校验：工具参数经 Pydantic 模型校验，非法参数回填给模型自动纠正
  - 重试退避：限流/网络/5xx 指数退避重试 3 次（见 llm_utils.with_retry）
  - 结构化日志：每次请求、工具调用、token 用量写入 logs/agent.log（1MB×3 轮转）
"""
import json
import os
import time
from typing import Literal, Optional

# 优先读取项目根目录的 .env（不上传 GitHub），环境变量已存在时不会被覆盖
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

from pydantic import BaseModel, Field, ValidationError

from llm_utils import get_logger, with_retry, classify_error
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

# ---------- 工具入参模型（Pydantic 校验，同时生成给模型看的 JSON Schema） ----------

class SearchArgs(BaseModel):
    """search_recipes 的入参"""
    ingredients: list[str] = Field(
        default_factory=list,
        description='用户现有的食材，如 ["鸡蛋", "番茄"]',
    )
    tastes: list[str] = Field(
        default_factory=list,
        description='口味偏好，如 ["酸甜", "麻辣"]',
    )
    category: Optional[Literal[
        "家常菜", "川菜", "素菜", "海鲜", "凉菜", "汤类", "主食"
    ]] = Field(None, description="分类筛选，可选")
    difficulty: Optional[Literal["简单", "中等", "较难"]] = Field(
        None, description="难度筛选，可选",
    )
    max_results: int = Field(
        10, ge=1, le=50,
        description="最多返回条数，默认 10，上限 50",
    )


class DetailArgs(BaseModel):
    """get_recipe_detail 的入参"""
    name: str = Field(
        ..., min_length=1, max_length=50,
        description="菜名，必须来自 search_recipes 的返回结果",
    )


class ShoppingArgs(BaseModel):
    """generate_shopping_list 的入参"""
    recipe_names: list[str] = Field(
        ..., min_length=1,
        description="要做的菜名列表，必须来自 search_recipes 的返回结果",
    )
    owned_ingredients: list[str] = Field(
        default_factory=list,
        description="用户已经有的食材，没有则传空数组",
    )


# name -> (工具描述, 入参模型)
_TOOL_META = {
    "search_recipes": (
        "按食材、口味、分类、难度搜索菜谱，返回匹配菜谱的简要列表（名称、分类、难度、时间、口味）。"
        "用户给出食材或口味偏好时调用。",
        SearchArgs,
    ),
    "get_recipe_detail": (
        "按菜名获取某道菜的完整信息，包括主料、调料、口味、做法步骤。"
        "用户想知道某道菜怎么做时调用。",
        DetailArgs,
    ),
    "generate_shopping_list": (
        "根据用户选中的菜谱和已有的食材，生成需要购买的食材清单，并按食材分类分组。",
        ShoppingArgs,
    ),
}


def _build_tools():
    """从 Pydantic 模型生成 OpenAI function calling 的 TOOLS 定义（单一数据源，避免 schema 漂移）"""
    tools = []
    for name, (desc, model) in _TOOL_META.items():
        schema = model.model_json_schema()
        schema.pop("title", None)  # 顶层 title 对模型无意义，去掉让 schema 更干净
        tools.append({
            "type": "function",
            "function": {"name": name, "description": desc, "parameters": schema},
        })
    return tools


TOOLS = _build_tools()
TOOL_ARGS = {name: model for name, (_, model) in _TOOL_META.items()}


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
        for ing, info in needed.items():
            cat = get_category(ing, categories)
            grouped.setdefault(cat, []).append(
                {"ingredient": ing, "dishes": info["dishes"], "amount": info["amount"]}
            )

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


def _create_stream(client, model, messages, logger):
    """
    创建流式响应（stream=True）。
    优先带 stream_options={"include_usage": True} 拿 token 统计；
    若 API 不支持该参数（部分兼容网关会 400），自动降级为无 usage 的流式。
    """
    base = dict(model=model, messages=messages, tools=TOOLS, temperature=0.7, stream=True)
    try:
        return with_retry(
            lambda: client.chat.completions.create(
                **base, stream_options={"include_usage": True}
            ),
            retries=3, base_delay=1.0, logger=logger,
        )
    except Exception as e:
        name = type(e).__name__
        status = getattr(e, "status_code", None)
        is_bad_request = name in ("BadRequestError", "UnprocessableEntityError") or (
            name == "APIStatusError" and isinstance(status, int) and 400 <= status < 500
        )
        if not is_bad_request:
            raise  # 认证/限流/网络等错误交给 with_retry 已经处理过，这里直接抛
        logger.warning("stream_options 不被支持，降级为无 usage 流式: %s", e)
        return with_retry(
            lambda: client.chat.completions.create(**base),
            retries=3, base_delay=1.0, logger=logger,
        )


def run_agent(user_message, history=None):
    """
    Agent 主循环：LLM <-> 工具，最多 MAX_TURNS 轮，全程流式。

    history: [{"role": "user"|"assistant", "content": str}, ...] 之前的对话
    产出事件：
      {"type": "delta", "content"}                                # 流式增量
      {"type": "tool", "name", "args", "brief"}
      {"type": "answer", "content", "usage": {prompt, completion, turns}}  # usage 可能为 None
      {"type": "answer", "content", "error": True}                 # 调用失败的用户提示
    """
    logger = get_logger()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in (history or [])[-10:]:  # 只保留最近 10 轮，控制上下文长度
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})

    client = _get_client()
    model = os.getenv("LLM_MODEL") or DEFAULT_MODEL
    total_prompt = total_completion = 0

    for turn in range(MAX_TURNS):
        logger.info(
            "LLM请求(流式) turn=%d model=%s messages=%d user=%r",
            turn + 1, model, len(messages), user_message[:50],
        )
        t0 = time.time()

        try:
            stream = _create_stream(client, model, messages, logger)
        except Exception as e:
            logger.error("LLM调用失败 %s: %s", type(e).__name__, e)
            yield {"type": "answer", "content": classify_error(e), "error": True}
            return

        # ---- 消费流：边收边 yield 增量，同时聚合 content 与 tool_calls ----
        content_parts = []
        tool_acc = {}  # index -> {id, name, args}
        finish_reason = None
        stream_usage = None

        try:
            for chunk in stream:
                u = getattr(chunk, "usage", None)
                if u is not None:
                    stream_usage = u

                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue  # include_usage 模式的 usage chunk 没有 choices
                choice = choices[0]

                delta = getattr(choice, "delta", None)
                if delta is not None:
                    piece = getattr(delta, "content", None)
                    if piece:
                        content_parts.append(piece)
                        yield {"type": "delta", "content": piece}
                    for tdc in (getattr(delta, "tool_calls", None) or []):
                        idx = getattr(tdc, "index", 0) or 0
                        acc = tool_acc.setdefault(idx, {"id": "", "name": "", "args": ""})
                        if getattr(tdc, "id", None) and not acc["id"]:
                            acc["id"] = tdc.id
                        fn = getattr(tdc, "function", None)
                        if fn is not None:
                            # OpenAI 协议：name 在首个 delta 完整给出，args 分片到达
                            if getattr(fn, "name", None) and not acc["name"]:
                                acc["name"] = fn.name
                            if getattr(fn, "arguments", None):
                                acc["args"] += fn.arguments

                fin = getattr(choice, "finish_reason", None)
                if fin:
                    finish_reason = fin
        except Exception as e:
            # 流中途断掉无法原地重试（会重复吐字），直接给出提示
            logger.error("流式中断 %s: %s", type(e).__name__, e)
            yield {"type": "answer", "content": classify_error(e), "error": True}
            return

        if stream_usage is not None:
            total_prompt += getattr(stream_usage, "prompt_tokens", 0) or 0
            total_completion += getattr(stream_usage, "completion_tokens", 0) or 0
        logger.info(
            "LLM响应 turn=%d 耗时=%.1fs finish=%s tokens=%s/%s",
            turn + 1, time.time() - t0, finish_reason,
            getattr(stream_usage, "prompt_tokens", "-") if stream_usage else "-",
            getattr(stream_usage, "completion_tokens", "-") if stream_usage else "-",
        )

        full_content = "".join(content_parts)
        tool_calls = [tool_acc[i] for i in sorted(tool_acc)]

        # 数据不完整（声称 tool_calls 却没收到）——宁可报错也不发空调用
        if finish_reason == "tool_calls" and not tool_calls:
            logger.error("工具调用流数据不完整 turn=%d", turn + 1)
            yield {"type": "answer", "content": "⚠️ 模型返回的工具调用数据不完整，请重试。", "error": True}
            return

        # ---- 最终回答（无工具调用）----
        if not tool_calls:
            usage_out = None
            if total_prompt or total_completion:
                usage_out = {
                    "prompt": total_prompt,
                    "completion": total_completion,
                    "turns": turn + 1,
                }
            logger.info("最终回答 turn=%d 长度=%d", turn + 1, len(full_content))
            yield {"type": "answer", "content": full_content, "usage": usage_out}
            return

        # ---- 工具轮：回填 assistant（含聚合后的 tool_calls）----
        messages.append(
            {
                "role": "assistant",
                "content": full_content or None,
                "tool_calls": [
                    {
                        "id": t["id"] or f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": t["name"],
                            "arguments": t["args"] or "{}",
                        },
                    }
                    for i, t in enumerate(tool_calls)
                ],
            }
        )

        for i, t in enumerate(tool_calls):
            tool_name = t["name"]
            call_id = t["id"] or f"call_{i}"

            # 1) Pydantic 入参校验：非法参数不执行，回填错误让模型自己纠正
            arg_model = TOOL_ARGS.get(tool_name)
            try:
                if arg_model is None:
                    raise ValueError(f"未知工具: {tool_name}")
                args = arg_model.model_validate_json(t["args"] or "{}").model_dump()
            except (ValidationError, ValueError) as e:
                logger.warning("入参校验失败 tool=%s error=%s", tool_name, str(e).replace("\n", " | "))
                yield {
                    "type": "tool",
                    "name": tool_name,
                    "args": {},
                    "brief": "❌ 入参校验失败，已让模型自动修正",
                }
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(
                            {
                                "error": f"入参校验失败: {e}",
                                "hint": "请检查参数类型、必填项和取值范围后重新调用该工具",
                            },
                            ensure_ascii=False,
                        ),
                    }
                )
                continue

            # 2) 执行工具
            logger.info(
                "工具调用 tool=%s args=%s",
                tool_name, json.dumps(args, ensure_ascii=False)[:300],
            )
            yield {
                "type": "tool",
                "name": tool_name,
                "args": args,
                "brief": _tool_brief(tool_name, args),
            }
            try:
                result = execute_tool(tool_name, args)
            except Exception as e:  # 工具执行失败不让整个对话崩掉
                logger.error("工具执行异常 tool=%s: %s", tool_name, e)
                result = {"error": str(e)}

            logger.info(
                "工具结果 tool=%s status=%s",
                tool_name, "error" if "error" in result else "ok",
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

    # 轮数耗尽兜底
    logger.warning("轮数耗尽 MAX_TURNS=%d，返回兜底提示", MAX_TURNS)
    yield {"type": "answer", "content": "抱歉，这次思考的步骤太多了，请换个更具体的问法再试试～"}

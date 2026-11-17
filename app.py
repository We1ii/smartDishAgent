import streamlit as st

from core import (
    load_recipes,
    find_matching_recipes,
    generate_shopping_list,
    get_category,
)

# 页面配置
st.set_page_config(
    page_title="智能菜谱助手",
    page_icon="🍳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义样式
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #FF6B35;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .recipe-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 15px;
        color: white;
        margin-bottom: 1rem;
    }
    .tag {
        display: inline-block;
        background: rgba(255,255,255,0.2);
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.8rem;
        margin: 0.2rem;
    }
    .stButton > button {
        background: linear-gradient(135deg, #FF6B35 0%, #F7931E 100%);
        color: white;
        border: none;
        padding: 0.5rem 2rem;
        border-radius: 25px;
        font-weight: bold;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #F7931E 0%, #FF6B35 100%);
    }
    div[data-testid="stExpander"] {
        border: 1px solid #FF6B35;
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)


# 数据加载与匹配逻辑见 core.py；Agent 对话逻辑见 agent.py

# 加载数据
recipes, categories = load_recipes()

# 侧边栏
with st.sidebar:
    st.markdown("## 🍳 功能导航")
    page = st.radio(
        "选择功能",
        ["🏠 首页", "🤖 AI 助手", "🔍 按食材找菜", "🌶️ 按口味找菜", "📝 生成购物清单", "📖 菜谱大全"],
        label_visibility="collapsed"
    )

    st.markdown("---")
    st.markdown("### 📊 数据统计")
    st.info(f"收录菜谱: **{len(recipes)}** 道")
    st.info(f"食材种类: **{sum(len(v) for v in categories.values())}** 种")

# 主页面
st.markdown('<div class="main-header">🍳 智能菜谱助手</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">根据食材和口味，为你推荐最合适的菜谱</div>', unsafe_allow_html=True)

# 首页
if page == "🏠 首页":
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### 🥘 食材推荐")
        st.write("告诉我你有什么食材，我来推荐能做的菜")

    with col2:
        st.markdown("### 🌶️ 口味筛选")
        st.write("想吃什么口味？酸甜、麻辣、清淡...")

    with col3:
        st.markdown("### 📝 购物清单")
        st.write("选择想做的菜，自动生成购物清单")

    st.markdown("---")
    st.markdown("### 🔥 热门菜谱")

    # 显示热门菜谱
    popular_recipes = ["番茄炒蛋", "宫保鸡丁", "麻婆豆腐", "红烧肉", "可乐鸡翅"]
    cols = st.columns(5)
    for col, name in zip(cols, popular_recipes):
        recipe = next((r for r in recipes if r["name"] == name), None)
        if recipe:
            with col:
                with st.container():
                    st.markdown(f"**{recipe['name']}**")
                    st.caption(f"{recipe['difficulty']} | {recipe['time']}")
                    st.caption(f"{' '.join(recipe['taste'])}")

# AI 助手（Agent + 大模型）
elif page == "🤖 AI 助手":
    from agent import is_configured, run_agent

    st.markdown("### 🤖 AI 主厨")
    st.caption("用自然语言和我对话：'我有鸡蛋和番茄能做什么？' / '宫保鸡丁怎么做？' / '帮我列购物清单'")

    ok, err = is_configured()
    if not ok:
        st.error(err)
    else:
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        # 渲染历史消息
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        prompt = st.chat_input("试试：我有鸡蛋和番茄，能做什么？")
        if prompt:
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                answer = ""
                try:
                    # 先跑 Agent 循环，工具调用过程实时显示在 status 里
                    with st.status("🍳 AI 主厨思考中...", expanded=True) as status:
                        events = run_agent(
                            prompt,
                            history=st.session_state.chat_history[:-1],
                        )
                        for ev in events:
                            if ev["type"] == "tool":
                                status.write(f"🔧 调用工具 `{ev['name']}` — {ev['brief']}")
                            elif ev["type"] == "answer":
                                answer = ev["content"]
                    if answer:
                        st.markdown(answer)
                    else:
                        answer = "模型没有返回内容，请重试。"
                        st.warning(answer)
                except Exception as e:
                    answer = f"⚠️ 调用出错：{e}"
                    st.error(answer)

                st.session_state.chat_history.append({"role": "assistant", "content": answer})

        if st.session_state.chat_history:
            if st.button("🗑️ 清空对话"):
                st.session_state.chat_history = []
                st.rerun()

# 按食材找菜
elif page == "🔍 按食材找菜":
    st.markdown("### 🥕 输入你现有的食材")

    # 食材选择
    all_ingredients = []
    for items in categories.values():
        all_ingredients.extend(items)
    all_ingredients = sorted(set(all_ingredients))

    selected_ingredients = st.multiselect(
        "选择你有的食材（可多选）",
        all_ingredients,
        placeholder="点击选择或输入..."
    )

    # 额外输入
    custom_ingredients = st.text_input("或者手动输入食材（用逗号分隔）", placeholder="如：鸡蛋, 番茄, 牛肉")
    if custom_ingredients:
        custom_list = [x.strip() for x in custom_ingredients.split(",") if x.strip()]
        selected_ingredients = list(set(selected_ingredients + custom_list))

    # 筛选条件
    col1, col2 = st.columns(2)
    with col1:
        filter_taste = st.selectbox("筛选口味", ["不限", "酸甜", "麻辣", "清淡", "咸鲜", "微辣"])
    with col2:
        filter_difficulty = st.selectbox("筛选难度", ["不限", "简单", "中等", "较难"])

    if st.button("🔍 查找推荐菜谱", type="primary"):
        if selected_ingredients:
            taste = None if filter_taste == "不限" else filter_taste
            difficulty = None if filter_difficulty == "不限" else filter_difficulty

            results = find_matching_recipes(recipes, selected_ingredients, taste, difficulty=difficulty)

            if results:
                st.markdown(f"### 找到 {len(results)} 道匹配的菜谱")
                for recipe in results[:10]:
                    with st.expander(f"**{recipe['name']}** - {recipe['category']} | {recipe['difficulty']} | {recipe['time']}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("**食材**")
                            st.write(f"主料: {', '.join(recipe['main_ingredients'])}")
                            st.write(f"调料: {', '.join(recipe['seasonings'])}")
                        with col2:
                            st.markdown("**口味与标签**")
                            st.write(f"口味: {', '.join(recipe['taste'])}")
                            st.write(f"标签: {', '.join(recipe['tags'])}")

                        st.markdown("**做法步骤**")
                        for i, step in enumerate(recipe["steps"], 1):
                            st.write(f"{i}. {step}")
            else:
                st.warning("没有找到完全匹配的菜谱，试试调整食材或筛选条件")
        else:
            st.warning("请先选择或输入食材")

# 按口味找菜
elif page == "🌶️ 按口味找菜":
    st.markdown("### 🌶️ 选择你想要的口味")

    # 口味选项
    taste_options = ["酸甜", "麻辣", "清淡", "咸鲜", "微辣", "爽脆", "蒜香", "咖喱香"]
    selected_tastes = st.multiselect("选择口味偏好（可多选）", taste_options)

    # 额外筛选
    col1, col2, col3 = st.columns(3)
    with col1:
        filter_category = st.selectbox("筛选分类", ["不限", "家常菜", "川菜", "素菜", "海鲜", "凉菜", "汤类", "主食"])
    with col2:
        filter_difficulty = st.selectbox("筛选难度", ["不限", "简单", "中等", "较难"])
    with col3:
        filter_time = st.selectbox("筛选时间", ["不限", "15分钟以内", "30分钟以内", "1小时以内"])

    if st.button("🌶️ 查找推荐菜谱", type="primary"):
        if selected_tastes:
            results = []
            for recipe in recipes:
                if any(any(t in rt for t in selected_tastes) for rt in recipe["taste"]):
                    if filter_category != "不限" and recipe["category"] != filter_category:
                        continue
                    if filter_difficulty != "不限" and recipe["difficulty"] != filter_difficulty:
                        continue
                    results.append(recipe)

            if results:
                st.markdown(f"### 找到 {len(results)} 道匹配的菜谱")
                for recipe in results:
                    with st.expander(f"**{recipe['name']}** - {recipe['category']} | {recipe['difficulty']} | {recipe['time']}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("**食材**")
                            st.write(f"主料: {', '.join(recipe['main_ingredients'])}")
                            st.write(f"调料: {', '.join(recipe['seasonings'])}")
                        with col2:
                            st.markdown("**口味与标签**")
                            st.write(f"口味: {', '.join(recipe['taste'])}")
                            st.write(f"标签: {', '.join(recipe['tags'])}")

                        st.markdown("**做法步骤**")
                        for i, step in enumerate(recipe["steps"], 1):
                            st.write(f"{i}. {step}")
            else:
                st.warning("没有找到匹配的菜谱，试试调整筛选条件")
        else:
            st.warning("请先选择至少一种口味")

# 生成购物清单
elif page == "📝 生成购物清单":
    st.markdown("### 📝 选择你想做的菜，生成购物清单")

    # 选择菜谱
    recipe_names = [r["name"] for r in recipes]
    selected_recipes = st.multiselect("选择菜谱（可多选）", recipe_names, placeholder="点击选择...")

    # 输入已有食材
    st.markdown("### 🏠 你已经有的食材")
    owned_ingredients = st.text_input("输入你已有的食材（用逗号分隔）", placeholder="如：盐, 糖, 食用油, 鸡蛋")

    if st.button("📝 生成购物清单", type="primary"):
        if selected_recipes:
            # 获取选中的菜谱
            selected = [r for r in recipes if r["name"] in selected_recipes]

            # 解析已有食材
            owned = [x.strip() for x in owned_ingredients.split(",") if x.strip()] if owned_ingredients else []

            # 生成购物清单
            shopping_list = generate_shopping_list(selected, owned)

            if shopping_list:
                st.markdown("### 🛒 购物清单")

                # 按分类显示
                grouped = {}
                for ing, count in shopping_list.items():
                    cat = get_category(ing, categories)
                    if cat not in grouped:
                        grouped[cat] = []
                    grouped[cat].append((ing, count))

                for cat, items in grouped.items():
                    with st.expander(f"📦 {cat}（{len(items)}项）", expanded=True):
                        for ing, count in sorted(items):
                            suffix = f" ×{count}道菜" if count > 1 else ""
                            st.checkbox(f"{ing}{suffix}", key=f"shop_{ing}")

                st.markdown("---")
                st.info(f"共 **{len(shopping_list)}** 项需要购买")
            else:
                st.success("✅ 你已经拥有所有需要的食材！")

            # 显示选中菜谱的简要信息
            st.markdown("---")
            st.markdown("### 📋 选中的菜谱")
            for recipe in selected:
                st.write(f"• **{recipe['name']}** - {recipe['difficulty']} | {recipe['time']} | {', '.join(recipe['taste'])}")
        else:
            st.warning("请先选择至少一道菜谱")

# 菜谱大全
elif page == "📖 菜谱大全":
    st.markdown("### 📖 所有菜谱")

    # 筛选
    col1, col2, col3 = st.columns(3)
    with col1:
        filter_category = st.selectbox("筛选分类", ["全部"] + list(categories.keys()) + ["家常菜", "川菜", "素菜", "海鲜", "凉菜", "汤类", "主食"])
    with col2:
        filter_difficulty = st.selectbox("筛选难度", ["全部", "简单", "中等", "较难"])
    with col3:
        search_name = st.text_input("搜索菜名", placeholder="输入菜名...")

    # 过滤
    filtered = recipes
    if filter_category != "全部":
        filtered = [r for r in filtered if r["category"] == filter_category]
    if filter_difficulty != "全部":
        filtered = [r for r in filtered if r["difficulty"] == filter_difficulty]
    if search_name:
        filtered = [r for r in filtered if search_name in r["name"]]

    st.markdown(f"共找到 **{len(filtered)}** 道菜谱")

    for recipe in filtered:
        with st.expander(f"**{recipe['name']}** - {recipe['category']} | {recipe['difficulty']} | {recipe['time']}"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**食材**")
                st.write(f"主料: {', '.join(recipe['main_ingredients'])}")
                st.write(f"调料: {', '.join(recipe['seasonings'])}")
            with col2:
                st.markdown("**口味与标签**")
                st.write(f"口味: {', '.join(recipe['taste'])}")
                st.write(f"标签: {', '.join(recipe['tags'])}")

            st.markdown("**做法步骤**")
            for i, step in enumerate(recipe["steps"], 1):
                st.write(f"{i}. {step}")

# 页脚
st.markdown("---")
st.markdown(
    '<div style="text-align: center; color: #999; font-size: 0.8rem;">'
    '智能菜谱助手 v1.0 | 收录 20 道精选家常菜'
    '</div>',
    unsafe_allow_html=True
)

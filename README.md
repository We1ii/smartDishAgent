# 智能菜谱助手

一个智能菜谱助手，帮助你根据现有食材和口味偏好推荐菜谱，并生成购物清单。

## 功能特性

- 🥘 **食材推荐** - 根据你冰箱里的食材推荐能做的菜
- 🌶️ **口味筛选** - 按酸甜、麻辣、清淡等口味筛选
- 📝 **购物清单** - 自动计算缺少的食材并生成清单
- 👨‍🍳 **详细做法** - 提供完整的烹饪步骤
- 🤖 **AI 助手** - 大模型自然语言对话，流式逐字输出，历史会话持久化（刷新不丢）

## 运行方式

### 方式一：Web 网页应用（推荐）

#### 1. 安装依赖

```bash
pip install streamlit
```

#### 2. 启动应用

```bash
streamlit run app.py
```

#### 3. 打开浏览器

启动后会自动打开浏览器，访问 `http://localhost:8501`

### 方式二：命令行应用

```bash
python cli.py
```

### 方式三：AI 助手（Agent + 大模型）

通过 OpenAI 兼容接口接入大模型（默认小米 MiMo，也可换 DeepSeek / 通义 / Kimi 等），使用 Function Calling 让模型自主调用查菜谱、看做法、生成购物清单三个工具：

```bash
pip install -r requirements.txt

# 复制配置模板，然后在 .env 里填入真实 API Key（.env 已被 .gitignore 忽略，不会上传）
copy .env.example .env     # Windows
# cp .env.example .env     # Linux / macOS

streamlit run app.py
```

`.env` 文件内容：

```ini
LLM_API_KEY=你的APIKey
LLM_BASE_URL=https://api.xiaomimimo.com/v1   # 默认小米 MiMo，可换其他兼容接口
LLM_MODEL=mimo-v2.6-flash                    # 可换其他模型名
```

启动后在侧边栏选择「🤖 AI 助手」，即可自然语言对话，例如：

- 「我有鸡蛋和番茄，能做什么？」
- 「宫保鸡丁怎么做？」
- 「想做麻婆豆腐和番茄炒蛋，帮我列购物清单，我已经有盐和食用油」

#### Agent 架构

```
用户输入 -> LLM（决定调哪个工具）-> 工具执行（core.py 规则引擎 + SQLite 菜谱库）
        -> 结果回填 LLM -> 循环（最多 6 轮）-> 最终自然语言回答
```

| 文件 | 职责 |
|------|------|
| `core.py` | 数据加载与匹配逻辑（Web / Agent 共用），用量合并 |
| `recipe_store.py` | 菜谱存储层：SQLite 主库 + 种子 JSON 导入 + Pydantic 校验 |
| `agent.py` | LLM 客户端、工具定义、Function Calling 主循环（流式输出 + Pydantic 入参校验） |
| `llm_utils.py` | 调用基础设施：指数退避重试、错误分类、结构化日志（写 `logs/agent.log`） |
| `chat_store.py` | 会话持久化：SQLite 存对话历史（`data/chat.db`，刷新不丢） |
| `app.py` | Streamlit 界面，含「🤖 AI 助手」聊天页 |


## 使用示例

### 按食材找菜

1. 打开 Web 应用，选择「按食材找菜」
2. 选择你有的食材（如：鸡蛋、番茄）
3. 点击「查找推荐菜谱」
4. 查看推荐结果，点击展开查看详细做法

### 按口味找菜

1. 选择「按口味找菜」
2. 选择口味偏好（如：麻辣、酸甜）
3. 可选：筛选分类、难度、时间
4. 查看推荐结果

### 生成购物清单

1. 选择「生成购物清单」
2. 选择想做的菜（可多选）
3. 输入你已有的食材
4. 点击「生成购物清单」
5. 勾选需要购买的食材

## 菜谱数据库

**120 道菜谱**（原始 20 道 + 批量扩充 100 道），存储在 SQLite（`data/recipes.db`，自动生成），涵盖：

| 分类 | 数量 | 代表菜 |
|------|------|--------|
| 家常菜 | 37 | 番茄炒蛋、红烧肉、鱼香茄子、黄焖鸡、糖醋里脊 |
| 川菜 | 18 | 宫保鸡丁、水煮鱼、辣子鸡、毛血旺、酸菜鱼 |
| 素菜 | 17 | 地三鲜、香菇青菜、蚝油生菜、松仁玉米 |
| 汤类 | 14 | 玉米排骨汤、酸辣汤、银耳莲子汤、鲫鱼豆腐汤 |
| 主食 | 13 | 蛋炒饭、担担面、葱油拌面、猪肉白菜饺子 |
| 凉菜 | 11 | 凉拌黄瓜、口水鸡、夫妻肺片、皮蛋豆腐 |
| 海鲜 | 10 | 清蒸鲈鱼、油焖大虾、葱姜炒蛤蜊 |

新菜谱 schema 支持**食材用量**和**份量**，购物清单会自动合并同类用量（如 2 个番茄 + 1 个番茄 → 3 个番茄）。

## 项目结构

```
smartDishAgent/
├── app.py                          # Web 应用主文件
├── cli.py                          # 命令行版本
├── core.py                         # 公共业务逻辑（数据加载/匹配/用量合并）
├── recipe_store.py                 # 菜谱存储层（SQLite + 种子导入 + Pydantic 校验）
├── agent.py                        # AI Agent（LLM + Function Calling + 流式输出）
├── llm_utils.py                    # 重试退避 / 错误分类 / 结构化日志
├── chat_store.py                   # 对话历史持久化（SQLite）
├── scripts/
│   └── import_recipes.py           # 菜谱数据导入工具
├── data/
│   ├── seed/                       # 菜谱种子数据（入库）
│   │   ├── recipes_gen_1~4.json    # 批量扩充的 100 道
│   │   └── zz_categories_patch.json
│   └── recipes.db                  # 生成的主库（gitignore）
├── requirements.txt
├── .mimocode/skills/recipe-assistant/
│   └── recipes.json                # 原始 20 道种子
└── README.md
```

## 扩展菜谱

**方式一（推荐）：新建种子文件后导入**

在 `data/seed/` 下新建 JSON 文件（格式见下），然后：

```bash
python scripts/import_recipes.py                    # 导入全部种子（增量、幂等）
python scripts/import_recipes.py data/seed/xx.json  # 只导入指定文件
python scripts/import_recipes.py --rebuild          # 编辑旧种子后删库重建
python scripts/import_recipes.py --stats            # 查看库内统计
```

**方式二：直接编辑种子文件**（改完必须 `--rebuild` 才生效）

```json
{
  "recipes": [
    {
      "id": 201,
      "name": "新菜名",
      "category": "家常菜",
      "taste": ["咸鲜"],
      "difficulty": "简单",
      "time": "20分钟",
      "servings": 2,
      "main_ingredients": [
        {"name": "食材1", "amount": "200克"},
        {"name": "食材2", "amount": "1根"}
      ],
      "seasonings": [{"name": "盐", "amount": "适量"}],
      "steps": ["步骤1", "步骤2"],
      "tags": ["标签"]
    }
  ],
  "ingredient_categories": {"蔬菜": ["食材2"]}
}
```

校验规则：分类限 `家常菜/川菜/素菜/海鲜/凉菜/汤类/主食`，难度限 `简单/中等/较难`，必须有主料和步骤；新食材记得补进 `ingredient_categories`（否则购物清单归入"其他"）。食材写法兼容旧的纯字符串 `["番茄"]`。


## License

MIT

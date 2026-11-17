# 智能菜谱助手

一个智能菜谱助手，帮助你根据现有食材和口味偏好推荐菜谱，并生成购物清单。

## 功能特性

- 🥘 **食材推荐** - 根据你冰箱里的食材推荐能做的菜
- 🌶️ **口味筛选** - 按酸甜、麻辣、清淡等口味筛选
- 📝 **购物清单** - 自动计算缺少的食材并生成清单
- 👨‍🍳 **详细做法** - 提供完整的烹饪步骤

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
用户输入 -> LLM（决定调哪个工具）-> 工具执行（core.py 规则引擎 + recipes.json）
        -> 结果回填 LLM -> 循环（最多 6 轮）-> 最终自然语言回答
```

| 文件 | 职责 |
|------|------|
| `core.py` | 数据加载与匹配逻辑（Web / Agent 共用） |
| `agent.py` | LLM 客户端、工具定义、Function Calling 主循环 |
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

内置 20 道精选家常菜，涵盖：

| 分类 | 菜品 |
|------|------|
| 家常菜 | 番茄炒蛋、红烧肉、可乐鸡翅、糖醋排骨、酸辣土豆丝 |
| 川菜 | 宫保鸡丁、麻婆豆腐、鱼香肉丝、回锅肉、水煮肉片 |
| 素菜 | 蒜蓉西兰花、清炒时蔬、干煸豆角 |
| 海鲜 | 白灼虾 |
| 凉菜 | 凉拌黄瓜 |
| 汤类 | 紫菜蛋花汤、西红柿牛腩汤 |
| 主食 | 蛋炒饭、咖喱鸡肉饭 |

## 项目结构

```
smartDishAgent/
├── app.py                          # Web 应用主文件
├── cli.py                          # 命令行版本
├── core.py                         # 公共业务逻辑（数据加载/匹配/购物清单）
├── agent.py                        # AI Agent（LLM + Function Calling）
├── requirements.txt                # 依赖文件
├── .mimocode/
│   └── skills/
│       └── recipe-assistant/
│           ├── recipes.json        # 菜谱数据库
│           ├── SKILL.md            # MiMoCode 技能定义
│           └── shopping-list-generator.js
└── README.md
```

## 扩展菜谱

编辑 `.mimocode/skills/recipe-assistant/recipes.json` 添加新菜谱：

```json
{
  "id": 21,
  "name": "新菜名",
  "category": "分类",
  "taste": ["口味标签"],
  "difficulty": "简单|中等|较难",
  "time": "XX分钟",
  "main_ingredients": ["食材1", "食材2"],
  "seasonings": ["调料1", "调料2"],
  "steps": ["步骤1", "步骤2"],
  "tags": ["标签1", "标签2"]
}
```

## License

MIT

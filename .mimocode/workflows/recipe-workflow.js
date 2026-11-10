/**
 * 菜谱助手工作流
 * 处理复杂的菜谱推荐和购物清单生成场景
 */

export const meta = {
  name: "recipe-assistant",
  description: "智能菜谱助手工作流 - 根据食材和口味推荐菜谱，生成购物清单"
};

// 加载菜谱数据
async function loadRecipeData() {
  const dataPath = "skills/recipe-assistant/recipes.json";
  const content = await readFile(dataPath);
  return JSON.parse(content);
}

// 智能推荐菜谱
async function recommendRecipes(ingredients, tastePreference, difficulty) {
  const data = await loadRecipeData();
  let recipes = data.recipes;

  // 按食材筛选
  if (ingredients && ingredients.length > 0) {
    recipes = recipes.filter(recipe => {
      const matchCount = recipe.main_ingredients.filter(ing =>
        ingredients.some(userIng => ing.includes(userIng) || userIng.includes(ing))
      ).length;
      return matchCount > 0;
    });

    // 计算匹配度并排序
    recipes = recipes.map(recipe => {
      const matchCount = recipe.main_ingredients.filter(ing =>
        ingredients.some(userIng => ing.includes(userIng) || userIng.includes(ing))
      ).length;
      const totalIngredients = recipe.main_ingredients.length;
      return { ...recipe, matchRate: matchCount / totalIngredients };
    }).sort((a, b) => b.matchRate - a.matchRate);
  }

  // 按口味筛选
  if (tastePreference) {
    recipes = recipes.filter(recipe =>
      recipe.taste.some(t => t.includes(tastePreference))
    );
  }

  // 按难度筛选
  if (difficulty) {
    recipes = recipes.filter(recipe => recipe.difficulty === difficulty);
  }

  return recipes;
}

// 生成购物清单
async function createShoppingList(recipeNames, ownedIngredients) {
  const data = await loadRecipeData();
  const shoppingList = new Map();

  recipeNames.forEach(name => {
    const recipe = data.recipes.find(r => r.name === name);
    if (recipe) {
      [...recipe.main_ingredients, ...recipe.seasonings].forEach(ing => {
        if (!ownedIngredients.includes(ing)) {
          shoppingList.set(ing, (shoppingList.get(ing) || 0) + 1);
        }
      });
    }
  });

  return Array.from(shoppingList.entries()).map(([name, count]) => ({
    name,
    count,
    category: getCategory(name, data.ingredient_categories)
  }));
}

function getCategory(ingredient, categories) {
  for (const [cat, items] of Object.entries(categories)) {
    if (items.includes(ingredient)) return cat;
  }
  return "其他";
}

// 格式化输出
function formatRecipeList(recipes) {
  if (recipes.length === 0) {
    return "抱歉，没有找到匹配的菜谱。请尝试提供更多信息。";
  }

  let output = "## 推荐菜谱\n\n";
  recipes.slice(0, 5).forEach((recipe, index) => {
    output += `### ${index + 1}. ${recipe.name}\n`;
    output += `- **分类**: ${recipe.category}\n`;
    output += `- **难度**: ${recipe.difficulty} | **时间**: ${recipe.time}\n`;
    output += `- **口味**: ${recipe.taste.join('、')}\n`;
    output += `- **主料**: ${recipe.main_ingredients.join('、')}\n`;
    if (recipe.matchRate !== undefined) {
      output += `- **匹配度**: ${Math.round(recipe.matchRate * 100)}%\n`;
    }
    output += `- **标签**: ${recipe.tags.join('、')}\n\n`;
  });

  return output;
}

function formatShoppingList(items) {
  if (items.length === 0) {
    return "你已经拥有所有需要的食材！";
  }

  let output = "## 购物清单\n\n";
  const grouped = {};
  items.forEach(item => {
    if (!grouped[item.category]) grouped[item.category] = [];
    grouped[item.category].push(item);
  });

  Object.entries(grouped).forEach(([category, categoryItems]) => {
    output += `### ${category}\n`;
    categoryItems.forEach(item => {
      const suffix = item.count > 1 ? ` (×${item.count}道菜)` : "";
      output += `- [ ] ${item.name}${suffix}\n`;
    });
    output += "\n";
  });

  output += `*共 ${items.length} 项*\n`;
  return output;
}

export default async function(args) {
  log("🍳 智能菜谱助手启动");

  const { action, ingredients, taste, difficulty, recipes: recipeNames, owned } = args;

  switch (action) {
    case "recommend": {
      log(`正在根据食材 [${ingredients}] 和口味 [${taste}] 推荐菜谱...`);
      const results = await recommendRecipes(ingredients, taste, difficulty);
      return formatRecipeList(results);
    }

    case "shopping-list": {
      log(`正在为 ${recipeNames.length} 道菜生成购物清单...`);
      const list = await createShoppingList(recipeNames, owned || []);
      return formatShoppingList(list);
    }

    case "detail": {
      const data = await loadRecipeData();
      const recipe = data.recipes.find(r => r.name === recipeNames[0]);
      if (!recipe) return "未找到该菜谱";

      let output = `## ${recipe.name}\n\n`;
      output += `**分类**: ${recipe.category}\n`;
      output += `**难度**: ${recipe.difficulty} | **时间**: ${recipe.time}\n`;
      output += `**口味**: ${recipe.taste.join('、')}\n\n`;
      output += `### 食材\n`;
      output += `- 主料: ${recipe.main_ingredients.join('、')}\n`;
      output += `- 调料: ${recipe.seasonings.join('、')}\n\n`;
      output += `### 做法步骤\n`;
      recipe.steps.forEach((step, i) => {
        output += `${i + 1}. ${step}\n`;
      });
      output += `\n### 标签\n${recipe.tags.join('、')}\n`;
      return output;
    }

    default:
      return "请指定操作：recommend（推荐菜谱）或 shopping-list（购物清单）或 detail（菜品详情）";
  }
}

/**
 * 购物清单生成器
 * 根据用户已有食材和目标菜谱，生成需要购买的食材清单
 */

const fs = require('fs');
const path = require('path');

// 加载菜谱数据
function loadRecipes() {
  const dataPath = path.join(__dirname, 'recipes.json');
  const data = JSON.parse(fs.readFileSync(dataPath, 'utf-8'));
  return data;
}

// 生成购物清单
function generateShoppingList(targetRecipes, ownedIngredients) {
  const data = loadRecipes();
  const allIngredients = new Set();
  const neededIngredients = new Map();

  // 收集目标菜谱所需的所有食材
  targetRecipes.forEach(recipeName => {
    const recipe = data.recipes.find(r => r.name === recipeName);
    if (recipe) {
      recipe.main_ingredients.forEach(ing => {
        allIngredients.add(ing);
        neededIngredients.set(ing, (neededIngredients.get(ing) || 0) + 1);
      });
      recipe.seasonings.forEach(ing => {
        allIngredients.add(ing);
        neededIngredients.set(ing, (neededIngredients.get(ing) || 0) + 1);
      });
    }
  });

  // 过滤掉已有的食材
  const shoppingList = [];
  allIngredients.forEach(ingredient => {
    if (!ownedIngredients.includes(ingredient)) {
      // 查找分类
      let category = '其他';
      for (const [cat, items] of Object.entries(data.ingredient_categories)) {
        if (items.includes(ingredient)) {
          category = cat;
          break;
        }
      }
      shoppingList.push({
        name: ingredient,
        category: category,
        recipeCount: neededIngredients.get(ingredient)
      });
    }
  });

  // 按分类排序
  const categoryOrder = ['蔬菜', '肉类', '海鲜', '蛋奶豆', '主食', '调味料', '其他'];
  shoppingList.sort((a, b) => {
    return categoryOrder.indexOf(a.category) - categoryOrder.indexOf(b.category);
  });

  return shoppingList;
}

// 格式化购物清单为 Markdown
function formatShoppingListMarkdown(shoppingList, recipeNames) {
  let md = `## 购物清单\n\n`;
  md += `**目标菜谱**: ${recipeNames.join('、')}\n\n`;

  let currentCategory = '';
  shoppingList.forEach(item => {
    if (item.category !== currentCategory) {
      currentCategory = item.category;
      md += `\n### ${currentCategory}\n`;
    }
    const suffix = item.recipeCount > 1 ? ` (×${item.recipeCount}道菜)` : '';
    md += `- [ ] ${item.name}${suffix}\n`;
  });

  md += `\n---\n`;
  md += `*共 ${shoppingList.length} 项*\n`;

  return md;
}

// 导出
module.exports = {
  loadRecipes,
  generateShoppingList,
  formatShoppingListMarkdown
};

// 命令行使用
if (require.main === module) {
  const args = process.argv.slice(2);
  if (args.length < 1) {
    console.log('用法: node shopping-list-generator.js <菜谱名称1,菜谱名称2,...> [已有食材1,已有食材2,...]');
    process.exit(1);
  }

  const recipeNames = args[0].split(',');
  const ownedIngredients = args.length > 1 ? args[1].split(',') : [];

  const list = generateShoppingList(recipeNames, ownedIngredients);
  const md = formatShoppingListMarkdown(list, recipeNames);
  console.log(md);
}

import asyncio
import os
from typing import List, Dict, Any
import concurrent.futures
from threading import Lock
import json
import time
import statistics

import asyncpg
from mcp.server.fastmcp import FastMCP

# 模型对战相关导入
try:
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from model_battle import ModelBattle, ModelType, BattleResult
    MODEL_BATTLE_AVAILABLE = True
    
    # 创建全局实例
    _battle_instance = ModelBattle()
    
    # 创建线程池用于执行异步任务
    _executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    
except ImportError as e:
    print(f"警告: 无法导入模型对战功能: {e}")
    MODEL_BATTLE_AVAILABLE = False

mcp = FastMCP(
    "shiji_app_server",
    dependencies=["asyncpg"],
)

# 数据库连接配置
DB_DSN = f"postgresql://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', 'kangkang123')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', 5432)}/shiji_app"

# 线程池锁
_pool_lock = Lock()

async def execute_query_async(query: str, params: tuple = (), limit: int = 100) -> str:
    """异步执行数据库查询"""
    try:
        # 安全检查：只允许SELECT查询
        sql_lower = query.strip().lower()
        if not sql_lower.startswith('select'):
            return "错误：只允许执行SELECT查询语句"
        
        # 添加LIMIT限制（如果查询中没有LIMIT）
        if 'limit' not in sql_lower:
            query_limited = f"{query.rstrip(';')} LIMIT {limit}"
        else:
            query_limited = query
        
        # 建立连接并执行查询
        conn = await asyncpg.connect(DB_DSN)
        try:
            # 执行查询
            if params:
                rows = await conn.fetch(query_limited, *params)
            else:
                rows = await conn.fetch(query_limited)
            
            # 转换结果为字典列表
            result = []
            for row in rows:
                result.append(dict(row))
            
            if not result:
                return "查询成功，但没有找到匹配的数据。"
            
            return f"查询成功，返回 {len(result)} 条记录：\n{str(result)}"
            
        finally:
            await conn.close()
            
    except Exception as e:
        return f"查询执行失败：{e}"

def execute_query_sync(query: str, params: tuple = (), limit: int = 100) -> str:
    """同步执行数据库查询的包装器"""
    try:
        # 在独立线程中运行异步查询
        future = _executor.submit(asyncio.run, execute_query_async(query, params, limit))
        return future.result(timeout=30)  # 30秒超时
    except concurrent.futures.TimeoutError:
        return "查询超时，请检查查询条件"
    except Exception as e:
        return f"查询执行失败：{e}"

def execute_battle_sync(question: str, models: List[str]) -> str:
    """同步执行模型对战的包装器"""
    if not MODEL_BATTLE_AVAILABLE:
        return "模型对战功能不可用：请安装相关依赖"
    
    try:
        # 将模型名称转换为ModelType枚举
        model_types = []
        for model_name in models:
            if model_name == "qwen-turbo":
                model_types.append(ModelType.DASHSCOPE_QWEN)
            elif model_name == "qwen-max":
                model_types.append(ModelType.DASHSCOPE_QWEN_MAX)
            elif model_name == "qwen-vl-max":
                model_types.append(ModelType.DASHSCOPE_QWEN_VL_MAX)
            elif model_name == "qwen-audio-turbo-latest":
                model_types.append(ModelType.DASHSCOPE_QWEN_AUDIO_TURBO_LATEST)
            else:
                continue  # 跳过不支持的模型
        
        if not model_types:
            return "错误：没有找到支持的模型"
        
        # 异步执行对战
        async def run_battle():
            result = await _battle_instance.battle(question, model_types)
            return {
                "question": result.question,
                "final_winner": result.final_winner,
                "final_scores": result.final_scores,
                "final_answer": result.final_answer,
                "timestamp": result.timestamp,
                "rounds_count": len(result.rounds)
            }
        
        future = _executor.submit(asyncio.run, run_battle())
        result = future.result(timeout=120)  # 2分钟超时
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except concurrent.futures.TimeoutError:
        return "模型对战超时"
    except Exception as e:
        return f"模型对战失败：{e}"

@mcp.tool()
def write_to_txt(filename: str, content: str) -> str:
    """
    将指定内容写入文本文件并且保存到本地。
    参数:
      filename: 文件名（例如 "output.txt"）
      content: 要写入的文本内容
    返回:
      写入成功或失败的提示信息
    """
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        return f"成功写入文件 {filename}。"
    except Exception as e:
        return f"写入文件失败：{e}"

@mcp.tool()
def query_database(sql_query: str, limit: int = 100) -> str:
    """
    执行SQL查询并返回结果。
    参数:
      sql_query: 要执行的SQL查询语句
      limit: 返回结果的最大行数，默认100行
    返回:
      查询结果的JSON格式字符串或错误信息
    """
    return execute_query_sync(sql_query, (), limit)

@mcp.tool()
def get_tables_info() -> str:
    """
    获取数据库中所有表的信息。
    返回:
      数据库表列表和基本信息
    """
    query = """
    SELECT 
        table_name,
        table_type,
        table_schema
    FROM information_schema.tables 
    WHERE table_schema = 'public'
    ORDER BY table_name;
    """
    return execute_query_sync(query)

@mcp.tool()
def get_table_structure(table_name: str) -> str:
    """
    获取指定表的结构信息。
    参数:
      table_name: 表名
    返回:
      表结构信息，包括列名、数据类型等
    """
    query = """
    SELECT 
        column_name,
        data_type,
        is_nullable,
        column_default,
        character_maximum_length
    FROM information_schema.columns 
    WHERE table_schema = 'public' AND table_name = $1
    ORDER BY ordinal_position;
    """
    return execute_query_sync(query, (table_name,))

@mcp.tool()
def query_user_info(user_id: int, limit: int = 10) -> str:
    """
    查询用户表数据。
    参数:
      limit: 返回结果的最大行数，默认10行
    返回:
      用户数据
    """
    query = "SELECT * FROM users where id = $1"
    result =  execute_query_sync(query, (user_id,), limit)
    user_info = {
        "用户ID": result["id"],
        "用户名": result["name"],
        "年龄": result["age"],
        "性别": result["gender"],
        "身高": result["height"],
        "体重": result["weight"],
        "BMI": round(result["weight"] / ((result["height"]/100) ** 2), 1) if result["weight"] and result["height"] else '未计算',
        "健康目标": result["health_goal"],
        "饮食偏好": result["diet_preference"],
        "活动水平": result["activity_level"],
        "过敏信息": result["allergies"],
        "健康状况": result["health_conditions"]
    }
    return user_info

@mcp.tool()
def query_foods(search_term: str = "", limit: int = 20) -> str:
    """
    查询食物表数据。
    参数:
      search_term: 搜索关键词（可选），用于搜索食物名称
      limit: 返回结果的最大行数，默认20行
    返回:
      食物数据
    """
    if search_term:
        query = "SELECT id, food_name, calories, protein, fat, carbs FROM foods WHERE food_name ILIKE $1"
        return execute_query_sync(query, (f'%{search_term}%',), limit)
    else:
        query = "SELECT id, food_name, calories, protein, fat, carbs FROM foods"
        return execute_query_sync(query, (), limit)

@mcp.tool()
def query_recipes(search_term: str = "", limit: int = 10) -> str:
    """
    查询食谱表数据。
    参数:
      search_term: 搜索关键词（可选），用于搜索食谱标题
      limit: 返回结果的最大行数，默认10行
    返回:
      食谱数据
    """
    if search_term:
        query = "SELECT id, title, description, preparation_time, cooking_time, calories FROM recipes WHERE title ILIKE $1"
        return execute_query_sync(query, (f'%{search_term}%',), limit)
    else:
        query = "SELECT id, title, description, preparation_time, cooking_time, calories FROM recipes"
        return execute_query_sync(query, (), limit)

@mcp.tool()
def search_foods_advanced(search_term: str = "", search_field: str = "food_name", limit: int = 20) -> str:
    """
    高级食物搜索功能。
    参数:
      search_term: 搜索关键词
      search_field: 搜索字段 (food_name, category, 或 all 表示在多个字段中搜索)
      limit: 返回结果的最大行数，默认20行
    返回:
      食物数据
    """
    if not search_term:
        return query_foods("", limit)
    
    if search_field == "all":
        query = """
        SELECT id, food_name, calories, protein, fat, carbs, category 
        FROM foods 
        WHERE food_name ILIKE $1 OR category ILIKE $1
        """
        return execute_query_sync(query, (f'%{search_term}%',), limit)
    elif search_field == "food_name":
        query = "SELECT id, food_name, calories, protein, fat, carbs FROM foods WHERE food_name ILIKE $1"
        return execute_query_sync(query, (f'%{search_term}%',), limit)
    elif search_field == "category":
        query = "SELECT id, food_name, calories, protein, fat, carbs, category FROM foods WHERE category ILIKE $1"
        return execute_query_sync(query, (f'%{search_term}%',), limit)
    else:
        return f"错误：不支持的搜索字段 '{search_field}'。支持的字段：food_name, category, all"

@mcp.tool()
def search_recipes_advanced(search_term: str = "", search_field: str = "title", limit: int = 10) -> str:
    """
    高级食谱搜索功能。
    参数:
      search_term: 搜索关键词
      search_field: 搜索字段 (title, description, 或 all 表示在多个字段中搜索)
      limit: 返回结果的最大行数，默认10行
    返回:
      食谱数据
    """
    if not search_term:
        return query_recipes("", limit)
    
    if search_field == "all":
        query = """
        SELECT id, title, description, preparation_time, cooking_time, calories, protein, fat, carbs
        FROM recipes 
        WHERE title ILIKE $1 OR description ILIKE $1
        """
        return execute_query_sync(query, (f'%{search_term}%',), limit)
    elif search_field == "title":
        query = "SELECT id, title, description, preparation_time, cooking_time, calories FROM recipes WHERE title ILIKE $1"
        return execute_query_sync(query, (f'%{search_term}%',), limit)
    elif search_field == "description":
        query = "SELECT id, title, description, preparation_time, cooking_time, calories FROM recipes WHERE description ILIKE $1"
        return execute_query_sync(query, (f'%{search_term}%',), limit)
    else:
        return f"错误：不支持的搜索字段 '{search_field}'。支持的字段：title, description, all"

@mcp.tool()
def get_recipe_details(recipe_id: int) -> str:
    """
    获取食谱详细信息。
    参数:
      recipe_id: 食谱ID
    返回:
      食谱详细信息
    """
    query = "SELECT * FROM recipes WHERE id = $1"
    return execute_query_sync(query, (recipe_id,), 1)
@mcp.tool()
def get_diet_records(user_id: int) -> str:
    """
    获取用户饮食历史。
    参数:
      user_id: 用户ID
    返回:
      用户饮食历史
    """
    query = "SELECT * FROM diet_records WHERE user_id = $1"
    result = execute_query_sync(query, (user_id,), 10)
    diet_records = []
    for record in result:
        diet_record= {
            "食物": record["diet_name"],
            "数量": record["quantity"],
            "类型": "早餐" if record["meal_type"] == "breakfast" else "午餐" if record["meal_type"] == "lunch" else "晚餐" if record["meal_type"] == "dinner" else "加餐" if record["meal_type"] == "snack" else "其他",
            "单位": record["unit"],
            "卡路里": record["calories"],
            "蛋白质": record["protein"],
            "脂肪": record["fat"],
            "碳水化合物": record["carbs"],
            "时间": record["created_at"]
        }
        diet_records.append(diet_record)
    return diet_records

@mcp.tool()
def search_recipes_by_ingredient(ingredient: str, limit: int = 10) -> str:
    """
    根据配料搜索食谱。
    参数:
      ingredient: 配料名称
      limit: 返回结果的最大行数，默认10行
    返回:
      包含指定配料的食谱
    """
    query = """
    SELECT id, title, description, ingredients 
    FROM recipes 
    WHERE ingredients::text ILIKE $1 OR ingredient_name_texts::text ILIKE $1
    """
    return execute_query_sync(query, (f'%{ingredient}%',), limit)

@mcp.tool()
def get_nutrition_info(food_name: str) -> str:
    """
    获取食物营养信息。
    参数:
      food_name: 食物名称
    返回:
      详细营养信息
    """
    query = """
    SELECT food_name, calories, protein, fat, carbs, other_nutrition 
    FROM foods 
    WHERE food_name ILIKE $1
    """
    return execute_query_sync(query, (f'%{food_name}%',), 5)

@mcp.tool()
def get_recipe_by_cook_time(max_time: int, limit: int = 10) -> str:
    """
    根据烹饪时间搜索食谱。
    参数:
      max_time: 最大烹饪时间（分钟）
      limit: 返回结果的最大行数，默认10行
    返回:
      符合时间要求的食谱
    """
    query = """
    SELECT id, title, preparation_time, cooking_time, 
           (preparation_time + cooking_time) as total_time
    FROM recipes 
    WHERE (preparation_time + cooking_time) <= $1
    ORDER BY total_time ASC
    """
    return execute_query_sync(query, (max_time,), limit)

# ============ 模型对战工具 ============

@mcp.tool()
def ai_model_battle(question: str, models: str = "qwen-turbo,qwen-max") -> str:
    """
    让多个AI模型对战回答同一个问题并比较结果。
    参数:
      question: 要让模型回答的问题
      models: 参战模型列表，用逗号分隔 (支持: qwen-turbo, qwen-max, qwen-vl-max, qwen-audio-turbo-latest)
    返回:
      包含各模型回答、评分和获胜者的详细对战结果
    """
    model_list = [model.strip() for model in models.split(",")]
    return execute_battle_sync(question, model_list)

@mcp.tool()
def cooking_recipe_battle(ingredient: str) -> str:
    """
    让多个AI模型对战提供关于特定食材的烹饪建议。
    参数:
      ingredient: 食材名称（如：鸡蛋、土豆、番茄等）
    返回:
      各模型提供的烹饪建议对战结果
    """
    question = f"请为{ingredient}提供3种不同的烹饪方法，包括具体步骤和营养价值分析。"
    models = ["qwen-turbo", "qwen-max"]
    return execute_battle_sync(question, models)

@mcp.tool()
def health_advice_battle(health_goal: str) -> str:
    """
    让多个AI模型对战提供健康建议。
    参数:
      health_goal: 健康目标（如：减肥、增肌、提高免疫力等）
    返回:
      各模型提供的健康建议对战结果
    """
    question = f"针对{health_goal}这个健康目标，请提供详细的饮食建议和生活方式建议。"
    models = ["qwen-turbo", "qwen-max"]
    return execute_battle_sync(question, models)

@mcp.tool()
def nutrition_analysis_battle(food_list: str) -> str:
    """
    让多个AI模型对战分析食物营养价值。
    参数:
      food_list: 食物列表，用逗号分隔
    返回:
      各模型提供的营养分析对战结果
    """
    question = f"请分析以下食物的营养价值和健康益处：{food_list}。包括热量、主要营养成分和适合的人群。"
    models = ["qwen-turbo", "qwen-max"]
    return execute_battle_sync(question, models)

@mcp.tool()
def query_user_by_phone(phone: str) -> str:
    """
    通过手机号查询用户信息。
    参数:
      phone: 手机号码
    返回:
      用户数据
    """
    query = "SELECT * FROM users WHERE phone = $1 OR name = $1"
    result = execute_query_sync(query, (phone,), 1)
    
    # 如果结果是字符串（表示错误或无结果），直接返回
    if isinstance(result, str):
        return result
    
    # 如果结果是列表且有数据
    if isinstance(result, list) and len(result) > 0:
        user = result[0]
        user_info = {
            "用户ID": user.get("id"),
            "用户名": user.get("name"),
            "手机号": user.get("phone"),
            "年龄": user.get("age"),
            "性别": user.get("gender"),
            "身高": user.get("height"),
            "体重": user.get("weight"),
            "BMI": round(user["weight"] / ((user["height"]/100) ** 2), 1) if user.get("weight") and user.get("height") else '未计算',
            "健康目标": user.get("health_goal"),
            "饮食偏好": user.get("diet_preference"),
            "活动水平": user.get("activity_level"),
            "过敏信息": user.get("allergies"),
            "健康状况": user.get("health_conditions")
        }
        return user_info
    else:
        return f"未找到手机号为 {phone} 的用户"

@mcp.tool()
def generate_weekly_diet_plan(user_info: str, user_id: int = None) -> str:
    """
    生成个性化的一周饮食计划。
    参数:
      user_info: 用户信息（JSON字符串或描述）
      user_id: 用户ID（可选，用于获取饮食历史）
    返回:
      个性化的一周饮食推荐计划
    """
    try:
        # 获取用户饮食历史（如果提供了用户ID）
        diet_history = ""
        if user_id:
            try:
                history_result = get_diet_records(user_id)
                if isinstance(history_result, list) and len(history_result) > 0:
                    diet_history = f"\n用户最近的饮食记录：{str(history_result[:5])}"  # 只取最近5条
            except:
                diet_history = ""
        
        # 获取一些推荐的健康食物
        healthy_foods = query_foods("", 15)  # 获取15种食物作为参考
        
        # 获取一些健康食谱
        healthy_recipes = query_recipes("", 10)  # 获取10个食谱作为参考
        
        # 构建详细的提示
        prompt = f"""请根据以下用户信息，制定一个详细的一周饮食计划：

用户信息：
{user_info}

{diet_history}

可参考的健康食物：
{healthy_foods}

可参考的健康食谱：
{healthy_recipes}

请制定一个详细的一周饮食计划，包括：
1. 每天的三餐安排（早餐、午餐、晚餐）
2. 根据用户的健康目标、饮食偏好、过敏信息等个性化定制
3. 营养搭配均衡，包含蛋白质、碳水化合物、脂肪、维生素等
4. 考虑用户的活动水平调整热量摄入
5. 如果有健康状况，请给出相应的饮食建议
6. 每餐的大概热量和主要营养成分
7. 简单的制作建议或食谱推荐

格式要求：
- 按天组织（周一到周日）
- 每天包含早餐、午餐、晚餐
- 每餐包含具体食物、分量、营养价值
- 总结每日营养摄入和健康要点

请确保推荐科学合理，符合营养学原理。"""

        # 使用AI模型生成饮食计划
        return execute_battle_sync(prompt, ["qwen-max"])
        
    except Exception as e:
        return f"生成饮食计划失败：{str(e)}"

if __name__ == "__main__":
    mcp.run(transport='stdio')
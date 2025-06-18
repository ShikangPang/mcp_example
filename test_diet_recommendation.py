#!/usr/bin/env python3
"""
测试脚本：为用户13683931181生成下周饮食推荐
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from cli.client import MCPClient

async def test_diet_recommendation():
    """测试饮食推荐功能"""
    client = MCPClient()
    
    try:
        # 连接到服务器
        server_path = os.path.join(os.path.dirname(__file__), "server", "server.py")
        await client.connect_to_server(server_path)
        
        print("🔍 正在查找用户信息...")
        
        # 查询用户信息
        query = "帮用户13683931181推荐下周的饮食计划，请先查询用户信息，然后生成个性化的饮食推荐"
        
        print(f"📝 查询: {query}")
        print("-" * 60)
        
        # 处理查询
        response = await client.process_query(query)
        
        print("\n🍽️ 饮食推荐结果:")
        print("=" * 80)
        print(response)
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        print(traceback.format_exc())
    
    finally:
        await client.cleanup()

if __name__ == "__main__":
    print("🚀 开始为用户13683931181生成饮食推荐...")
    asyncio.run(test_diet_recommendation()) 
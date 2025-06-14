import os
import asyncio
from typing import Optional
from contextlib import AsyncExitStack
import json
import traceback
 
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
 
from dashscope import Generation
from dotenv import load_dotenv
 
load_dotenv()  # 加载环境变量从 .env
 
class MCPClient:
    def __init__(self):
        # 初始化会话和客户端对象
        self.session: Optional[ClientSession] = None # 会话对象
        self.exit_stack = AsyncExitStack() # 退出堆栈
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        self.model = "qwen-max"  # 使用支持工具调用的模型

    def get_response(self, messages: list, tools: list):
        """调用 Dashscope Generation API"""
        try:
            response = Generation.call(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                api_key=self.api_key
            )
            return response
        except Exception as e:
            print(f"API调用错误: {e}")
            raise
    
    async def get_tools(self):
        # 列出可用工具
        response = await self.session.list_tools()
        available_tools = [{ 
            "type":"function",
            "function":{
                "name": tool.name,
                "description": tool.description, # 工具描述
                "parameters": tool.inputSchema  # 工具输入模式
            }
        } for tool in response.tools]
        
        return available_tools
        
    
    async def connect_to_server(self, server_script_path: str):
        """连接到 MCP 服务器
    
        参数:
            server_script_path: 服务器脚本路径 (.py 或 .js)
        """
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("服务器脚本必须是 .py 或 .js 文件")
            
        command = "python" if is_python else "node"
        # 创建 StdioServerParameters 对象
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )
        
        # 使用 stdio_client 创建与服务器的 stdio 传输
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        
        # 解包 stdio_transport，获取读取和写入句柄
        self.stdio, self.write = stdio_transport
        
        # 创建 ClientSession 对象，用于与服务器通信
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        
        # 初始化会话
        await self.session.initialize()
        # 列出可用工具
        response = await self.session.list_tools()
        tools = response.tools
        print("\n连接到服务器，工具列表:", [tool.name for tool in tools])

    async def process_query(self, query: str) -> str:
        """使用 Dashscope 和可用工具处理查询"""
        
        # 创建消息列表
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]
        
        # 列出可用工具
        available_tools = await self.get_tools()
        print(f"\n可用工具: {json.dumps([t['function']['name'] for t in available_tools], ensure_ascii=False)}")
        
        # 处理消息
        response = self.get_response(messages, available_tools)

        # 检查响应状态
        if response.status_code != 200:
            return f"API调用失败: {response.message}"

        # 处理LLM响应和工具调用
        tool_results = []
        final_text = []
        
        choice = response.output.choices[0]
        message = choice.message
        
        # 检查是否有工具调用
        tool_calls = None
        if hasattr(message, 'tool_calls'):
            tool_calls = message.tool_calls
        elif isinstance(message, dict) and 'tool_calls' in message:
            tool_calls = message['tool_calls']
        
        if tool_calls:
            print(f"发现工具调用: {len(tool_calls)} 个")
            
            for tool_call in tool_calls:
                # 处理不同的工具调用格式
                if hasattr(tool_call, 'function'):
                    tool_name = tool_call.function.name
                    tool_args_str = tool_call.function.arguments
                    tool_id = getattr(tool_call, 'id', 'unknown_id')
                elif isinstance(tool_call, dict):
                    tool_name = tool_call.get('function', {}).get('name')
                    tool_args_str = tool_call.get('function', {}).get('arguments')
                    tool_id = tool_call.get('id', 'unknown_id')
                else:
                    print(f"未知的工具调用格式: {tool_call}")
                    continue
                
                print(f"准备调用工具: {tool_name}")
                print(f"参数字符串: {tool_args_str}")
                
                try:
                    # 解析工具参数
                    tool_args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
                    print(f"解析后参数: {json.dumps(tool_args, ensure_ascii=False, indent=2)}")
                    
                    # 执行工具调用，获取结果
                    result = await self.session.call_tool(tool_name, tool_args)
                    print(f"\n工具调用返回结果类型: {type(result)}")
                    
                    # 安全处理content
                    content = None
                    if hasattr(result, 'content'):
                        if isinstance(result.content, list):
                            content = "\n".join(str(item.text) if hasattr(item, 'text') else str(item) for item in result.content)
                        else:
                            content = str(result.content)
                    else:
                        content = str(result)
                    
                    print(f"工具执行结果: {content}")
                    tool_results.append({"call": tool_name, "result": content})
                    
                    # 构建工具调用的消息
                    messages.append({
                        "role": "assistant", 
                        "content": "",
                        "tool_calls": [tool_call] if hasattr(tool_call, 'function') else [{"function": {"name": tool_name, "arguments": tool_args_str}, "id": tool_id}]
                    })
                    
                    # 添加工具结果消息
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": content
                    })
                    
                except Exception as e:
                    print(f"\n工具调用异常: {str(e)}")
                    print(f"异常详情: {traceback.format_exc()}")
                    final_text.append(f"工具调用失败: {str(e)}")
                    continue

            # 如果有工具调用，获取最终响应
            if tool_results:
                try:
                    print("获取包含工具结果的最终响应...")
                    final_response = self.get_response(messages, available_tools)
                    
                    if final_response.status_code == 200:
                        final_choice = final_response.output.choices[0]
                        final_content = final_choice.message.content
                        
                        if isinstance(final_content, list):
                            final_text.append("\n".join(item.get('text', str(item)) for item in final_content))
                        else:
                            final_text.append(str(final_content))
                    else:
                        final_text.append("获取最终响应失败")
                except Exception as e:
                    print(f"获取最终响应异常: {e}")
                    # 如果无法获取最终响应，返回工具调用结果
                    final_text.append(f"工具调用完成: {json.dumps(tool_results, ensure_ascii=False, indent=2)}")
        
        else:
            # 没有工具调用，直接返回文本内容
            content = message.content
            if isinstance(content, list):
                final_text.append("\n".join(item.get('text', str(item)) for item in content))
            else:
                final_text.append(str(content))

        return "\n".join(final_text) if final_text else "没有收到有效响应"

    async def chat_loop(self):
        """运行交互式聊天循环（没有记忆）"""
        print("\nMCP Client 启动!")
        print("输入您的查询或 'quit' 退出.")
        
        while True:
            try:
                query = input("\nQuery: ").strip()
                
                if query.lower() == 'quit':
                    break
                    
                print("\n处理查询中...")
                response = await self.process_query(query)
                print("\n" + response)
                    
            except Exception as e:
                print(f"\n错误: {str(e)}")
                print(f"错误详情: {traceback.format_exc()}")
    
    async def cleanup(self):
        """清理资源"""
        await self.exit_stack.aclose() 

async def main():
    """
    主函数：初始化并运行 MCP 客户端
    此函数执行以下步骤：
    1. 检查命令行参数是否包含服务器脚本路径
    2. 创建 MCPClient 实例
    3. 连接到指定的服务器
    4. 运行交互式聊天循环
    5. 在结束时清理资源
    用法：
    python client.py <path_to_server_script>
    """
    # 检查命令行参数
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)
    
    # 创建 MCPClient 实例
    client = MCPClient()
    try:
        # 连接到服务器
        await client.connect_to_server(sys.argv[1])
        # 运行聊天循环
        await client.chat_loop()
    finally:
        # 确保在任何情况下都清理资源
        await client.cleanup()

if __name__ == "__main__":
    import sys
    asyncio.run(main())
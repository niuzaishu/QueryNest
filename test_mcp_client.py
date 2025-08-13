#!/usr/bin/env python3
"""测试MCP客户端连接的脚本"""

import asyncio
import json
import sys
import os
from pathlib import Path

# 添加项目路径到Python path
sys.path.insert(0, str(Path(__file__).parent))

async def test_mcp_connection():
    """测试MCP连接"""
    
    # 启动MCP服务器进程
    cmd = [
        "C:\\Users\\zaishu.niu\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
        "mcp_server.py",
        "--log-level", "DEBUG"
    ]
    
    print("启动MCP服务器进程...")
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(Path(__file__).parent)
    )
    
    # 发送初始化请求
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "test-client",
                "version": "1.0.0"
            }
        }
    }
    
    try:
        # 发送请求
        request_data = json.dumps(init_request) + '\n'
        print(f"发送初始化请求: {request_data.strip()}")
        
        process.stdin.write(request_data.encode())
        await process.stdin.drain()
        
        # 等待响应 
        response_data = await asyncio.wait_for(process.stdout.readline(), timeout=10.0)
        
        if response_data:
            response = response_data.decode().strip()
            print(f"收到响应: {response}")
            
            # 发送工具列表请求
            tools_request = {
                "jsonrpc": "2.0", 
                "id": 2,
                "method": "tools/list",
                "params": {}
            }
            
            request_data = json.dumps(tools_request) + '\n'
            print(f"发送工具列表请求: {request_data.strip()}")
            
            process.stdin.write(request_data.encode())
            await process.stdin.drain()
            
            # 等待工具列表响应
            tools_response = await asyncio.wait_for(process.stdout.readline(), timeout=10.0)
            if tools_response:
                print(f"工具列表响应: {tools_response.decode().strip()}")
        else:
            print("没有收到响应")
            
    except asyncio.TimeoutError:
        print("请求超时")
    except Exception as e:
        print(f"连接测试失败: {e}")
    finally:
        # 关闭进程
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            process.kill()
            
        # 读取错误输出
        stderr_data = await process.stderr.read()
        if stderr_data:
            print(f"错误输出: {stderr_data.decode()}")
            
    print("测试完成")

if __name__ == "__main__":
    asyncio.run(test_mcp_connection())
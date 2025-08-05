# QueryNest MCP Server 启动脚本
Write-Host "Starting QueryNest MCP Server..." -ForegroundColor Green

# 设置工作目录
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# 设置环境变量
$env:QUERYNEST_CONFIG_PATH = Join-Path $ScriptDir "config.yaml"

# 启动服务
try {
    python mcp_server.py
} catch {
    Write-Host "Failed to start QueryNest MCP Server: $_" -ForegroundColor Red
    Read-Host "Press Enter to continue..."
    exit 1
}

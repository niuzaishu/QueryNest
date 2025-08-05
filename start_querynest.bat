@echo off
echo Starting QueryNest MCP Server...
cd /d "%~dp0"
set QUERYNEST_CONFIG_PATH=%~dp0config.yaml
python mcp_server.py
if errorlevel 1 (
    echo Failed to start QueryNest MCP Server
    pause
    exit /b 1
)

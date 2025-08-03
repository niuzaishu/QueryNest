FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y     gcc     && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建必要目录
RUN mkdir -p logs data cache temp

# 设置环境变量
    ENV PYTHONPATH=/app
    ENV QUERYNEST_CONFIG_PATH=/app/config.yaml
    ENV QUERYNEST_LOG_LEVEL=INFO
    ENV QUERYNEST_MCP_TRANSPORT=stdio

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "start.py"]

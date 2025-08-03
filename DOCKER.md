# QueryNest Docker 部署指南

本指南将帮助您使用Docker快速部署QueryNest MongoDB多实例查询服务。

**项目地址**: [https://github.com/niuzaishu/QueryNest](https://github.com/niuzaishu/QueryNest)

## 📋 前置要求

- Docker Engine 20.10+
- Docker Compose 2.0+
- 至少4GB可用内存
- 至少10GB可用磁盘空间

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/niuzaishu/QueryNest.git
cd QueryNest
```

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑环境变量文件
nano .env  # 或使用您喜欢的编辑器
```

**重要**: 请修改 `.env` 文件中的默认密码和密钥！

### 3. 创建配置文件

```bash
# 创建配置目录
mkdir -p config

# 复制配置模板
cp config.yaml config/config.yaml

# 编辑配置文件以匹配Docker环境
nano config/config.yaml
```

### 4. 启动服务

```bash
# 启动基础服务（MongoDB + QueryNest）
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f querynest
```

## 🏗️ 服务架构

### 核心服务

| 服务 | 端口 | 描述 |
|------|------|------|
| `mongodb-prod` | 27017 | 生产环境MongoDB实例 |
| `mongodb-test` | 27018 | 测试环境MongoDB实例 |
| `mongodb-dev` | 27019 | 开发环境MongoDB实例 |
| `redis` | 6379 | 会话存储和缓存 |
| `querynest` | 8000 | QueryNest主服务 |

### 可选服务

使用 `--profile` 参数启动可选服务：

```bash
# 启动管理界面
docker-compose --profile management up -d

# 启动监控服务
docker-compose --profile monitoring up -d

# 启动所有服务
docker-compose --profile management --profile monitoring up -d
```

| 服务 | 端口 | 描述 | Profile |
|------|------|------|----------|
| `mongo-express` | 8081 | MongoDB Web管理界面 | management |
| `prometheus` | 9090 | 监控数据收集 | monitoring |
| `grafana` | 3000 | 监控数据可视化 | monitoring |

## ⚙️ 配置说明

### Docker配置文件

为Docker环境创建专用的配置文件 `config/config.yaml`：

```yaml
# MongoDB实例配置
mongodb:
  instances:
    docker-prod:
      name: "Docker生产环境"
      environment: "prod"
      connection_string: "mongodb://admin:${MONGO_PROD_PASSWORD}@mongodb-prod:27017/admin"
      database: "querynest_prod"
      description: "Docker生产环境MongoDB实例"
      status: "active"
      tags: ["prod", "docker"]
      
    docker-test:
      name: "Docker测试环境"
      environment: "test"
      connection_string: "mongodb://admin:${MONGO_TEST_PASSWORD}@mongodb-test:27017/admin"
      database: "querynest_test"
      description: "Docker测试环境MongoDB实例"
      status: "active"
      tags: ["test", "docker"]
      
    docker-dev:
      name: "Docker开发环境"
      environment: "dev"
      connection_string: "mongodb://admin:${MONGO_DEV_PASSWORD}@mongodb-dev:27017/admin"
      database: "querynest_dev"
      description: "Docker开发环境MongoDB实例"
      status: "active"
      tags: ["dev", "docker"]

# 元数据库配置
metadata:
  database_name: "querynest_metadata"
  collections:
    instances: "instances"
    databases: "databases"
    collections: "collections"
    fields: "fields"
    query_history: "query_history"
  retention:
    query_history_days: 30
    scan_history_days: 90

# MCP服务配置
mcp:
  name: "querynest"
  version: "0.1.0"
  description: "QueryNest MCP MongoDB查询服务"
  transport: "stdio"  # 默认使用stdio，可选http
  # 如果使用HTTP模式，取消注释以下配置
  # host: "0.0.0.0"
  # port: 8000

# 其他配置...
```

### 环境变量

在 `.env` 文件中配置以下变量：

```bash
# 必需配置
MONGO_PROD_PASSWORD=your_secure_password
MONGO_TEST_PASSWORD=your_secure_password
MONGO_DEV_PASSWORD=your_secure_password
REDIS_PASSWORD=your_secure_password

# 可选配置
MONGOEXPRESS_LOGIN=admin
MONGOEXPRESS_PASSWORD=your_secure_password
GRAFANA_USER=admin
GRAFANA_PASSWORD=your_secure_password
```

## 🔧 常用操作

### 服务管理

```bash
# 启动所有服务
docker-compose up -d

# 停止所有服务
docker-compose down

# 重启特定服务
docker-compose restart querynest

# 查看服务状态
docker-compose ps

# 查看服务日志
docker-compose logs -f querynest
docker-compose logs -f mongodb-prod
```

### 数据管理

```bash
# 备份MongoDB数据
docker-compose exec mongodb-prod mongodump --out /data/backup

# 恢复MongoDB数据
docker-compose exec mongodb-prod mongorestore /data/backup

# 清理所有数据（谨慎使用）
docker-compose down -v
```

### 服务调试

```bash
# 进入QueryNest容器
docker-compose exec querynest bash

# 进入MongoDB容器
docker-compose exec mongodb-prod mongosh

# 查看容器资源使用
docker stats
```

## 🧪 测试部署

### 1. 健康检查

```bash
# 检查所有服务健康状态
docker-compose ps

# 检查QueryNest服务
curl -f http://localhost:8000/health || echo "Service not ready"
```

### 2. 功能测试

```bash
# 进入QueryNest容器运行测试
docker-compose exec querynest python test_service.py --test-type basic
```

### 3. 连接测试

```bash
# 测试MongoDB连接
docker-compose exec mongodb-prod mongosh -u admin -p

# 测试Redis连接
docker-compose exec redis redis-cli -a your_redis_password ping
```

## 📊 监控和管理

### MongoDB Express

访问 http://localhost:8081 使用Web界面管理MongoDB：

- 用户名：在 `.env` 文件中配置的 `MONGOEXPRESS_LOGIN`
- 密码：在 `.env` 文件中配置的 `MONGOEXPRESS_PASSWORD`

### Prometheus监控

访问 http://localhost:9090 查看监控指标：

- QueryNest服务指标
- MongoDB性能指标
- 系统资源使用情况

### Grafana可视化

访问 http://localhost:3000 查看监控仪表板：

- 用户名：在 `.env` 文件中配置的 `GRAFANA_USER`
- 密码：在 `.env` 文件中配置的 `GRAFANA_PASSWORD`

## 🔒 安全配置

### 1. 密码安全

- 使用强密码
- 定期更换密码
- 不要在代码中硬编码密码

### 2. 网络安全

```yaml
# 在生产环境中，限制端口暴露
services:
  mongodb-prod:
    ports:
      - "127.0.0.1:27017:27017"  # 只绑定到本地
```

### 3. 数据加密

```yaml
# 启用MongoDB加密
services:
  mongodb-prod:
    command: mongod --auth --bind_ip_all --tlsMode requireTLS
```

## 🚀 生产部署

### 1. 资源配置

```yaml
# 在docker-compose.yml中添加资源限制
services:
  querynest:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
```

### 2. 数据持久化

```yaml
# 使用外部卷进行数据持久化
volumes:
  mongodb_prod_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /opt/querynest/data/mongodb-prod
```

### 3. 备份策略

```bash
# 创建备份脚本
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
docker-compose exec -T mongodb-prod mongodump --archive | gzip > backup_${DATE}.gz
```

## 🐛 故障排除

### 常见问题

1. **服务启动失败**
   ```bash
   # 检查日志
   docker-compose logs querynest
   
   # 检查配置文件
   docker-compose config
   ```

2. **MongoDB连接失败**
   ```bash
   # 检查MongoDB状态
   docker-compose exec mongodb-prod mongosh --eval "db.adminCommand('ismaster')"
   
   # 检查网络连接
   docker-compose exec querynest ping mongodb-prod
   ```

3. **权限问题**
   ```bash
   # 检查文件权限
   ls -la config/
   
   # 修复权限
   sudo chown -R $USER:$USER config/
   ```

### 性能优化

1. **增加内存限制**
   ```yaml
   services:
     mongodb-prod:
       command: mongod --auth --bind_ip_all --wiredTigerCacheSizeGB 2
   ```

2. **优化连接池**
   ```yaml
   # 在config.yaml中调整
   performance:
     connection_pool:
       max_pool_size: 50
       min_pool_size: 5
   ```

## 📚 更多资源

- [Docker官方文档](https://docs.docker.com/)
- [Docker Compose文档](https://docs.docker.com/compose/)
- [MongoDB Docker镜像](https://hub.docker.com/_/mongo)
- [QueryNest项目文档](./README.md)

## 🆘 获取帮助

如果遇到问题，请：

1. 查看服务日志：`docker-compose logs`
2. 检查配置文件语法
3. 查阅本文档的故障排除部分
4. 提交Issue到项目仓库
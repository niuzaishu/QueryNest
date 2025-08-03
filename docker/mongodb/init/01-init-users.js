// MongoDB初始化脚本
// 为每个实例创建QueryNest服务所需的用户和数据库（元数据库按需创建）

// 切换到admin数据库
db = db.getSiblingDB('admin');

// 获取环境变量中的密码，如果没有则使用默认值
const servicePassword = process.env.MONGO_SERVICE_PASSWORD || 'querynest_service_password';
const metadataPassword = process.env.MONGO_METADATA_PASSWORD || 'querynest_metadata_password';

// 创建QueryNest服务用户
db.createUser({
  user: 'querynest_service',
  pwd: servicePassword,
  roles: [
    {
      role: 'readWriteAnyDatabase',
      db: 'admin'
    },
    {
      role: 'dbAdminAnyDatabase',
      db: 'admin'
    },
    {
      role: 'clusterMonitor',
      db: 'admin'
    }
  ]
});

// 为当前实例创建元数据数据库
db = db.getSiblingDB('querynest_metadata');

// 创建元数据管理用户
db.createUser({
  user: 'querynest_metadata',
  pwd: metadataPassword,
  roles: [
    {
      role: 'readWrite',
      db: 'querynest_metadata'
    }
  ]
});

// 创建基础集合
db.createCollection('instances');
db.createCollection('databases');
db.createCollection('collections');
db.createCollection('fields');
db.createCollection('queries');
db.createCollection('query_history');

// 创建索引
db.instances.createIndex({ "instance_id": 1 }, { unique: true });
db.databases.createIndex({ "instance_id": 1, "database_name": 1 }, { unique: true });
db.collections.createIndex({ "instance_id": 1, "database_name": 1, "collection_name": 1 }, { unique: true });
db.fields.createIndex({ "instance_id": 1, "database_name": 1, "collection_name": 1, "field_path": 1 }, { unique: true });
db.queries.createIndex({ "query_id": 1 }, { unique: true });
db.query_history.createIndex({ "query_id": 1, "executed_at": -1 });
db.query_history.createIndex({ "executed_at": -1 });

// 插入当前实例的示例数据
// 注意：每个实例只记录自己的信息，不再记录其他实例
// 实例发现将通过配置文件和连接管理器来实现

// 可以根据环境变量来确定当前实例的信息
// 这里提供一个通用的示例
var currentInstance = {
  instance_name: process.env.INSTANCE_NAME || 'current-instance',
  instance_alias: process.env.INSTANCE_ALIAS || '当前实例',
  description: process.env.INSTANCE_DESCRIPTION || '当前MongoDB实例的元数据库',
  environment: process.env.INSTANCE_ENVIRONMENT || 'docker',
  created_at: new Date(),
  updated_at: new Date(),
  status: 'active'
};

db.instances.insertOne(currentInstance);

print('QueryNest MongoDB初始化完成');
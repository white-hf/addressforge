# AddressForge 快速开始

> 这是一份给新开发者的最短可运行路径。  
> 目标是在最少步骤内跑通：初始化、导入样例、清洗、训练、启动 API。

## 1. 先准备环境

```bash
cd addressforge
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
cp .env.example src/addressforge/core/.env.local
```

然后在 `src/addressforge/core/.env.local` 中填写本地数据库配置。

## 2. 初始化 schema

```bash
./scripts/init_schema.sh
```

这一步会创建最小表：

- `etl_run`
- `source_ingestion_cursor`
- `raw_address_record`
- `external_building_reference`

## 3. 用示例 CSV 跑通最小导入

```bash
export ADDRESSFORGE_IMPORT_CSV_PATH=examples/sample_raw_addresses.csv
./scripts/import_csv.sh
```

这一步会把示例地址写入 `raw_address_record`。

## 4. 跑一个 baseline 训练骨架

```bash
./scripts/run_training.sh
```

这一步会生成一个最小训练产物，先把训练闭环跑通。

## 5. 启动控制 worker

控制 worker 负责执行控制台排队的后台任务，例如增量导入、训练和后续的持续模式任务。

```bash
./scripts/run_control_worker.sh
```

## 6. 启动 API

```bash
./scripts/run_api.sh
```

启动后可以调用：

- `GET /health`
- `GET /api/v1/model`
- `POST /api/v1/normalize`
- `POST /api/v1/parse`
- `POST /api/v1/validate`
- `POST /api/v1/explain`

## 7. 如果你有自己的私有数据

你有两种接入方式。

### 6.1 API Pull

设置：

- `ADDRESSFORGE_INGESTION_MODE=api`
- `ADDRESSFORGE_INGESTION_API_URL=...`

然后运行：

```bash
./scripts/run_ingestion.sh
```

### 6.2 Database Direct Import

第三方把数据先导入自己控制的表，例如：

```sql
CREATE TABLE source_raw_address (
    external_id VARCHAR(128) PRIMARY KEY,
    raw_address_text TEXT NOT NULL,
    city VARCHAR(128),
    province VARCHAR(32),
    postal_code VARCHAR(16),
    latitude DOUBLE,
    longitude DOUBLE,
    updated_at DATETIME
);
```

然后设置：

- `ADDRESSFORGE_INGESTION_MODE=db`
- `ADDRESSFORGE_INGESTION_DB_HOST=...`
- `ADDRESSFORGE_INGESTION_DB_USER=...`
- `ADDRESSFORGE_INGESTION_DB_PASSWORD=...`
- `ADDRESSFORGE_INGESTION_DB_NAME=...`
- `ADDRESSFORGE_INGESTION_DB_TABLE=source_raw_address`

再运行：

```bash
./scripts/run_ingestion.sh
```

## 8. 最短路径总结

1. 初始化 schema
2. 导入示例 CSV
3. 跑 baseline 训练
4. 启动控制 worker
5. 启动 API
6. 用自己的私有数据替换示例数据

## 9. 结论

如果你只想先确认系统能跑起来，就按这份文档执行即可。  
先跑通最小闭环，再逐步替换成你自己的私有数据和自定义模型。

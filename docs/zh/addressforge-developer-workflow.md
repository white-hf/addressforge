# AddressForge 开发者工作流

> 适用于第一次接触 AddressForge 的开发者。  
> 目标是从“把自己的私有地址数据接进来”开始，逐步完成“清洗、训练、评估、部署 API、持续迭代”。

## 1. 这份文档的目标

AddressForge 是一个开源、自部署的地址智能平台。  
新开发者通常会遇到三个问题：

1. 我的原始地址数据放在哪里？
2. 我怎样把数据导入系统并开始清洗？
3. 我怎样把清洗结果、训练结果和 API 组合成我自己的项目？

这份文档按实际操作顺序回答这三个问题。

## 2. 推荐的项目形态

建议把自己的私有数据放在仓库外部，例如：

- `workspace/private_sources/`
- `workspace/imports/`
- `workspace/labels/`
- `workspace/training/`
- `workspace/artifacts/`

不要把私有地址样本、私有数据库密码、私有第三方接口地址提交到 git。

仓库里只保留：

- 代码
- schema
- 示例配置
- 文档

## 3. 第一步：准备本地环境

### 3.1 安装依赖

```bash
cd addressforge
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

### 3.2 配置本地变量

复制示例配置：

```bash
cp .env.example src/addressforge/core/.env.local
```

然后修改你自己的本地数据库和 ingestion 配置。

最少需要配置：

- `MYSQL_HOST`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE`
- `ADDRESSFORGE_DATABASE`
- `ADDRESSFORGE_INGESTION_MODE`

如果你用 API 拉取新增数据，还需要：

- `ADDRESSFORGE_INGESTION_API_URL`
- `ADDRESSFORGE_INGESTION_API_TOKEN`（如果对方接口需要）

如果你用数据库直导，还需要：

- `ADDRESSFORGE_INGESTION_DB_HOST`
- `ADDRESSFORGE_INGESTION_DB_USER`
- `ADDRESSFORGE_INGESTION_DB_PASSWORD`
- `ADDRESSFORGE_INGESTION_DB_NAME`
- `ADDRESSFORGE_INGESTION_DB_TABLE`

## 4. 第二步：初始化数据库

AddressForge 的最小 schema 在：

- `sql/addressforge_schema.sql`

建议先在本地库里创建这些基础表：

- `etl_run`
- `source_ingestion_cursor`
- `raw_address_record`
- `external_building_reference`

如果你已经有自己的业务库，也可以把它们建在同一个数据库中，只要表名前缀保持一致。

## 5. 第三步：接入你的私有地址数据

AddressForge 目前支持两种接入方式。

### 5.1 API Pull

适合第三方系统已经有自己的接口。

做法：

1. 第三方提供私有 API
2. AddressForge 按 cursor / batch 拉取新增原始地址
3. 拉到的数据写入 `raw_address_record`
4. 系统自动记录 `source_ingestion_cursor`

适合场景：

- 你的上游系统本来就会提供增量接口
- 你不想让私有数据离开原系统太久

### 5.2 Database Direct Import

适合第三方更偏 ETL / 数据库导入。

做法：

1. 第三方把原始地址导入他们控制的表
2. AddressForge 通过配置连接到该表
3. 读取新增行，写入 `raw_address_record`
4. 同样记录 cursor

适合场景：

- 你已经有自己的源数据库
- 你希望用数据库同步代替 API

### 5.3 运行 ingestion

```bash
./scripts/run_ingestion.sh
```

这一步只负责把第三方私有原始数据拉进平台，不负责完整清洗。

## 6. 第四步：运行解析和清洗

当前平台的对外 API 可以先直接使用默认加拿大 / 北美模型：

```bash
./scripts/run_api.sh
```

你可以把你的地址数据直接发到 API：

- `POST /api/v1/normalize`
- `POST /api/v1/parse`
- `POST /api/v1/validate`
- `POST /api/v1/explain`

这一步的作用是：

- 把原始文本标准化
- 拆出 building / unit / postal / city / province
- 给出校验结果
- 输出可解释信息

## 7. 第五步：建立你的清洗闭环

当你开始有自己的数据后，建议按以下顺序运行：

1. 拉取新增原始数据
2. 标准化地址
3. 解析 building / unit
4. 用 reference 校验
5. 生成待审核样本
6. 人工或 LLM 审核简单样本
7. 把结果写成金标
8. 再训练你自己的模型
9. 用训练后的模型继续清洗

这就是一个完整的本地个性化闭环。

## 8. 第六步：训练你自己的模型

AddressForge 的设计目标是允许你把默认加拿大模型换成你自己的模型。

推荐做法：

1. 从你的历史清洗结果里导出训练样本
2. 放到 `workspace/training/`
3. 在 `src/addressforge/learning/` 里实现你的训练脚本
4. 把训练产物放到 `models/<your_model_name>/`
5. 在 `.env.local` 里切换默认模型版本

如果你只想先用默认加拿大模型，也可以跳过训练这一步。

## 9. 第七步：部署你自己的 API

当你有了自己的模型后，可以继续用同一套 API 对外提供服务。

典型流程：

1. 训练并保存模型
2. 配置平台默认模型版本
3. 启动 API
4. 让你自己的业务系统调用：
   - 规范化
   - 解析
   - 校验
   - 解释

这样你的本地项目就从“清洗工具”变成了“地址解析服务”。

## 10. 推荐的开发顺序

如果你是第一次使用 AddressForge，建议按这个顺序做：

1. 配置本地数据库
2. 初始化 schema
3. 选择 ingestion 模式
4. 导入一小批私有样本
5. 跑一次 API 解析
6. 验证解析结果
7. 再导入更多数据
8. 生成标签
9. 训练自己的模型
10. 用训练模型替换默认模型
11. 发布你自己的 API

## 11. 常见错误

- 把私有数据直接提交到 git
  - 不要这样做
- 先追求大规模训练
  - 不要这样做
  - 先让最小闭环跑通
- 训练和 API 没有版本号
  - 不要这样做
  - 每次产物都要可追踪
- ingestion 和清洗混在一个脚本里
  - 不推荐
  - 这会让系统难以维护

## 12. 结论

新开发者最重要的目标不是“看懂所有代码”，而是：

- 把自己的私有地址数据接进来
- 让数据先跑通一轮清洗
- 有能力导出训练样本
- 能训练自己的模型
- 能把模型再用于自己的 API

这就是 AddressForge 的核心价值。

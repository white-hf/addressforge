# AddressForge 开源平台 API 文档

> 中文：开源、自部署地址平台的对外接口说明。

> English: Public API specification for the open-source, self-hosted address platform.

# Address Library AddressForge Open Source Platform API

## 1. 文档目的

这份文档说明 AddressForge 默认提供的公共 API。  
目标不是做一个复杂的 SaaS 网关，而是给自部署用户一个**稳定、可替换、可扩展**的地址解析入口。

默认版本以加拿大 / 北美模型为基础。

## 2. 启动方式

默认以本地服务方式运行。

启动脚本：

```bash
cd address-data-cleaning-system
./run_address_platform_api.sh
```

环境变量示例：

- `ADDRESSFORGE_PORT`
- `ADDRESSFORGE_DEFAULT_PROFILE`
- `ADDRESSFORGE_MODEL_VERSION`
- `ADDRESSFORGE_REFERENCE_VERSION`

启动后提供的主要能力是：

- `normalize`
- `parse`
- `validate`
- `explain`
- `model info`

## 3. API 列表

### 3.1 `GET /health`

返回服务健康状态。

### 3.2 `GET /api/v1/model`

返回当前平台默认模型、参考源和解析器版本信息。

### 3.3 `POST /api/v1/normalize`

输入原始地址，输出标准化文本和归一化结果。

### 3.4 `POST /api/v1/parse`

输入原始地址，输出多个 parser 候选、最高分候选和结构化字段。

### 3.5 `POST /api/v1/validate`

输入原始地址或解析结果，输出：

- `accept`
- `enrich`
- `review`
- `reject`

并附带：

- 置信度
- 单元补全建议
- building 类型提示
- reference 命中信息

### 3.6 `POST /api/v1/explain`

输出人类可读说明，用于调试、产品展示或二次确认。

## 4. 统一请求字段

典型请求字段如下：

- `raw_address_text`
- `city`
- `province`
- `postal_code`
- `country_code`
- `latitude`
- `longitude`
- `profile`
- `parsers`

## 5. 默认模型配置

默认配置是：

- `base_canada`

这表示：

- 使用加拿大地址规则
- 使用加拿大默认 parser 组合
- 使用加拿大 reference / gold / history 作为默认参考

## 6. 面向自部署用户的设计说明

这套 API 是给别人下载代码后本地部署使用的。

他们可以：

- 保持默认加拿大模型直接使用
- 替换自己的 parser
- 替换自己的 reference
- 接入自己的数据后重新训练
- 输出自己的地址解析 API

## 7. 最小使用建议

如果你只想快速上线：

1. 先启动默认 API
2. 调 `normalize`
3. 调 `parse`
4. 需要时调 `validate`
5. 用 `model info` 确认当前版本

## 8. 说明

这是 AddressForge 公共 API 的第一版说明。  
后续会继续补充：

- 请求 / 响应示例
- 错误码
- 批量接口
- 异步任务接口
- 自定义模型配置说明

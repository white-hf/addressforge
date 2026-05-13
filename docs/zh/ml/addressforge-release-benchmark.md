# AddressForge 发布评测标准

这份文档定义 AddressForge 在发布新模型、新规则或新清洗链路前，必须固定输出的一组 benchmark 指标。

目标不是只看“能不能跑通”，而是回答：

- 新版本是否比当前版本更准
- 哪一层更准了
- 哪一层退化了
- 是否值得 promote 为默认模型

## 1. 发布评测的原则

每次候选版本发布前，都应使用**冻结的 gold set**运行同一套评测。

评测必须至少覆盖：

- 地址解析
- 结构识别
- 最终决策
- 运行风格

## 2. 核心发布指标

AddressForge 当前固定追踪 8 个核心指标：

1. `decision_f1`
2. `building_type_f1`
3. `unit_number_f1`
4. `unit_recall`
5. `commercial_f1`
6. `accept_rate`
7. `review_rate`
8. `reject_rate`

## 3. 指标含义

### 3.1 `decision_f1`

衡量最终决策是否正确。

目标值越高越好。

### 3.2 `building_type_f1`

衡量地址是否被正确识别为：

- `single_unit`
- `multi_unit`
- `commercial`
- `unknown`

### 3.3 `unit_number_f1`

衡量系统是否正确识别、补全或保留单元号。

### 3.4 `unit_recall`

衡量系统是否漏掉本应识别出的 unit。

这是加拿大地址里非常关键的指标。

### 3.5 `commercial_f1`

衡量商业地址识别是否准确。

用于区分：

- 独栋住宅
- 多单元公寓
- 写字楼 / 商场 / 商业楼

### 3.6 `accept_rate`

衡量系统把多少地址直接接受为高置信结果。

### 3.7 `review_rate`

衡量系统把多少地址送去人工复核。

### 3.8 `reject_rate`

衡量系统拒绝了多少地址。

## 4. 什么时候允许发布

建议采用如下门槛：

- `decision_f1` 不低于当前 active
- `building_type_f1` 不低于当前 active
- `unit_number_f1` 不低于当前 active
- `unit_recall` 不退化
- `commercial_f1` 不退化
- `review_rate` 不异常升高
- `reject_rate` 不异常升高

## 5. 当前 evaluator 的输出

当前 evaluator 会把以下内容写入 `metrics_json`：

- `decision`
- `building_type`
- `unit_number`
- `commercial`
- `runtime_distribution`
- `release_benchmark`

其中 `release_benchmark` 是发布判断时最重要的一组固定指标。

## 6. 推荐发布流程

1. 冻结 gold
2. 训练候选模型
3. 运行 evaluation
4. 检查 `release_benchmark`
5. 运行 shadow
6. 对比 active 与 candidate
7. 满足门槛后 promote


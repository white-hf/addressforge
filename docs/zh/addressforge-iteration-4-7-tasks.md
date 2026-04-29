# AddressForge 后续迭代任务清单 (Iterations 4-7)

## Iteration 4: Training, Evaluation, Shadow, Promote
- [ ] **任务 4.1**: 实现 `trainer.py` 的标准化训练闭环，支持模型版本化保存。
- [ ] **任务 4.2**: 完善 `shadow.py`，实现新模型在生产流量下的影子预测与评估。
- [ ] **任务 4.3**: 构建发布门禁 (Release Gate)，自动对比 `shadow` 与 `active` 模型的 Benchmark 结果。

## Iteration 5: Canonical Address and Reference Quality
- [ ] **任务 5.1**: 实现 `canonical_building` 和 `canonical_unit` 的自动去重与合并逻辑。
- [ ] **任务 5.2**: 完善 `reference-first` 决策机制，在 Parser 冲突时优先选择 Reference 证据。

## Iteration 6: Historical Replay and Release Readiness
- [ ] **任务 6.1**: 开发 `historical_replay.py`，支持基于固定数据集重跑清洗流程并生成对比报告。
- [ ] **任务 6.2**: 完善版本间对比工具，量化版本迭代带来的准确率提升。

## Iteration 7: Country Abstraction
- [ ] **任务 7.1**: 将 Canada 逻辑从核心流水线剥离，抽象出 `CountryProfile` 基类。
- [ ] **任务 7.2**: 定义 `Parser` / `Reference` / `Validator` 的接口适配器，实现多国家可插拔配置。

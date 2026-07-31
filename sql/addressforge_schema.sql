-- =========================================================
-- AddressForge Core Schema
-- =========================================================

-- 表 1: etl_run
-- 目的: 记录系统内所有异步流水线和任务的运行实例（如清洗、训练、评估）。
CREATE TABLE IF NOT EXISTS etl_run (
    run_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_type ENUM('ingestion','history_import','normalize','parse','evidence_aggregate','publish','user_profile','ml_export','ml_train','ml_eval','ml_shadow','ml_gold','ml_active_learning','incremental_pipeline','control_job') NOT NULL,
    parser_version VARCHAR(64) DEFAULT NULL,
    scoring_version VARCHAR(64) DEFAULT NULL,
    status ENUM('running','completed','failed','paused') NOT NULL DEFAULT 'running',
    notes MEDIUMTEXT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP NULL DEFAULT NULL,
    INDEX idx_etl_run_type_status (run_type, status, created_at)
) COMMENT='任务运行实例表，用于追踪所有异步操作的状态';

-- 表 2: source_ingestion_cursor
-- 目的: 存储不同外部数据源的同步偏移量（游标），确保增量同步不遗漏、不重复。
CREATE TABLE IF NOT EXISTS source_ingestion_cursor (
    cursor_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL DEFAULT 'default',
    source_system VARCHAR(64) NOT NULL,
    cursor_type VARCHAR(64) NOT NULL,
    cursor_value TEXT NOT NULL,
    last_success_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_source_cursor (workspace_name, source_system, cursor_type)
) COMMENT='数据摄取游标表，记录增量同步的进度';

-- 表 3: workspace_registry
-- 目的: 定义多租户/工作区环境，管理每个工作区的默认模型、语言和参考库版本。
CREATE TABLE IF NOT EXISTS workspace_registry (
    workspace_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL,
    description TEXT DEFAULT NULL,
    default_model_id BIGINT DEFAULT NULL,
    default_profile VARCHAR(64) NOT NULL DEFAULT 'base_canada',
    default_reference_version VARCHAR(64) DEFAULT NULL,
    default_language VARCHAR(16) NOT NULL DEFAULT 'en',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_workspace_name (workspace_name),
    KEY idx_workspace_default_model (default_model_id)
) COMMENT='工作区注册表，配置多租户环境参数';

-- 表 4: model_registry
-- 目的: 存储机器学习模型的元数据、指标和构件路径，支持模型的版本管理与发布。
CREATE TABLE IF NOT EXISTS model_registry (
    model_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL,
    model_name VARCHAR(128) NOT NULL,
    model_version VARCHAR(64) NOT NULL,
    model_family VARCHAR(64) NOT NULL DEFAULT 'baseline',
    status ENUM('draft','trained','evaluated','promoted','deprecated') NOT NULL DEFAULT 'draft',
    is_default BOOLEAN NOT NULL DEFAULT 0,
    default_profile VARCHAR(64) NOT NULL DEFAULT 'base_canada',
    dataset_name VARCHAR(128) DEFAULT NULL,
    training_run_id BIGINT DEFAULT NULL,
    evaluation_run_id BIGINT DEFAULT NULL,
    reference_version VARCHAR(64) DEFAULT NULL,
    rule_version VARCHAR(64) DEFAULT NULL,
    artifact_path TEXT DEFAULT NULL,
    metrics_json JSON DEFAULT NULL,
    notes MEDIUMTEXT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    promoted_at TIMESTAMP NULL DEFAULT NULL,
    UNIQUE KEY uq_model_version (workspace_name, model_name, model_version),
    KEY idx_model_workspace_status (workspace_name, status, created_at),
    KEY idx_model_workspace_default (workspace_name, is_default, created_at)
) COMMENT='模型注册表，管理 ML 模型的全生命周期';

-- 表 5: control_job
-- 目的: 任务队列系统，存储由控制台触发的所有后台任务指令。
CREATE TABLE IF NOT EXISTS control_job (
    job_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL,
    job_kind VARCHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'queued',
    priority INT NOT NULL DEFAULT 0,
    requested_by VARCHAR(64) DEFAULT NULL,
    claimed_by VARCHAR(128) DEFAULT NULL,
    payload_json JSON DEFAULT NULL,
    result_json JSON DEFAULT NULL,
    error_text TEXT DEFAULT NULL,
    etl_run_id BIGINT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_at TIMESTAMP NULL DEFAULT NULL,
    started_at TIMESTAMP NULL DEFAULT NULL,
    finished_at TIMESTAMP NULL DEFAULT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_control_job_status_priority (status, priority, created_at),
    KEY idx_control_job_workspace_status (workspace_name, status, created_at),
    KEY idx_control_job_kind (job_kind, status, created_at),
    KEY idx_control_job_etl_run (etl_run_id)
) COMMENT='控制任务表，充当系统的任务队列';

-- 表 6: control_setting
-- 目的: 存储系统运行时的动态配置参数（如摄取模式、API 批量大小等）。
CREATE TABLE IF NOT EXISTS control_setting (
    setting_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL,
    setting_key VARCHAR(128) NOT NULL,
    setting_value TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_control_setting (workspace_name, setting_key),
    KEY idx_control_setting_workspace (workspace_name, updated_at)
) COMMENT='控制设置表，存储持久化的动态系统配置';

-- 表 7: gold_label
-- 目的: 存储经人工或高置信度验证后的“黄金标准”地址数据，作为 ML 训练的真值。
CREATE TABLE IF NOT EXISTS gold_label (
    gold_label_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL,
    source_name VARCHAR(64) NOT NULL DEFAULT 'human',
    source_id VARCHAR(128) NOT NULL,
    task_type VARCHAR(64) NOT NULL,
    label_json JSON NOT NULL,
    review_status ENUM('pending','accepted','rejected') NOT NULL DEFAULT 'pending',
    label_source ENUM('human','weak_rule','llm_assist','import','model') NOT NULL DEFAULT 'human',
    score DECIMAL(6,4) DEFAULT NULL,
    notes MEDIUMTEXT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_gold_label_source (workspace_name, source_name, source_id, task_type),
    KEY idx_gold_label_workspace_status (workspace_name, review_status, task_type, created_at),
    KEY idx_gold_label_workspace_source (workspace_name, label_source, created_at),
    KEY idx_gold_label_source_id (workspace_name, source_id)
) COMMENT='黄金标签表，存储经人工审核确认的真值数据';

-- 表 8: gold_set_snapshot
-- 目的: 记录金标数据集的静态快照版本，用于模型训练时的可重复性验证。
CREATE TABLE IF NOT EXISTS gold_set_snapshot (
    snapshot_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL,
    gold_set_version VARCHAR(64) NOT NULL,
    split_version VARCHAR(64) NOT NULL,
    label_source_filter VARCHAR(64) NOT NULL DEFAULT 'human',
    task_type VARCHAR(64) DEFAULT NULL,
    sample_count INT NOT NULL DEFAULT 0,
    train_count INT NOT NULL DEFAULT 0,
    eval_count INT NOT NULL DEFAULT 0,
    test_count INT NOT NULL DEFAULT 0,
    notes MEDIUMTEXT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_gold_snapshot (workspace_name, gold_set_version, split_version, label_source_filter, task_type),
    KEY idx_gold_snapshot_workspace_created (workspace_name, created_at)
) COMMENT='金标集快照表，定义用于训练/测试的数据集版本';

-- 表 9: gold_set_member
-- 目的: 映射金标快照与具体标签的关系，并定义其在训练/评估/测试集中的角色。
CREATE TABLE IF NOT EXISTS gold_set_member (
    member_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL,
    snapshot_id BIGINT NOT NULL,
    gold_label_id BIGINT NOT NULL,
    split_name ENUM('train','eval','test') NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_gold_snapshot_member (snapshot_id, gold_label_id),
    KEY idx_gold_member_workspace_split (workspace_name, snapshot_id, split_name),
    KEY idx_gold_member_workspace_label (workspace_name, gold_label_id)
) COMMENT='金标集成员表，记录快照中每个样本的集合归属';

-- 表 10: active_learning_queue
-- 目的: 存储主动学习（Active Learning）抽取的样本，等待人工审核。
CREATE TABLE IF NOT EXISTS active_learning_queue (
    queue_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL,
    source_name VARCHAR(64) NOT NULL DEFAULT 'address_cleaning_result',
    source_id VARCHAR(128) NOT NULL,
    task_type VARCHAR(64) NOT NULL,
    priority INT NOT NULL DEFAULT 0,
    confidence DECIMAL(6,4) DEFAULT NULL,
    reason TEXT DEFAULT NULL,
    status ENUM('queued','exported','labeled','skipped') NOT NULL DEFAULT 'queued',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_active_learning_source (workspace_name, source_name, source_id, task_type),
    KEY idx_active_learning_workspace_status (workspace_name, status, priority, created_at),
    KEY idx_active_learning_source_id (workspace_name, source_id)
) COMMENT='主动学习队列表，存储系统筛选出待人工审核的困难样本';

-- 表 11: review_prescreen_cache
-- 目的: 缓存 LLM 或预审逻辑对样本的初步判断，减少重复计算。
CREATE TABLE IF NOT EXISTS review_prescreen_cache (
    prescreen_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL,
    source_name VARCHAR(64) NOT NULL,
    source_id VARCHAR(128) NOT NULL,
    task_type VARCHAR(64) NOT NULL,
    llm_json JSON NOT NULL,
    llm_model VARCHAR(128) DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_review_prescreen_source (workspace_name, source_name, source_id, task_type),
    KEY idx_review_prescreen_workspace (workspace_name, updated_at)
) COMMENT='审核预筛缓存表，加速人工审核页面的加载';

-- 表 12: address_cleaning_result
-- 目的: 存储清洗后的结构化地址和系统的最终决策结果，是核心业务输出表。
CREATE TABLE IF NOT EXISTS address_cleaning_result (
    result_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL,
    raw_id BIGINT NOT NULL,
    raw_address_text TEXT NOT NULL,
    normalize_json JSON DEFAULT NULL,
    decision VARCHAR(32) NOT NULL,
    confidence DECIMAL(6,4) DEFAULT NULL,
    reason TEXT DEFAULT NULL,
    building_type VARCHAR(32) DEFAULT NULL,
    suggested_unit_number VARCHAR(64) DEFAULT NULL,
    base_address_key VARCHAR(128) DEFAULT NULL,
    full_address_key VARCHAR(128) DEFAULT NULL,
    parser_json JSON DEFAULT NULL,
    validation_json JSON DEFAULT NULL,
    reference_json JSON DEFAULT NULL,
    checkpoint_stage VARCHAR(32) DEFAULT NULL,
    checkpoint_status VARCHAR(24) NOT NULL DEFAULT 'pending',
    checkpoint_error TEXT DEFAULT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_cleaning_result_workspace_raw (workspace_name, raw_id),
    KEY idx_cleaning_result_workspace_processed (workspace_name, processed_at),
    KEY idx_cleaning_result_decision (workspace_name, decision, processed_at),
    KEY idx_cleaning_result_confidence (workspace_name, confidence),
    KEY idx_cleaning_result_full_scan (workspace_name, checkpoint_status, updated_at, raw_id)
) COMMENT='地址清洗结果表，记录每一条原始地址的最终结构化结果及决策';

-- 表 13: historical_replay_run
-- 目的: 记录“历史重跑”实验的概览信息，对比新老模型的表现。
CREATE TABLE IF NOT EXISTS historical_replay_run (
    replay_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL,
    run_id BIGINT NOT NULL,
    model_name VARCHAR(128) NOT NULL,
    model_version VARCHAR(64) NOT NULL,
    candidate_model_id BIGINT DEFAULT NULL,
    active_model_id BIGINT DEFAULT NULL,
    requested_count INT NOT NULL DEFAULT 0,
    processed_count INT NOT NULL DEFAULT 0,
    failure_count INT NOT NULL DEFAULT 0,
    disagreement_count INT NOT NULL DEFAULT 0,
    decision_match_rate DECIMAL(6,4) NOT NULL DEFAULT 0.0000,
    building_type_match_rate DECIMAL(6,4) NOT NULL DEFAULT 0.0000,
    unit_number_match_rate DECIMAL(6,4) NOT NULL DEFAULT 0.0000,
    status VARCHAR(24) NOT NULL DEFAULT 'completed',
    error_text TEXT DEFAULT NULL,
    candidate_runtime_identity_json JSON DEFAULT NULL,
    active_runtime_identity_json JSON DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL DEFAULT NULL,
    UNIQUE KEY uq_historical_replay_run (workspace_name, run_id),
    KEY idx_historical_replay_workspace_created (workspace_name, created_at)
) COMMENT='历史重跑实验表，用于衡量模型迭代的线上收益';

-- 表 14: historical_replay_result
-- 目的: 存储历史重跑实验中每一条记录的具体预测对比。
CREATE TABLE IF NOT EXISTS historical_replay_result (
    replay_result_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL,
    run_id BIGINT NOT NULL,
    raw_id BIGINT NOT NULL,
    current_decision VARCHAR(32) DEFAULT NULL,
    current_building_type VARCHAR(32) DEFAULT NULL,
    current_unit_number VARCHAR(64) DEFAULT NULL,
    candidate_decision VARCHAR(32) DEFAULT NULL,
    candidate_building_type VARCHAR(32) DEFAULT NULL,
    candidate_unit_number VARCHAR(64) DEFAULT NULL,
    active_decision VARCHAR(32) DEFAULT NULL,
    active_building_type VARCHAR(32) DEFAULT NULL,
    active_unit_number VARCHAR(64) DEFAULT NULL,
    decision_match BOOLEAN NOT NULL DEFAULT 0,
    building_type_match BOOLEAN NOT NULL DEFAULT 0,
    unit_number_match BOOLEAN NOT NULL DEFAULT 0,
    candidate_vs_active_different BOOLEAN NOT NULL DEFAULT 0,
    candidate_vs_current_different BOOLEAN NOT NULL DEFAULT 0,
    active_vs_current_different BOOLEAN NOT NULL DEFAULT 0,
    processing_status VARCHAR(24) NOT NULL DEFAULT 'success',
    error_text TEXT DEFAULT NULL,
    current_output_json JSON DEFAULT NULL,
    candidate_output_json JSON DEFAULT NULL,
    active_output_json JSON DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_historical_replay_result (workspace_name, run_id, raw_id),
    KEY idx_historical_replay_result_workspace_run (workspace_name, run_id),
    KEY idx_historical_replay_result_different (workspace_name, run_id, candidate_vs_active_different),
    KEY idx_historical_replay_result_status (workspace_name, run_id, processing_status)
) COMMENT='历史重跑结果表，详细记录新旧模型对同一地址的决策差异';

-- 表 15: raw_address_record
-- 目的: AddressForge 系统的内部原始数据存储基座。
-- 说明: 无论数据是通过 API 还是 DB 导入，最终都会在此表汇聚，以便统一清洗。
CREATE TABLE IF NOT EXISTS raw_address_record (
    raw_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL DEFAULT 'default',
    source_name VARCHAR(64) NOT NULL,
    external_id VARCHAR(128) NOT NULL,
    raw_address_text TEXT NOT NULL,
    city VARCHAR(128) DEFAULT NULL,
    province VARCHAR(32) DEFAULT NULL,
    postal_code VARCHAR(16) DEFAULT NULL,
    country_code VARCHAR(8) NOT NULL DEFAULT 'CA',
    latitude DOUBLE DEFAULT NULL,
    longitude DOUBLE DEFAULT NULL,
    source_cursor TEXT DEFAULT NULL,
    source_payload JSON DEFAULT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_raw_address_source_external (workspace_name, source_name, external_id),
    KEY idx_raw_address_workspace (workspace_name, source_name),
    KEY idx_raw_address_source_cursor (source_name, source_cursor(128)),
    KEY idx_raw_address_active (is_active, source_name)
) COMMENT='原始地址存储表，系统所有后续处理的源头';

-- 表 16: external_building_reference
-- 目的: 存储外部官方参考地址库（如 GeoNova），用于辅助解析和验证。
CREATE TABLE IF NOT EXISTS external_building_reference (
    reference_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL DEFAULT 'default',
    source_name VARCHAR(64) NOT NULL,
    external_id VARCHAR(128) NOT NULL,
    segment_id VARCHAR(128) DEFAULT NULL,
    street_number VARCHAR(32) NOT NULL,
    street_name VARCHAR(255) NOT NULL,
    unit_number VARCHAR(64) DEFAULT NULL,
    city VARCHAR(128) DEFAULT NULL,
    municipality VARCHAR(128) DEFAULT NULL,
    county VARCHAR(128) DEFAULT NULL,
    province VARCHAR(32) NOT NULL,
    postal_code VARCHAR(16) DEFAULT NULL,
    reference_lat DOUBLE DEFAULT NULL,
    reference_lon DOUBLE DEFAULT NULL,
    reference_tier ENUM('authoritative','semi_authoritative','weak') NOT NULL DEFAULT 'weak',
    quality_score DECIMAL(6,4) NOT NULL DEFAULT 0.0000,
    raw_payload JSON DEFAULT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_external_building_reference (workspace_name, source_name, external_id),
    KEY idx_external_building_reference_active (workspace_name, is_active, source_name),
    KEY idx_external_building_reference_coarse (street_number, street_name(64), province, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='外部参考地址表，存储官方地理实体数据';

-- 表 17: canonical_building
-- 目的: 存储经过聚合与决策后的“标准建筑资产”。
CREATE TABLE IF NOT EXISTS canonical_building (
    building_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL DEFAULT 'default',
    building_key CHAR(64) NOT NULL COMMENT 'SHA256 Hash of street number, name, city, province, country',
    street_number VARCHAR(32) NOT NULL,
    street_name VARCHAR(255) NOT NULL,
    city VARCHAR(128) NOT NULL,
    province VARCHAR(32) NOT NULL,
    postal_code VARCHAR(16) DEFAULT NULL,
    country_code VARCHAR(8) NOT NULL DEFAULT 'CA',
    latitude DOUBLE DEFAULT NULL,
    longitude DOUBLE DEFAULT NULL,
    source_attribution JSON DEFAULT NULL COMMENT 'Audit trail of source raw IDs',
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_canonical_building_key (workspace_name, building_key),
    KEY idx_canonical_building_geo (latitude, longitude),
    KEY idx_canonical_building_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='标准建筑资产表，存储清洗后归一化的唯一建筑实体';

-- 表 18: canonical_unit
-- 目的: 存储“标准单元资产”，并关联其所属的建筑。
CREATE TABLE IF NOT EXISTS canonical_unit (
    unit_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL DEFAULT 'default',
    unit_key CHAR(64) NOT NULL COMMENT 'SHA256 Hash of building_key and unit_number',
    building_key CHAR(64) NOT NULL,
    unit_number VARCHAR(64) NOT NULL,
    unit_type VARCHAR(32) DEFAULT NULL COMMENT 'e.g. APT, SUITE, BSMT',
    source_attribution JSON DEFAULT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_canonical_unit_key (workspace_name, unit_key),
    KEY idx_canonical_unit_building (building_key),
    KEY idx_canonical_unit_active (is_active),
    CONSTRAINT fk_canonical_unit_building FOREIGN KEY (workspace_name, building_key) REFERENCES canonical_building (workspace_name, building_key) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='标准单元资产表，存储建筑内部的归一化单元实体';

-- =========================================================
-- 外部/导入专用 Landing 表 ( Landing Tables )
-- =========================================================

-- 表 19: source_raw_address (外部源 Landing 占位符)
-- 目的: 作为“外部数据源”的示例或落地表。
-- 说明: 只有在控制台 System Settings 中配置了 DB 导入模式且指向此表时，Worker 才会扫描此表并同步到 raw_address_record。
CREATE TABLE IF NOT EXISTS source_raw_address (
    id INT AUTO_INCREMENT PRIMARY KEY,
    external_id VARCHAR(128) COMMENT '外部系统主键ID',
    raw_address_text TEXT COMMENT '原始未清洗地址文本',
    city VARCHAR(128) DEFAULT NULL,
    province VARCHAR(32) DEFAULT NULL,
    postal_code VARCHAR(16) DEFAULT NULL,
    latitude DOUBLE DEFAULT NULL,
    longitude DOUBLE DEFAULT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) COMMENT='外部数据落地表，仅作为 DB 导入模式的默认示例数据源';

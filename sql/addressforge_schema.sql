CREATE TABLE IF NOT EXISTS etl_run (
    run_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_type ENUM('ingestion','history_import','normalize','parse','evidence_aggregate','publish','user_profile','ml_export','ml_train','ml_eval','ml_shadow','ml_gold','ml_active_learning','incremental_pipeline','control_job') NOT NULL,
    parser_version VARCHAR(64) DEFAULT NULL,
    scoring_version VARCHAR(64) DEFAULT NULL,
    status ENUM('running','completed','failed','paused') NOT NULL DEFAULT 'running',
    notes TEXT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP NULL DEFAULT NULL,
    INDEX idx_etl_run_type_status (run_type, status, created_at)
);

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
);

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
);

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
    notes TEXT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    promoted_at TIMESTAMP NULL DEFAULT NULL,
    UNIQUE KEY uq_model_version (workspace_name, model_name, model_version),
    KEY idx_model_workspace_status (workspace_name, status, created_at),
    KEY idx_model_workspace_default (workspace_name, is_default, created_at)
);

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
);

CREATE TABLE IF NOT EXISTS control_setting (
    setting_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL,
    setting_key VARCHAR(128) NOT NULL,
    setting_value TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_control_setting (workspace_name, setting_key),
    KEY idx_control_setting_workspace (workspace_name, updated_at)
);

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
    notes TEXT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_gold_label_source (workspace_name, source_name, source_id, task_type),
    KEY idx_gold_label_workspace_status (workspace_name, review_status, task_type, created_at),
    KEY idx_gold_label_workspace_source (workspace_name, label_source, created_at)
);

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
    notes TEXT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_gold_snapshot (workspace_name, gold_set_version, split_version, label_source_filter, task_type),
    KEY idx_gold_snapshot_workspace_created (workspace_name, created_at)
);

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
);

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
    KEY idx_active_learning_workspace_status (workspace_name, status, priority, created_at)
);

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
);

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
    KEY idx_cleaning_result_decision (workspace_name, decision, processed_at)
);

CREATE TABLE IF NOT EXISTS historical_replay_run (
    replay_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_name VARCHAR(64) NOT NULL,
    run_id BIGINT NOT NULL,
    model_name VARCHAR(128) NOT NULL,
    model_version VARCHAR(64) NOT NULL,
    processed_count INT NOT NULL DEFAULT 0,
    decision_match_rate DECIMAL(6,4) NOT NULL DEFAULT 0.0000,
    building_type_match_rate DECIMAL(6,4) NOT NULL DEFAULT 0.0000,
    unit_number_match_rate DECIMAL(6,4) NOT NULL DEFAULT 0.0000,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_historical_replay_run (workspace_name, run_id),
    KEY idx_historical_replay_workspace_created (workspace_name, created_at)
);

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
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_historical_replay_result (workspace_name, run_id, raw_id),
    KEY idx_historical_replay_result_workspace_run (workspace_name, run_id),
    KEY idx_historical_replay_result_different (workspace_name, run_id, candidate_vs_active_different)
);

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
);

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------
-- Canonical Address Assets (Iteration 5 & 6 Final Schema)
-- 标准地址资产 (迭代 5 与 6 最终态 Schema)
-- ---------------------------------------------------------

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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
    CONSTRAINT fk_canonical_unit_building FOREIGN KEY (workspace_name, building_key)         REFERENCES canonical_building (workspace_name, building_key) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

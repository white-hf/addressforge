CREATE TABLE IF NOT EXISTS etl_run (
    run_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_type ENUM('ingestion','history_import','normalize','parse','evidence_aggregate','publish','user_profile','ml_export','incremental_pipeline') NOT NULL,
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
    source_system VARCHAR(64) NOT NULL,
    cursor_type VARCHAR(64) NOT NULL,
    cursor_value TEXT NOT NULL,
    last_success_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_source_cursor (source_system, cursor_type)
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
    is_default TINYINT(1) NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS raw_address_record (
    raw_id BIGINT AUTO_INCREMENT PRIMARY KEY,
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
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_raw_address_source_external (source_name, external_id),
    KEY idx_raw_address_source_cursor (source_name, source_cursor(128)),
    KEY idx_raw_address_active (is_active, source_name)
);

CREATE TABLE IF NOT EXISTS external_building_reference (
    reference_id BIGINT AUTO_INCREMENT PRIMARY KEY,
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
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_external_building_reference (source_name, external_id),
    KEY idx_external_building_reference_active (is_active, source_name),
    KEY idx_external_building_reference_coarse (street_number, street_name(64), province, is_active)
);

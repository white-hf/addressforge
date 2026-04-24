# AddressForge Quick Start

> A shortest-path guide for new developers.  
> The goal is to get you from setup to ingestion, cleaning, training, and API serving with the fewest steps.

## 1. Prepare the environment

```bash
cd addressforge
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
cp .env.example src/addressforge/core/.env.local
```

Then fill in your local database configuration in `src/addressforge/core/.env.local`.

## 2. Initialize the schema

```bash
./scripts/init_schema.sh
```

This creates the minimal tables:

- `etl_run`
- `source_ingestion_cursor`
- `raw_address_record`
- `external_building_reference`

## 3. Run the sample CSV import

```bash
export ADDRESSFORGE_IMPORT_CSV_PATH=examples/sample_raw_addresses.csv
./scripts/import_csv.sh
```

This writes the sample addresses into `raw_address_record`.

## 4. Run the baseline training skeleton

```bash
./scripts/run_training.sh
```

This generates a minimal training artifact and proves the training loop works.

## 5. Start the API

```bash
./scripts/run_api.sh
```

Then you can call:

- `GET /health`
- `GET /api/v1/model`
- `POST /api/v1/normalize`
- `POST /api/v1/parse`
- `POST /api/v1/validate`
- `POST /api/v1/explain`

## 6. If you have your own private data

There are two supported ingestion paths.

### 6.1 API Pull

Set:

- `ADDRESSFORGE_INGESTION_MODE=api`
- `ADDRESSFORGE_INGESTION_API_URL=...`

Then run:

```bash
./scripts/run_ingestion.sh
```

### 6.2 Database Direct Import

The third party imports raw rows into a table it controls, for example:

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

Then set:

- `ADDRESSFORGE_INGESTION_MODE=db`
- `ADDRESSFORGE_INGESTION_DB_HOST=...`
- `ADDRESSFORGE_INGESTION_DB_USER=...`
- `ADDRESSFORGE_INGESTION_DB_PASSWORD=...`
- `ADDRESSFORGE_INGESTION_DB_NAME=...`
- `ADDRESSFORGE_INGESTION_DB_TABLE=source_raw_address`

Then run:

```bash
./scripts/run_ingestion.sh
```

## 7. Shortest path summary

1. Initialize the schema
2. Import the sample CSV
3. Run the baseline training skeleton
4. Start the API
5. Replace the sample data with your own private data

## 8. Conclusion

If you only want to confirm that the system works, follow this guide first.  
Then replace the sample inputs with your own private data and custom model.

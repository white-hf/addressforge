# AddressForge

AddressForge is an open-source, self-hosted address intelligence platform.

It ships with a default Canada / North America model and can be adapted to other regions by users who deploy it on their own infrastructure.

## Repository layout
- `src/addressforge/api/`: public parsing API
- `src/addressforge/console/`: control console
- `src/addressforge/core/`: shared parsing, reference, and database helpers
- `src/addressforge/pipelines/`: offline pipeline entry points
- `src/addressforge/learning/`: training and evaluation helpers
- `src/addressforge/models/`: model assets and model metadata
- `docs/zh/` and `docs/en/`: separate Chinese and English documentation trees
- `sql/`: minimal schema and bootstrap DDL
- `assets/`: bundled static assets
- `examples/`: example request payloads
- `workspace/`: local runtime workspace, not committed

## What it includes
- address normalization
- parser candidate generation
- validation and enrichment
- canonical building / unit production
- user historical address facts
- ingestion adapters for private third-party data
- control console for long-running jobs
- public parsing API

## Quick start
1. Copy the example environment file and fill in your local credentials.

```bash
cp .env.example src/addressforge/core/.env.local
```

2. Install dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

3. Start the API.

```bash
./scripts/run_api.sh
```

4. Run ingestion if you want to pull or import private source data.

```bash
./scripts/run_ingestion.sh
```

5. For a minimal end-to-end smoke test, use the built-in sample CSV.

```bash
./scripts/init_schema.sh
export ADDRESSFORGE_IMPORT_CSV_PATH=examples/sample_raw_addresses.csv
./scripts/import_csv.sh
./scripts/run_training.sh
```

If you run modules directly, make sure `src/` is on `PYTHONPATH` or install the package in editable mode.

## Configuration
Sensitive configuration is intentionally not committed.

- Put local database credentials in `src/addressforge/core/.env.local`
- Do not commit `.env`, `.env.local`, or any credentials file
- Use `.env.example` as the template
- Keep third-party source files outside git, for example under `workspace/private_sources/`

The default local configuration keys are:
- `MYSQL_HOST`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE`
- `ADDRESSFORGE_DATABASE`
- `ADDRESS_V2_DATABASE`
- `ADDRESSFORGE_PORT`
- `ADDRESSFORGE_CONSOLE_PORT`
- `ADDRESS_PLATFORM_VERSION`
- `ADDRESS_PLATFORM_MODEL_VERSION`
- `ADDRESS_PLATFORM_REFERENCE_VERSION`
- `ADDRESS_PLATFORM_DEFAULT_PROFILE`
- `ADDRESSFORGE_REFERENCE_FILE`
- `ADDRESSFORGE_INGESTION_MODE`
- `ADDRESSFORGE_INGESTION_API_URL`
- `ADDRESSFORGE_INGESTION_DB_HOST`
- `ADDRESSFORGE_INGESTION_DB_NAME`
- `ADDRESSFORGE_INGESTION_DB_TABLE`
- `SALT`

## Ingestion modes
AddressForge supports two private ingestion paths:

1. **API pull**
   - Configure `ADDRESSFORGE_INGESTION_MODE=api`
   - Set `ADDRESSFORGE_INGESTION_API_URL`
   - Optional bearer token can be set in `ADDRESSFORGE_INGESTION_API_TOKEN`
   - The third party keeps its data private and only exposes an API endpoint

2. **Database direct import**
   - Configure `ADDRESSFORGE_INGESTION_MODE=db`
   - Set source database credentials and source table name
   - The third party can import rows directly into a table they control
   - AddressForge reads the source table and ingests new rows

## Bundled schema
The minimal local schema is documented in:

- `sql/addressforge_schema.sql`

## Minimal developer path
If you want the shortest path to understand the system:

1. initialize the schema
2. import the sample CSV
3. run the baseline training skeleton
4. start the API
5. replace the sample data with your own private data

## Documentation
- Chinese docs: `docs/zh/README.md`
- English docs: `docs/en/README.md`
- Developer workflow: `docs/zh/addressforge-developer-workflow.md` / `docs/en/addressforge-developer-workflow.md`
- Quick start: `docs/zh/addressforge-quickstart.md` / `docs/en/addressforge-quickstart.md`
- Model training and tuning guide: `docs/zh/addressforge-model-training-guide.md` / `docs/en/addressforge-model-training-guide.md`

# AddressForge Developer Workflow

> For developers who are new to AddressForge.  
> The goal is to take you from “I have my own private address data” to “I can ingest, clean, train, and serve my own address API”.

## 1. What this document is for

AddressForge is an open-source, self-hosted address intelligence platform.  
New developers usually ask three questions:

1. Where should I put my raw address data?
2. How do I ingest it and start cleaning?
3. How do I turn the cleaned data, training process, and API into my own project?

This guide answers those questions in execution order.

## 2. Recommended project layout

Keep private data outside the repository, for example:

- `workspace/private_sources/`
- `workspace/imports/`
- `workspace/labels/`
- `workspace/training/`
- `workspace/artifacts/`

Do not commit private address samples, private database passwords, or private third-party URLs to git.

Keep only:

- code
- schemas
- sample configs
- docs

## 3. Step 1: Set up your local environment

### 3.1 Install dependencies

```bash
cd addressforge
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

### 3.2 Configure local variables

Copy the example config:

```bash
cp .env.example src/addressforge/core/.env.local
```

Then fill in your own local database and ingestion settings.

Minimum required values:

- `MYSQL_HOST`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE`
- `ADDRESSFORGE_DATABASE`
- `ADDRESSFORGE_INGESTION_MODE`

If you want API pull ingestion, also set:

- `ADDRESSFORGE_INGESTION_API_URL`
- `ADDRESSFORGE_INGESTION_API_TOKEN` if the source requires auth
- `ADDRESSFORGE_INGESTION_API_ADAPTER`
  - `generic`: standard cursor-style API
  - `legacy_batch_orders`: compatible with the older `getbatchlist -> getdriverordercountmerged -> getdriverordersinbatchlist` flow
- `ADDRESSFORGE_INGESTION_API_FIELD_MAPPING_JSON`: local field mapping that stays outside git

If you want database direct import, also set:

- `ADDRESSFORGE_INGESTION_DB_HOST`
- `ADDRESSFORGE_INGESTION_DB_USER`
- `ADDRESSFORGE_INGESTION_DB_PASSWORD`
- `ADDRESSFORGE_INGESTION_DB_NAME`
- `ADDRESSFORGE_INGESTION_DB_TABLE`

## 4. Step 2: Initialize the database

The minimal schema lives in:

- `sql/addressforge_schema.sql`

You should create these baseline tables locally:

- `etl_run`
- `source_ingestion_cursor`
- `raw_address_record`
- `external_building_reference`

If you already have your own business database, you can create them there as long as the names stay consistent.

## 5. Step 3: Connect your private address data

AddressForge currently supports two ingestion paths.

### 5.1 API Pull

Use this when the upstream system already exposes its own private endpoint.

Flow:

1. The third party exposes a private API
2. AddressForge pulls new raw address rows by cursor / batch
3. Rows are written into `raw_address_record`
4. The platform stores the ingestion cursor in `source_ingestion_cursor`

Best for:

- systems that already provide an incremental API
- cases where you want the private data to stay in the source system

### 5.2 Database Direct Import

Use this when the third party prefers ETL / database import.

Flow:

1. The third party imports raw addresses into a table they control
2. AddressForge connects to that table by configuration
3. New rows are read and written into `raw_address_record`
4. The cursor is updated as well

Best for:

- teams that already have a source database
- ETL-oriented workflows

### 5.3 Run ingestion

```bash
./scripts/run_ingestion.sh
```

This only ingests private raw data. It does not perform the full cleaning pipeline yet.

## 6. Step 4: Run parsing and serving

The public API can already be used with the default Canada / North America model:

```bash
./scripts/run_api.sh
```

You can call:

- `POST /api/v1/normalize`
- `POST /api/v1/parse`
- `POST /api/v1/validate`
- `POST /api/v1/explain`

What this gives you:

- normalized text
- building / unit parsing
- validation output
- human-readable explanation

## 7. Step 5: Build your cleaning loop

Once your own data is in the system, the recommended loop is:

1. ingest new raw data
2. normalize addresses
3. parse building / unit fields
4. validate against reference data
5. generate review samples
6. let humans or LLMs review the easy samples
7. write the results as labels
8. train your own model
9. use the trained model to clean the next round

That is the full local personalized loop.

## 8. Step 6: Train your own model

The platform is designed so you can replace the default Canada model with your own model.

Recommended approach:

1. export training samples from your cleaning results
2. place them under `workspace/training/`
3. implement your training scripts under `src/addressforge/learning/`
4. store artifacts under `models/<your_model_name>/`
5. switch the default model version in `.env.local`

If you only want to start with the default Canada model, you can skip this step.

## 9. Step 7: Serve your own API

After you have a trained model, you can keep using the same API surface.

Typical sequence:

1. train and save the model
2. point the platform to the new model version
3. start the API
4. let your own business system call:
   - normalize
   - parse
   - validate
   - explain

At that point, your local project becomes an address parsing service, not just a cleaning tool.

## 10. Recommended order of work

If you are new to AddressForge, follow this order:

1. configure the local database
2. initialize the schema
3. pick an ingestion mode
4. ingest a small private sample
5. run one parsing pass
6. inspect the result
7. ingest more data
8. generate labels
9. train your own model
10. replace the default model
11. serve your own API

## 11. Common mistakes

- committing private data to git
  - do not do this
- trying to start with large-scale training first
  - do not do this
  - get the smallest loop working first
- not versioning model / API outputs
  - do not do this
  - keep all artifacts traceable
- mixing ingestion and cleaning into one opaque script
  - not recommended
  - it becomes hard to debug and extend

## 12. Conclusion

The main goal for a new developer is not to understand every line of code.  
The main goal is to:

- connect private address data
- run one successful cleaning pass
- export training samples
- train a custom model
- serve that model through the API

That is the core value of AddressForge.

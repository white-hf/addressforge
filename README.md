# AddressForge

AddressForge is an open-source, self-hosted address intelligence platform for parsing, cleaning, validating, and serving address APIs.

It ships with a default Canada / North America model and can be adapted to other regions by users who deploy it on their own infrastructure.

## What AddressForge solves

Address data is usually messy:

- the same address appears in many formats
- apartments, suites, and commercial units are easy to miss
- historical address data is inconsistent
- raw input often needs standardization, validation, and enrichment before it is useful

AddressForge gives you a complete workflow for:

- ingesting address data
- normalizing and parsing it
- building canonical building / unit records
- validating and enriching new records
- collecting review labels and gold data
- training and tuning models
- exposing the result through an API

## Core concepts

The repository is organized around four runtime roles:

- **Ingestion service**: brings private third-party source data into the system
- **Cleaning pipeline**: normalizes, parses, validates, and materializes canonical records
- **Learning pipeline**: freezes gold, trains models, runs shadow evaluation, and promotes versions
- **Control console**: creates and observes jobs, shows status, and lets a human control the system

## Core capabilities

- Address normalization
- Parser candidate generation
- Building / unit detection
- Validation and enrichment
- Historical user address facts
- Model registry and version control
- Gold set review and freezing
- Training and tuning workflow
- Public parsing API
- Control console
- Private data ingestion

## Default model and extensibility

AddressForge is designed to be useful out of the box and still remain easy to customize.

- **Default model**
  - preconfigured Canada / North America baseline
  - ready for immediate local testing

- **Custom data**
  - users can connect their own private address sources
  - private source data stays outside git
  - ingestion supports API pull and direct database import

- **Custom models**
  - users can train their own parsing / validation / fusion models
  - users can run their own evaluation and shadow workflows
  - users can publish their own API behavior from their own deployment

## Architecture at a glance

```text
Private source data
        |
        v
   Ingestion service
        |
        v
 Cleaning pipeline -> Review / Gold set -> Training / Evaluation
        |                                   |
        v                                   v
   Canonical data ---------------------> Model tuning
        |
        v
   API + Control console
```

## Quick start

1. Copy the example environment file and fill in local credentials.

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

3. Initialize the schema.

```bash
./scripts/init_schema.sh
```

4. Import the sample CSV.

```bash
export ADDRESSFORGE_IMPORT_CSV_PATH=examples/sample_raw_addresses.csv
./scripts/import_csv.sh
```

5. Run the baseline training skeleton.

```bash
./scripts/run_training.sh
```

6. Start the API.

```bash
./scripts/run_api.sh
```

7. Start the console.

```bash
./scripts/run_console.sh
```

## API example

```bash
curl -s http://127.0.0.1:8000/health
```

```bash
curl -s http://127.0.0.1:8000/api/v1/model
```

## Documentation

- Chinese docs: `docs/zh/README.md`
- English docs: `docs/en/README.md`
- Developer workflow: `docs/zh/addressforge-developer-workflow.md` / `docs/en/addressforge-developer-workflow.md`
- Quick start: `docs/zh/addressforge-quickstart.md` / `docs/en/addressforge-quickstart.md`
- Model training and tuning guide: `docs/zh/addressforge-model-training-guide.md` / `docs/en/addressforge-model-training-guide.md`

## Project status

The current repository already includes:

- API skeleton
- console skeleton
- ingestion adapters
- baseline training scaffold
- schema bootstrap
- developer workflow docs
- quick start docs
- training and tuning docs

This repository is intended as a practical starting point for teams that want to:

- clean their own address data
- train their own models
- serve their own address API
- keep private data outside git

## Project structure

This section is intentionally short. The repository is organized around runtime roles rather than legacy version numbers.

- `src/addressforge/api/`: public parsing API
- `src/addressforge/console/`: control console
- `src/addressforge/core/`: shared parsing, reference, and database helpers
- `src/addressforge/pipelines/`: offline pipeline entry points
- `src/addressforge/learning/`: training and evaluation helpers
- `src/addressforge/models/`: model assets and model metadata
- `docs/zh/` and `docs/en/`: separate Chinese and English documentation trees
- `sql/`: minimal schema and bootstrap DDL
- `examples/`: example request payloads
- `workspace/`: local runtime workspace, not committed

## Configuration and privacy

Sensitive configuration is intentionally not committed.

- Put local database credentials in `src/addressforge/core/.env.local`
- Do not commit `.env`, `.env.local`, or any credentials file
- Use `.env.example` as the template
- Keep third-party source files outside git, for example under `workspace/private_sources/`

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

## License

See `LICENSE` in the repository root.

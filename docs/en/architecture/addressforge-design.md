# AddressForge Open Source Platform Design

> English: Design for an open-source, self-hosted, trainable address platform with public APIs.

> 中文：开源、自部署、可训练、可对外提供地址解析 API 的平台设计说明。

# Address Library AddressForge Open Source Platform Design

## 1. Design Goal

AddressForge is not just “a stronger internal cleaning system”. It is a **reference open-source platform**:

- ships with a default Canada / North America model
- can be self-hosted locally or on private infrastructure
- can ingest another party’s raw address data
- can train a user-specific model
- can expose public address parsing APIs
- can serve as a reference implementation that others adapt to their own country or region

In one sentence:

> AddressForge is an open-source address intelligence platform reference implementation, not a SaaS and not a multi-tenant hosted service.

## 2. Design Principles

1. **Canada / North America first**
   - make the default experience work well for Canada / North America
   - let other users adapt it afterward

2. **Open source and self-hosted**
   - code can be downloaded
   - models can be replaced
   - data stays under the operator’s control
   - no dependency on a central cloud service

3. **Separate online APIs from offline production**
   - online APIs handle parsing, normalization, validation, enrichment, and suggestions
   - offline pipelines handle cleaning, training, evaluation, and freezing

4. **Control console as the control plane**
   - the console triggers, pauses, and observes
   - backend workers execute the long-running work

5. **ML / LLM as primary enhancement layers**
   - rules provide the baseline guardrails
   - ML provides the main decision enhancement
   - LLM handles weak labels, explanations, and part of review replacement

## 3. Overall Architecture

AddressForge should be organized into 6 layers:

### 3.1 Data Layer

Stores all raw and derived data:

- raw facts
- normalization outputs
- parser candidates
- canonical building / unit entities
- validation results
- user facts
- external references
- gold labels
- model runs
- API usage / job records

### 3.2 Cleaning Layer

Turns raw addresses into canonical records:

- normalize
- parse
- publish canonical building / unit
- validate
- build user facts
- generate review tasks

### 3.3 Learning Layer

Learns from history and human feedback:

- reranker
- unit span detector
- building clustering
- validation triage
- confidence fusion
- active learning
- LLM weak labeling

### 3.4 API Serving Layer

Exposes stable public APIs:

- parse
- normalize
- validate
- enrich
- suggest
- explain
- model/version info

### 3.5 Control Console Layer

Provides the human-facing control surface:

- start / stop incremental ingestion
- enable / disable continuous mode
- trigger a one-off cleaning cycle
- trigger training / evaluation / freezing
- inspect job status and reports

### 3.6 Workspace / Project Layer

Every self-hosted deployment should have its own workspace:

- its own data
- its own models
- its own references
- its own gold set
- its own API settings

This is not a SaaS tenant. It is a local project workspace.

## 4. Core Concepts

### 4.1 Workspace

A workspace is the main isolation boundary.

It includes:

- data source config
- reference source config
- model config
- gold versions
- evaluation config
- API config

### 4.2 Model Profile

The system ships with a Canada profile by default.

Users can define their own profiles, such as:

- `base_canada`
- `north_america_custom`
- `user_custom_country`

Profiles determine:

- which parsers to use
- which references to use
- which dictionaries to use
- which training samples to use
- which evaluation set to use

### 4.3 Address Decision

Every address decision must be traceable:

- raw input
- parser outputs
- reference hits
- model scores
- final canonical result
- confidence / reason

## 5. Online API Design

AddressForge must provide at least these APIs:

### 5.1 Parse API

Input raw address, output structured fields.

### 5.2 Normalize API

Input raw address, output normalized text and token results.

### 5.3 Validate API

Input address + reference context, output:

- accept / enrich / review / reject
- confidence
- unit suggestion
- GPS conflict hints

### 5.4 Explain API

Input address and system decision, output a human-readable explanation.

### 5.5 Model Info API

Return model version, reference version, and rule version.

## 6. Offline Training Design

Offline training must be independent from the online API:

- train without network if needed
- replay on local datasets
- freeze gold
- generate evaluation reports
- shadow into the API path

Training flow:

1. export samples
2. build or confirm gold
3. split train / eval / test
4. train models
5. evaluate models
6. run shadow
7. publish via console

## 7. Control Console Design

The console is the control plane for humans.

It must support:

- start / stop incremental ingestion
- enable / disable continuous mode
- run one incremental cleaning cycle
- trigger training / evaluation / freezing
- view reports
- switch model versions

The console must not directly hold the long-running logic. It only creates jobs, shows status, and triggers workers.

## 8. How Others Adapt It to Their Own Countries / Regions

AddressForge does not aim to be a global one-size-fits-all model, but it must be easy to adapt.

It should support:

- replacing parser config
- replacing reference sources
- replacing normalization dictionaries
- replacing gold sets
- replacing model profiles
- replacing API defaults

In other words, the system provides the standard skeleton; others replace the country-specific knowledge.

## 9. Version Boundary

AddressForge’s boundaries are:

- platformization
- open-source self-hosting
- Canada / North America by default
- public APIs
- easy adaptation to other country / region datasets

AddressForge does not aim for:

- global one-shot coverage
- multi-tenant SaaS
- central managed operations

## 10. Summary

The final shape of AddressForge should be:

- a standard open-source address intelligence platform
- a self-hosted Canada / North America default system
- a reference implementation that others can adapt to their own country / region
- a complete system with offline cleaning, online API, learning, and control console

## 11. Ingestion Architecture

The Ingestion Service is the first layer of the platform and must not depend on bundled private address samples in the repository.

It supports two ingestion paths:

1. **API Pull**
   - The third party exposes a private API
   - AddressForge pulls incremental raw records via cursor / batch
   - Suitable for teams that already expose an internal service

2. **Database Direct Import**
   - The third party imports raw records into a database table they control
   - AddressForge connects to that table through configuration
   - Suitable for ETL-oriented or warehouse-oriented workflows

Design requirements:

- Private source data must not be committed to git
- The repository only keeps schemas, sample configs, and code
- Ingestion only acquires raw data; the background pipeline performs cleaning afterward

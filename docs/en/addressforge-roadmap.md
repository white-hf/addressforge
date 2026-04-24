# AddressForge Open Source Platform Roadmap

> English: Implementation roadmap for the open-source, self-hosted address platform.

> 中文：开源自部署地址智能平台的实施路线图。

# Address Library AddressForge Open Source Platform Roadmap

## 1. Roadmap Purpose

This roadmap answers the question:

**How do we evolve the current system into an open-source, self-hosted, trainable platform with public APIs?**

It is not about one more feature. It is about organizing the system into:

- clear entry points
- clear architecture
- clear models
- clear data layers
- clear APIs
- reusable, modifiable, deployable parts

## 2. Roadmap Principles

1. **Stabilize the default Canada / North America model first**
   - the open-source system must be usable out of the box
   - the default experience should already work well for Canada / North America

2. **Standardize first, then open up**
   - standardize internal data layers, training layers, and API layers
   - then expose them for others to adapt

3. **Build the platform skeleton before adding regional adapters**
   - the platform skeleton must be complete first
   - other countries / regions should be handled by configuration, references, dictionaries, and models

4. **Offline first, then online**
   - stabilize cleaning, training, and evaluation first
   - then expose a stable API

5. **Usable first, modifiable second**
   - first let people use it immediately
   - then make it easy to adapt

## 3. Phase 0: Platform Foundation

### Goal

Turn the system from an internal cleaning project into an open-source platform skeleton.

### Deliverables

- default Canada / North America model entry
- workspace / project configuration layer
- API service skeleton
- control console skeleton
- model version registry skeleton
- standardized data layout

### Exit Criteria

- the system clearly separates platform / workspace / model / dataset
- the code structure is friendly to forks and customization

## 4. Phase 1: Default Canada Model Packaging

### Goal

Package the existing Canadian capabilities into the default model bundle.

### Deliverables

- Canada parser profile
- Canada reference profile
- Canada cleaning pipeline profile
- Canada evaluation set
- Canada gold set / human gold snapshot

### Exit Criteria

- a default deployment can process Canada / North America addresses immediately
- model and rule versions are explicitly identifiable

## 5. Phase 2: Public Address APIs

### Goal

Expose address capability as formal APIs.

### Deliverables

- parse API
- normalize API
- validate API
- explain API
- model info API

### Exit Criteria

- users can call address intelligence through HTTP
- API output is structured
- API output is traceable to model and reference versions

## 6. Phase 3: Self-Hosted Training Workflow

### Goal

Allow users to train their own models in their own deployment.

### Deliverables

- sample export
- gold split
- model training
- evaluation
- shadow deployment
- model activation

### Exit Criteria

- users can finish the full train/evaluate/serve loop on local data
- users can choose either the default Canada model or their own model

## 7. Phase 4: Adaptation Hooks for Other Regions

### Goal

Make it easy for others to adapt the system to their own country / region.

### Deliverables

- reference source adapter
- parser profile adapter
- normalization dictionary adapter
- locale / country configuration
- gold set adapter

### Exit Criteria

- users can replace the Canada profile with their own regional knowledge

## 8. Phase 5: Console / Job / Continuous Mode

### Goal

Standardize runtime operation as console-driven continuous execution.

### Deliverables

- job manager
- ingestion control
- continuous mode
- training / freezing jobs
- report jobs

### Exit Criteria

- the console can control system state
- backend workers can execute continuously
- no manual scripts are required for normal operations

## 9. Phase 6: Documentation and Reference Project

### Goal

Turn the system into a reference open-source project that people can learn from and modify.

### Deliverables

- English docs
- Chinese docs
- architecture docs
- API docs
- deployment guide
- training guide

### Exit Criteria

- developers can deploy, train, and use the APIs by following the docs
- documentation and code stay in sync

## 10. Current Status

The current system already has:

- the Canada historical cleaning pipeline
- building / unit layered modeling
- ML / LLM learning pipelines
- the control console and continuous mode

The next step is to **platformize** these capabilities:

- turn them from an internal project into an open-source standard platform

## 11. Ingestion Service Milestone

The next Ingestion Service milestone is:

- support API Pull
- support Database Direct Import
- keep private source configuration out of git
- decouple ingestion from the cleaning pipeline

This means:

- third parties can keep their data in their own systems
- AddressForge only handles ingestion and cleaning
- training, evaluation, and API serving then run against the same private data loop

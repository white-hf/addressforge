# AddressForge Open Source Platform Task Breakdown

> English: Task breakdown for the open-source, self-hosted address platform.

> 中文：开源自部署地址智能平台的任务拆分。

# Address Library AddressForge Open Source Platform Task Breakdown

## 1. Purpose

Break AddressForge into executable, testable, and shippable work items.

## 2. Workstreams

### 2.1 Platform Skeleton

Tasks:

- define the platform / workspace / model / dataset directory structure
- standardize configuration loading
- standardize model version registry
- standardize job state tracking

Exit criteria:

- a forked user can understand the system layout immediately
- internal cleaning logic is not mixed with the external API layer

### 2.2 Default Canada Model

Tasks:

- package the current Canada parser / reference / cleaning config
- freeze the default model version
- freeze the default gold / eval sets

Exit criteria:

- default deployment can be used for Canada / North America out of the box

### 2.3 Online APIs

Tasks:

- parse API
- normalize API
- validate API
- explain API
- model info API

Exit criteria:

- any developer can call the APIs directly
- output is structured, traceable, and versioned

### 2.4 Offline Training

Tasks:

- sample export
- gold generation
- train/eval/test split
- model training
- evaluation and shadow runs

Exit criteria:

- users can complete the train-to-serve loop on local data

### 2.5 Regional Adaptation

Tasks:

- parser config adaptation
- reference config adaptation
- dictionary adaptation
- gold set adaptation

Exit criteria:

- others can adapt the system to their own country / region

### 2.6 Console and Continuous Operations

Tasks:

- start / stop incremental ingestion
- start / stop continuous mode
- trigger one incremental cleaning cycle
- inspect job status and recent results
- trigger training / freezing / reports

Exit criteria:

- operators can use the system without scripts for daily work

## 3. Dependency Order

Recommended order:

1. platform skeleton
2. default Canada model
3. online APIs
4. offline training
5. regional adaptation
6. console and continuous operations

## 4. Definition of Done

Task completion requires:

- runnable code
- synced docs
- traceable outputs
- frozen versions
- rollback capability

## 5. Ingestion Task Split

The Ingestion work is split into two independently implementable paths:

1. **API Pull**
   - configure a private API endpoint
   - pull incremental records by cursor / batch
   - write records into the platform raw table

2. **Database Direct Import**
   - configure a third-party database connection
   - read new records from a source table controlled by the third party
   - write records into the platform raw table

Exit criteria:

- no private third-party data is committed to git
- the third party can choose API or database direct import
- the downstream cleaning pipeline can consume raw table data directly

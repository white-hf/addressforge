# AddressForge Open Source Platform Requirements

> English: Requirements for an open-source, self-hosted address platform focused on Canada / North America.

> 中文：面向加拿大 / 北美地址处理的开源自部署平台需求说明。

> Reading guide: start with the summary here, then read the body.

# Address Library AddressForge Open Source Platform Requirements

## 1. Document Purpose

This document defines the requirements for an **open-source, self-hosted, trainable address system** that can also expose address parsing APIs.

It is not a multi-tenant SaaS and it is not a centrally hosted platform. The intended form is:

- ship with a pretrained Canada / North America address model
- let other developers download and deploy the code
- let others connect their own address data
- let others train their own models
- let others use their own models to clean their own address library and expose their own address parsing API

The system should be “small but complete”:

- offline cleaning
- online parsing
- continuous learning
- versioned management
- human review
- standard API exposure

## 2. Product Positioning

### 2.1 What this system should focus on first

The system should first focus on:

- Canada
- North America
- Halifax / Nova Scotia as the default reference scenario

Why:

- the current system already has a full end-to-end Canadian data chain
- Canada / North America is a realistic and representative address domain
- going deep on one region first is more practical than going global immediately

### 2.2 What this system should not try to do first

The current version is not trying to solve “all countries at once”.

It should not prioritize:

- global all-country coverage
- centrally hosted multi-tenant SaaS
- complex billing
- a unified shared account system

The goal is to provide a **standard, reusable, modifiable open-source address intelligence system** that others can adapt to their own country or region.

## 3. Core Goals

The system must simultaneously support four goals:

1. **Address parsing**
   - split noisy address text into structured fields
   - identify unit, street, building, city, province, postal code, etc.

2. **Address cleaning**
   - normalize format
   - remove noise
   - validate missing pieces
   - detect conflicts

3. **Address production**
   - build canonical building / unit libraries
   - preserve user historical address facts
   - retain evidence and version lineage

4. **Address API**
   - expose parsing, normalization, validation, enrichment, and confidence APIs
   - let other developers call it directly

## 4. Intended Users

This system serves two groups:

### 4.1 System users

They will deploy and use the system directly:

- data engineers
- backend engineers
- platform engineers
- application developers who need address intelligence

### 4.2 System adapters

They will download the code and adapt it to their own country or region:

- connect their own raw address data
- connect their own reference libraries
- train their own models
- expose their own address parsing API

## 5. Functional Requirements

### 5.1 Default Canada Model

The system must ship with:

- Canada-specific address rules
- Canada-specific parsing logic
- Canada building / unit cleaning pipeline
- Canada external reference integration
- Canada historical training samples

### 5.2 Self-Hosting

The system must support:

- local deployment
- private server deployment
- offline operation
- full user ownership of data and models

### 5.3 Data Ingestion

The system must support user-provided data:

- historical batch import
- incremental ingestion
- user-specific reference sources
- user-specific labels and review results

### 5.4 Training and Learning

The system must support:

- model training
- offline evaluation
- shadow prediction
- gold set freezing
- human gold freezing
- active learning
- LLM-assisted labeling

### 5.5 Online APIs

The system must provide APIs for:

- address parsing
- address normalization
- address validation
- unit inference suggestions
- building / unit confidence output
- review recommendation output

### 5.6 Control Console

The system must include a control console for:

- starting / pausing incremental ingestion
- starting / pausing continuous mode
- running one incremental cleaning cycle
- triggering training / evaluation / freezing
- observing job status and recent results

The console controls and observes; it does not perform long-running work itself.

## 6. Architecture Requirements

The system should be split into four long-running subsystems:

1. **Ingestion service**
   - fetch new data
   - maintain cursor state
   - deduplicate idempotently

2. **Cleaning pipeline**
   - normalize / parse / publish / validate / build user facts
   - advance automatically

3. **Learning pipeline**
   - training, evaluation, shadow runs, LLM backflow, gold freezing

4. **Control console**
   - trigger, pause, resume, and observe

These four layers should be separated but coordinated.

## 7. Data Requirements

The system must preserve these layers:

- raw facts
- normalization
- parser candidates
- canonical building / unit
- validation results
- user facts
- external reference evidence
- gold labels
- model run records
- job / control console records

## 8. Quality Requirements

The system should not only measure volume. It must measure:

- building precision / recall
- unit precision / recall
- validation accuracy
- auto-enrich accuracy
- review rate
- GPS conflict rate
- gold coverage

## 9. Design Principles

1. Canada / North America first
2. Open-source self-hosting first
3. Data isolation first
4. Model versioning first
5. Console usability first
6. Separate online serving from offline production
7. ML / LLM as the main decision enhancement layer, not the only truth source

## 10. Success Criteria

The system is successful when:

- Canada / North America address processing is accurate
- the default model is usable out of the box
- others can adapt it to their own country / region
- others can clean their own address libraries
- others can train their own models
- others can expose their own address parsing APIs
- the console, cleaning, training, and evaluation flows all work end to end

## 11. Notes

This is an open-source reference system.
Its value is that it is:

- usable by itself
- modifiable by others
- architecturally complete
- componentized
- able to cover parsing / cleaning / production / API / learning / control console end to end

## 12. Ingestion Service

The Ingestion Service is responsible for bringing third-party private address data into the platform without committing that private data to git.

The platform initially supports two ingestion paths:

1. **API Pull**
   - The third party exposes newly added raw addresses through its own private API
   - AddressForge pulls the data from that API
   - The private data stays in the third party's system

2. **Database Direct Import**
   - The third party imports raw addresses into a database table they control
   - AddressForge connects to that database table through configuration
   - New rows are read and passed into the cleaning pipeline

Constraints:

- Private source files, private database credentials, and private samples do not belong in the repository
- The repository only keeps schemas, sample configs, documentation, and executable code
- The third party can choose either API exposure or database table exposure for ingestion

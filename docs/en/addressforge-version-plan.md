# AddressForge Open Source Platform Version Plan

> English: Version plan for the open-source, self-hosted address platform.

> 中文：开源自部署地址智能平台的版本计划。

# Address Library AddressForge Open Source Platform Version Plan

## 1. Version Goal

Turn the current system into a standard open-source platform:

- usable for Canada / North America by default
- open-source and self-hosted
- able to ingest other people’s data
- able to train other people’s models
- able to serve other people’s APIs

## 2. Version Principles

1. Platformize first, then extend by region
2. Default to Canada model first, then open adaptation
3. Offline training loop before online APIs
4. Usable first, extendable second
5. Reference implementation first, polish later

## 3. Version Map

### AddressForge.0 Platform Skeleton

- platform / workspace / model / dataset structure
- job management
- unified config
- unified version tracking

### AddressForge.1 Default Canada Model

- default Canada parsing model
- default reference profile
- default cleaning and evaluation configuration

### AddressForge.2 Online API Layer

- parse / normalize / validate / explain APIs
- model info API
- structured outputs

### AddressForge.3 Self-Hosted Training Loop

- sample export
- gold split
- training
- evaluation
- shadow deployment
- model activation

### AddressForge.4 Regional Adaptation Hooks

- parser adapter
- reference adapter
- dictionary adapter
- gold adapter

### AddressForge.5 Console and Continuous Operations

- incremental ingestion control
- continuous mode
- training / freezing / report buttons

### AddressForge.6 Documentation and Examples

- English docs
- Chinese docs
- quick start
- API examples
- custom region examples

## 4. Release Policy

- every release must be self-hostable
- every release must be rollbackable
- every release must have docs
- every release must have minimal examples

## 5. What to Use Today

Today the default usable stack is:

- the Canada / North America default model
- the existing cleaning and learning capabilities
- the control console and continuous mode

But the final target is an open-source platform skeleton, not just an internal system.

## 6. Ingestion Version Focus

The first Ingestion version should focus on:

- API Pull
- Database Direct Import
- no private third-party data in git
- feeding raw data into the unified cleaning pipeline

This phase does not try to solve global coverage or complex federation yet; it only aims to make ingestion, cleaning, and training work end to end.

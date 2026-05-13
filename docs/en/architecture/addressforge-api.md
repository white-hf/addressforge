# AddressForge Open Source Platform API

> English: Public API specification for the open-source, self-hosted address platform.

> 中文：开源、自部署地址平台的对外接口说明。

# Address Library AddressForge Open Source Platform API

## 1. Purpose

This document describes the public APIs shipped by AddressForge.  
The goal is not to build a complex SaaS gateway. The goal is to provide self-hosted users with a **stable, replaceable, and extensible** address parsing entry point.

The default version is based on the Canada / North America model.

## 2. Startup

The API is intended to run as a local service.

Launch script:

```bash
cd address-data-cleaning-system
./run_address_platform_api.sh
```

Example environment variables:

- `ADDRESSFORGE_PORT`
- `ADDRESSFORGE_DEFAULT_PROFILE`
- `ADDRESSFORGE_MODEL_VERSION`
- `ADDRESSFORGE_REFERENCE_VERSION`

The main capabilities are:

- `normalize`
- `parse`
- `validate`
- `explain`
- `model info`

## 3. API List

### 3.1 `GET /health`

Returns service health status.

### 3.2 `GET /api/v1/model`

Returns the current platform model, reference, and parser version information.

### 3.3 `POST /api/v1/normalize`

Accepts a raw address and returns normalized text and normalization results.

### 3.4 `POST /api/v1/parse`

Accepts a raw address and returns parser candidates, the best candidate, and structured fields.

### 3.5 `POST /api/v1/validate`

Accepts a raw address or parsed payload and returns:

- `accept`
- `enrich`
- `review`
- `reject`

Together with:

- confidence
- unit inference hints
- building type hints
- reference hit information

### 3.6 `POST /api/v1/explain`

Returns a human-readable explanation for debugging, product display, or secondary confirmation.

## 4. Common Request Fields

Typical request fields are:

- `raw_address_text`
- `city`
- `province`
- `postal_code`
- `country_code`
- `latitude`
- `longitude`
- `profile`
- `parsers`

## 5. Default Model Profile

The default configuration is:

- `base_canada`

This means:

- use Canada address rules
- use the default Canada parser set
- use Canada reference / gold / history as the default basis

## 6. Self-Hosted Usage

This API is for users who download the code and run it on their own infrastructure.

They can:

- use the default Canada model out of the box
- replace parsers
- replace references
- ingest their own data and retrain
- expose their own address parsing API

## 7. Quick Use

If you want a minimal first deployment:

1. start the default API
2. call `normalize`
3. call `parse`
4. call `validate` when needed
5. call `model info` to confirm the active version

## 8. Notes

This is the first API spec for AddressForge.  
Future additions will include:

- request / response examples
- error codes
- batch endpoints
- async task endpoints
- custom model configuration guidance

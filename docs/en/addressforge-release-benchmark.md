# AddressForge Release Benchmark Standard

This document defines the benchmark metrics that AddressForge must produce before promoting a new model, rule set, or cleaning pipeline.

The goal is not just to confirm that the pipeline runs.  
The goal is to answer:

- Is the new version more accurate than the current one?
- Which layer improved?
- Which layer regressed?
- Is the candidate safe to promote?

## 1. Benchmark principles

Every candidate should be evaluated against the same **frozen gold set**.

The benchmark must cover:

- address parsing
- structure recognition
- final decision quality
- runtime behavior

## 2. Core release metrics

AddressForge currently tracks these 8 core release metrics:

1. `decision_f1`
2. `building_type_f1`
3. `unit_number_f1`
4. `unit_recall`
5. `commercial_f1`
6. `accept_rate`
7. `review_rate`
8. `reject_rate`

## 3. What each metric means

### 3.1 `decision_f1`

Measures whether the final decision is correct.

Higher is better.

### 3.2 `building_type_f1`

Measures whether the address is correctly classified as:

- `single_unit`
- `multi_unit`
- `commercial`
- `unknown`

### 3.3 `unit_number_f1`

Measures whether the system correctly extracts, preserves, or enriches unit numbers.

### 3.4 `unit_recall`

Measures how often the system misses units that should have been detected.

This is a critical metric for Canadian address quality.

### 3.5 `commercial_f1`

Measures commercial address recognition quality.

It helps separate:

- single-family homes
- multi-unit apartment buildings
- office towers / malls / commercial properties

### 3.6 `accept_rate`

Measures how often the system directly accepts an address as high-confidence.

### 3.7 `review_rate`

Measures how often the system sends an address to review.

### 3.8 `reject_rate`

Measures how often the system rejects an address.

## 4. Release gate recommendation

Suggested release conditions:

- `decision_f1` must not be lower than active
- `building_type_f1` must not be lower than active
- `unit_number_f1` must not be lower than active
- `unit_recall` must not regress
- `commercial_f1` must not regress
- `review_rate` must not spike unexpectedly
- `reject_rate` must not spike unexpectedly

## 5. Evaluator output

The current evaluator writes these sections into `metrics_json`:

- `decision`
- `building_type`
- `unit_number`
- `commercial`
- `runtime_distribution`
- `release_benchmark`

The `release_benchmark` block is the fixed summary that should be used for release decisions.

## 6. Recommended release workflow

1. freeze gold
2. train the candidate model
3. run evaluation
4. inspect `release_benchmark`
5. run shadow
6. compare active vs candidate
7. promote only if the release gate is satisfied


# AddressForge Model Training and Tuning Guide

> This guide answers three questions:  
> 1. How do I train my own model?  
> 2. How do I tune address parsing accuracy?  
> 3. How do I use the console to drive training, evaluation, freezing, and release?

## 1. Who this guide is for

This guide is for developers who already have the AddressForge minimal loop running.

If you have not done the following yet, start with the quick start guide first:

- initialize the database
- import sample or private address data
- run the API
- generate training samples

## 2. What training is trying to improve

AddressForge training is not “training for training’s sake”.  
The goal is to make your own address system more accurate on your own data.

Typical goals:

- improve parser candidate ranking
- improve unit recognition
- improve building / unit layering
- reduce review rate
- reduce GPS conflict false positives
- reduce wrong auto-enrichment

## 3. Know what you want to tune first

Before training, identify the problem class.

### 3.1 Parsers

If you often miss patterns like:

- `Apt 103`
- `Apart 101`
- `#207`
- `1-133 Main St`

then tune:

- parser candidate ranking
- unit span detection

### 3.2 Validation

If your main issue is:

- accepted addresses are rejected
- missing units are not enriched
- apartments are classified as houses

then tune:

- validation triage
- building clustering
- reference matching

### 3.3 Fusion

If each component looks reasonable but the final decision is unstable, tune:

- confidence fusion
- thresholds
- review routing

## 4. Recommended training order

Do not start with complex models first.

### Step 1: Prepare samples

Export training samples from your cleaning results.

Prioritize these buckets:

- `building_cluster`
- `unit_span`
- `validation`
- `reference_review`

Also keep difficult samples such as:

- multi-unit apartments
- buildings without a unit
- office towers / shopping centers
- GPS conflicts
- parser disagreements

### Step 2: Freeze gold

After human review in the console, freeze the labels into a stable version.

Recommended actions:

- generate the next batch
- review
- complete the batch and freeze

If you already have pure human labels, use a human-only freeze.

### Step 3: Split train / eval / test

Do not rely on a single training score.

You should have:

- train
- eval
- test

Recommended rules:

- avoid leakage across buildings
- avoid leakage across the same user
- do not sample only easy cases

### Step 4: Train a baseline

Train the simplest baseline first.

The goal is not the best score.  
The goal is to confirm:

- features are correct
- label semantics are correct
- evaluation is correct

### Step 5: Run shadow evaluation

Do not replace online behavior directly.

Shadow evaluation should:

- not affect production
- only record predictions
- compare against rules
- show whether the model is actually better

### Step 6: Promote through the console

After evaluation is stable, use the console to switch the default model version.

This should be a console action, not a manual code edit.

## 5. What the console does in training

The console is the control plane, not the trainer itself.

It should handle:

- generating training batches
- freezing gold
- triggering training jobs
- triggering evaluation jobs
- triggering shadow jobs
- showing job status
- switching model versions
- starting / pausing continuous mode

The console should not:

- run long training work inline
- hide all logic inside web requests
- require scripts for normal operation

## 6. What to tune

### 6.1 Parser ranking

Tune:

- parser weights
- confidence thresholds
- unit bonuses / penalties
- postal code bonuses

### 6.2 Validation triage

Tune the boundaries between:

- `accept`
- `enrich`
- `review`
- `reject`

### 6.3 Building / unit

Tune:

- `single_unit`
- `multi_unit`
- `unknown`

### 6.4 Reference fusion

Tune:

- authoritative reference weight
- semi-authoritative reference weight
- weak reference weight
- GPS conflict thresholds

## 7. How to tell training actually improved things

Do not look only at train scores.

Check at least:

- eval accuracy
- precision / recall / F1
- review rate
- auto-enrichment accuracy
- GPS conflict rate
- building split / merge errors
- unit precision / recall

If you have a human gold set, also check:

- human gold precision / recall
- human gold coverage

## 8. A practical loop

If you are training for the first time, use this loop:

1. ingest a small amount of private data
2. run one cleaning pass
3. review a batch of hard samples in the console
4. freeze gold
5. train a baseline
6. run shadow
7. inspect reports
8. adjust thresholds
9. train again
10. switch the default model

## 9. Practical advice

- stabilize the system on small data before scaling
- start with one country / region before expanding
- train a simple baseline first
- version both training and evaluation outputs
- keep an audit trail in the console

## 10. When you are ready to go further

Once the baseline is stable, you can add:

- a stronger reranker
- a better unit span model
- more robust building adjudication
- stronger confidence fusion
- LLM-assisted labeling and review reduction

## 11. Conclusion

The key is not just “training a model”.

You want:

- the console to drive the flow
- gold to protect label quality
- eval and shadow to validate behavior
- versions to make rollback possible

AddressForge training should be a continuous loop, not a one-off script.

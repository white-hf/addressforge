# AddressForge Review Queue Re-enqueues the Same Address Under Different Task Types Bug

## Issue Type
- Functional defect
- Data processing logic error
- Human review efficiency loss

## Summary
The current system does not deduplicate review candidates at the “same address already reviewed” level. Instead, it deduplicates by:

- `workspace_name`
- `source_name`
- `source_id`
- `task_type`

As a result, the same address can re-enter the review queue if a later workflow assigns it a different `task_type`, even when that address has already been reviewed by a human.

## Confirmed Symptoms
In the `default` workspace, both the queue and the gold set already contain repeated address samples:

- the same `source_id` appears twice in `active_learning_queue`
- the same `source_id` also appears twice in `gold_label`

Repeated examples include:

- `68`
- `213`
- `216`
- `222`
- `223`
- `335`
- `425`
- `583`
- `584`
- `585`
- `600`
- `675`
- `676`
- `687`
- `746`

## Direct Mechanism of Repetition
These are not exact duplicate task rows. They are typically the same address re-entering the queue under a new task type:

- first as `review`
- later again as `commercial` / `single_unit` / `building_type`

For example:

- `213`: `review` -> `commercial`
- `287`: `review` -> `single_unit`
- `670`: `review` -> `single_unit`

So the system is currently treating “same address, new task_type” as a brand-new human review task.

## Root Cause Analysis
### 1. The queue uniqueness key includes `task_type`
`active_learning_queue` uses this uniqueness rule:

- `(workspace_name, source_name, source_id, task_type)`

See [addressforge_schema.sql](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/sql/addressforge_schema.sql:158)

This means:

- same address + same task type => update existing row
- same address + different task type => insert a new row

### 2. Gold labels are also stored separately by `task_type`
`gold_label` uses the same pattern:

- `(workspace_name, source_name, source_id, task_type)`

See [addressforge_schema.sql](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/sql/addressforge_schema.sql:111)

So repeated review under a changed task type creates both:

- duplicate queue records
- duplicate human gold rows

### 3. Queue-seeding logic does not exclude already reviewed source IDs
The main queue-seeding functions:

- `seed_active_learning_queue(...)`
- `seed_active_learning_from_errors(...)`
- `seed_unit_commercial_review_queue(...)`

all attempt to enqueue rows directly without first excluding source IDs that already have:

- accepted human gold
- prior queue history

Relevant code:
- [gold.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/learning/gold.py:310)
- [gold.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/learning/gold.py:421)
- [gold.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/learning/gold.py:494)

## Impact on Operations and Model Quality
### Human review impact
- the same address gets reviewed repeatedly
- reviewers may assume the sample is new
- human review time is wasted on reconfirming the same address

### Gold data impact
- the same address can accumulate multiple human gold rows under different task types
- gold size appears to grow, but true new-address coverage grows much less

### Training and evaluation impact
- training/evaluation can overweight the same address multiple times
- sample independence becomes weaker
- apparent improvements can be diluted or distorted by repeated samples

## This is a system logic defect, not an operations mistake
Operations users are not doing anything wrong.  
The repetition happens because the system incorrectly treats:

- “the same address with a new task type”

as:

- “a new review sample requiring fresh human review”

## Required Fix Outcomes
### 1. Queue generation must exclude already reviewed samples at the `source_id` level
By default, once a `source_id` already has accepted human gold, it should not be auto-enqueued again.

### 2. Queue generation must exclude any existing queue history for the same address
Changing `task_type` must not be enough to insert the same address into the review queue again.

### 3. `freeze gold`, training, and evaluation should deduplicate by `source_id` by default
Even if historical duplicate gold rows already exist, they should not continue to be treated as fully independent training samples.

### 4. Re-review of the same address must be explicit, not implicit
If the product genuinely needs to re-review an address later, that should happen through an explicit reopen / forced-review mechanism, not by silently re-enqueuing it during normal sampling.

## Minimum Acceptance Criteria
1. Re-running:
   - `seed_active_learning_queue`
   - `seed_active_learning_from_errors`
   - `seed_unit_commercial_review_queue`
   against an already reviewed batch must not insert the same addresses again
2. A new queue round must not include the same address if that address already has accepted human review
3. `freeze gold` sample counts must reflect deduplicated `source_id` coverage, not inflated counts caused by repeated task types

## Current Conclusion
The root cause of “most of these addresses were already reviewed last time” is:

**the system decides uniqueness using `(source_id + task_type)` instead of deciding whether the same address has already completed human review.**

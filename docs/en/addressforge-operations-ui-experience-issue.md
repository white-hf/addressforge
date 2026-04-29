# AddressForge Operations UI Experience Issue

## Background
The current AddressForge operations UI is primarily organized around technical modules or system capabilities, for example:

- `Batch Management`
- `Review`
- `Dashboard`
- `Reports`
- various `job / train / evaluation / release gate` actions

This structure is understandable for developers and system maintainers because it reflects internal module boundaries. However, operations users are not trying to “enter a module and use a feature.” Their real goal is to **complete a business workflow**, such as:

- generate review tasks
- complete manual review
- freeze gold
- trigger training
- trigger evaluation
- check shadow / gate results
- decide whether to move into the next iteration

Operations users care about “what should I do next,” not “which module contains this function.”

## Core Experience Problems

### 1. Users must understand the system workflow by themselves
The product does not present the full business path as a continuous sequence of steps. Users must already know:

- where to freeze gold after review is complete
- where to trigger training after freezing
- where to run evaluation after training
- whether shadow runs automatically after evaluation
- where to check the gate result

This forces users to build the workflow mentally first, then navigate across pages to execute it.

### 2. The UI behaves more like a feature console than a workflow workspace
The current interface behaves more like:

- a control panel split by feature area
- a module-oriented operations backend

rather than a workflow workspace for operations execution. As a result, users are presented with:

- feature entry points
- report entry points
- job entry points
- module status entry points

instead of:

- “which step am I on now?”
- “where is the current process blocked?”
- “what should I click next?”

### 3. Workflow actions are scattered across multiple pages
Actions from the same business flow are split across different areas:

- review lives in `Review`
- gold freeze lives in `Batch`
- training / evaluation live in `Dashboard`
- gate results live in `Reports`

This means users must jump across pages to complete one business objective, and must rebuild context at each transition.

### 4. Users must remember dependency relationships by themselves
Technically the system supports:

- freeze gold
- retrain
- re-evaluate
- shadow
- gate check

But these dependencies are not directly expressed in business language. Users must know which steps are prerequisites, which steps auto-follow, and which pages are only for viewing results.

That means:

- users are not “executing a workflow”
- they are “operating system modules”

### 5. The cognitive load is too high for non-technical operations users
If the user is not a developer, but instead a reviewer, operator, or project executor, the current interface creates clear cognitive overhead:

- they must understand system terminology
- they must understand module boundaries
- they must understand the relationship between jobs and workflows
- they must decide for themselves whether a stage is already complete

This lowers execution efficiency and increases the risk of mistakes or skipped steps.

## Root Issue
The current information architecture mainly answers:

- “What functional modules does the system have?”

But what operations users really need is:

- “What business workflow am I currently trying to complete?”
- “Which step am I on now?”
- “What should I do next?”
- “Which steps already happened automatically, and which still require manual action?”

So the core issue is not that a single button is missing. It is that:

**the product is organized by system capability, not by operations workflow execution.**

## Direct Impact
This creates direct experience problems:

- users must think instead of following a guided flow
- users must switch across modules to finish one task
- users must remember workflow dependencies by themselves
- users cannot quickly tell whether the current stage is complete
- the system is functionally rich, but execution is not smooth

## Summary
The current operations UI behaves more like a modular feature backend than a workflow-oriented operations workbench. To complete one business chain, users must understand the process themselves, find the relevant functions across pages, and decide the next step on their own, instead of being naturally guided through the workflow.

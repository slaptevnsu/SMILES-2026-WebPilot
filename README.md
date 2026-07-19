# SMILES 2026 WebPilot

This repository contains a prototype implementation of **WebPilot**, a browser-grounded web coding agent for the SMILES 2026 summer school project.

WebPilot is built around the idea that frontend code generation should not be a one-shot process. Instead, the agent should generate or modify code, run the web application in a real browser, collect execution feedback, diagnose failures, and iteratively repair the code.

## Current Status

The current prototype supports a browser-grounded diagnostic repair loop for small React/Vite applications.

Implemented features:

- typed task and result schemas with Pydantic;
- CLI runner for single-task execution;
- Playwright-based browser execution;
- browser artifact collection:
  - screenshots;
  - DOM snapshots;
  - console logs;
  - page errors;
  - interaction test results;
  - browser run summaries;
- deterministic repair baseline;
- LLM-based repair variants through an OpenAI-compatible API;
- role-based LLM agents:
  - planner;
  - browser-grounded reflector;
  - repairer;
- iterative repair loop with `max_iterations`;
- evaluation runner over multiple tasks and agent variants;
- machine-readable and human-readable evaluation artifacts.

## Core Loop

The implemented WebPilot loop is:

```text
task
  -> initial browser execution
  -> evidence collection
  -> planning
  -> diagnosis / reflection
  -> code repair
  -> browser re-execution
  -> verification
```

For repair variants, this loop can run for multiple iterations:

```text
initial_browser/
repair_iteration_01/
  llm_plan/
  llm_reflection/
  llm_repair/
  browser_after/
repair_iteration_02/
  ...
summary.json
```

The loop stops early when the repaired application passes browser verification.

## Architecture

```text
WebPilotRunner
  |
  |-- BrowserExecutor
  |     runs the frontend app in Chromium via Playwright
  |     collects screenshots, DOM snapshots, console logs, page errors, and test results
  |
  |-- InteractionTester
  |     checks task-specific browser behavior
  |
  |-- DeterministicRepairer
  |     applies rule-based repairs for known demo failures
  |
  |-- LLMPlanner
  |     produces a concise repair plan
  |
  |-- LLMReflector
  |     diagnoses failures from browser evidence and source code
  |
  |-- LLMRepairer
        produces corrected frontend code
```

The current MVP uses a lightweight custom Python orchestrator rather than a heavy agent framework. This keeps the execution loop transparent and easy to debug. The design is modular: the planner, browser executor, reflector, repairer, and evaluator can later be migrated into graph nodes if the workflow becomes more complex.

## Agent Variants

The current prototype supports four variants.

### `base`

Runs the application in a browser and collects evidence, but does not attempt repair.

This is expected to fail on diagnostic repair tasks.

### `deterministic-browser-feedback`

Uses browser/test failure evidence and applies a small rule-based repair.

This is not the main research agent. It is a sanity baseline that validates the execution, testing, artifact logging, and repair pipeline.

### `llm-code-only`

Uses an LLM planner and LLM repairer.

The repair prompt includes:

- task instruction;
- current `src/App.jsx`;
- LLM-generated repair plan.

It does not pass browser evidence into the repair prompt.

### `llm-browser-feedback`

Uses the full browser-grounded LLM repair pipeline.

The repair prompt includes:

- task instruction;
- current `src/App.jsx`;
- LLM-generated repair plan;
- browser-grounded diagnosis;
- browser/test evidence.

This is the main WebPilot-style variant in the current prototype.

## Repository Structure

```text
SMILES-2026-WebPilot/
  README.md
  pyproject.toml
  .gitignore
  .env.example

  tasks/
    sample_diagnostic_repair.json
    sample_input_echo_repair.json

  examples/
    buggy_counter/
    buggy_input_echo/

  webpilot/
    __init__.py
    cli.py
    runner.py
    evaluator.py
    schemas.py
    browser.py
    tester.py
    repairer.py
    llm_client.py
    agents/
      __init__.py
      planner.py
      reflector.py
      repairer.py

  scripts/
    smoke_llm_client.py

  outputs/
    .gitkeep
```

## Setup

The project requires Python 3.10+ and Node.js/npm.

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install the Python package in editable mode:

```bash
pip install -e .
```

Install Playwright browser dependencies:

```bash
python -m playwright install chromium
```

Check that Node.js and npm are available:

```bash
node -v
npm -v
```

The demo React/Vite applications install their own npm dependencies during browser execution.

## LLM Configuration

LLM variants use an OpenAI-compatible API client.

Create a local `.env` file or export the variables manually:

```bash
export WEBPILOT_LLM_BASE_URL="https://openrouter.ai/api/v1"
export WEBPILOT_LLM_API_KEY="replace_with_your_key"
export WEBPILOT_LLM_MODEL="openai/gpt-4.1-mini"
```

The `.env` file is ignored by git.

A minimal LLM smoke test is available:

```bash
python scripts/smoke_llm_client.py
```

The non-LLM variants do not require these environment variables.

## Running One Task

Run the base variant:

```bash
python -m webpilot.cli run \
  --task tasks/sample_diagnostic_repair.json \
  --variant base
```

Run the deterministic browser-feedback baseline:

```bash
python -m webpilot.cli run \
  --task tasks/sample_diagnostic_repair.json \
  --variant deterministic-browser-feedback
```

Run the LLM code-only variant:

```bash
python -m webpilot.cli run \
  --task tasks/sample_diagnostic_repair.json \
  --variant llm-code-only
```

Run the full browser-grounded LLM variant:

```bash
python -m webpilot.cli run \
  --task tasks/sample_diagnostic_repair.json \
  --variant llm-browser-feedback
```

Run with more than one repair iteration:

```bash
python -m webpilot.cli run \
  --task tasks/sample_diagnostic_repair.json \
  --variant llm-browser-feedback \
  --max-iterations 2
```

## Running Evaluation

Run a small non-LLM evaluation:

```bash
python -m webpilot.cli evaluate --tasks \
  tasks/sample_diagnostic_repair.json \
  tasks/sample_input_echo_repair.json \
  --variants base deterministic-browser-feedback
```

Run the full evaluation:

```bash
python -m webpilot.cli evaluate --tasks \
  tasks/sample_diagnostic_repair.json \
  tasks/sample_input_echo_repair.json \
  --variants base deterministic-browser-feedback llm-code-only llm-browser-feedback
```

For the current two diagnostic repair tasks, the expected high-level result is:

```text
base                           fails on both diagnostic tasks
deterministic-browser-feedback repairs both tasks
llm-code-only                  repairs both tasks
llm-browser-feedback           repairs both tasks
```

## Output Artifacts

Single-task runs create directories under:

```text
outputs/<task_id>/<timestamp>/
```

Typical artifacts include:

```text
task.json
plan.json
summary.json

initial_browser/
  npm_install.log
  dev_server.log
  screenshot.png
  dom_snapshot.html
  console_logs.json
  page_errors.json
  test_results.json
  browser_result.json

repair_iteration_01/
  llm_plan/
    llm_plan_prompt.txt
    llm_plan_response.txt

  llm_reflection/
    llm_reflection_prompt.txt
    llm_reflection_response.txt

  llm_repair/
    llm_prompt.txt
    llm_response.txt
    repair_plan.json
    patch.diff

  browser_after/
    npm_install.log
    dev_server.log
    screenshot.png
    dom_snapshot.html
    console_logs.json
    page_errors.json
    test_results.json
    browser_result.json
```

Evaluation runs create directories under:

```text
outputs/evaluations/<evaluation_id>/
```

with:

```text
evaluation_summary.json
evaluation_records.jsonl
evaluation_report.md
```

## Demo Tasks

The current prototype includes two WebCompass-style diagnostic repair tasks.

### `sample_diagnostic_repair`

A React counter app renders correctly, but clicking the increment button does not increase the displayed count.

The browser interaction test clicks the button and checks whether the count increased.

### `sample_input_echo_repair`

A React input echo app renders correctly, but typing into the input does not update the preview text.

The browser interaction test fills the input and checks whether the preview reflects the typed text.

## Evaluation Metrics

The prototype currently tracks:

- browser execution status;
- interaction test status;
- number of passed checks;
- number of failed checks;
- repair status;
- initial browser status;
- final browser status.

These metrics are stored in structured JSON and summarized in Markdown evaluation reports.

## Why LangGraph Is Not Used in the Current MVP

LangGraph was considered for orchestration, but the current MVP uses a lightweight Python runner because the implemented workflow is still mostly linear:

```text
browser execution -> planning -> reflection -> repair -> browser verification
```

Avoiding a graph framework keeps the prototype easier to inspect, debug, and explain. The architecture remains compatible with LangGraph: the current modules can later become graph nodes if the agent workflow adds more branches, checkpointing, human-in-the-loop steps, test synthesis, or visual reflection.

## Limitations

This is a minimal research prototype, not a full production web coding agent.

Current limitations:

- tasks are small React/Vite diagnostic repair examples;
- the interaction tester is task-specific;
- LLM repair currently targets `src/App.jsx`;
- screenshot artifacts are collected, but visual reflection is not yet implemented as a vision-language model step;
- there is no full WebCompass benchmark integration yet;
- deterministic repair is only a sanity baseline, not the main agent.

## Project Framing

The current implementation demonstrates the core WebPilot idea:

> A web coding agent should run the application in a real browser, collect grounded execution evidence, and use this feedback to drive iterative repair.

The main implemented comparison is between no-repair execution, deterministic browser-feedback repair, LLM repair without browser feedback, and LLM repair with browser-grounded feedback.

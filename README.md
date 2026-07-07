# SMILES 2026 WebPilot

This repository contains the SMILES 2026 project implementation for WebPilot, a browser-grounded multimodal web coding agent.

The goal of the project is to build an agent that goes beyond one-shot frontend code generation. Instead of only writing code once, the agent should run the generated or modified web application in a real browser, collect execution feedback, inspect failures, and iteratively repair the code.

## Project Idea

WebPilot follows an iterative loop:

```text
task -> plan -> code/patch -> browser execution -> evidence collection -> diagnosis -> repair
```

For each web coding task, the agent should be able to:

- generate or edit frontend code;
- run the application in a real browser;
- collect browser-grounded feedback:
  - build/runtime logs;
  - console logs;
  - DOM snapshots;
  - screenshots;
  - interaction test results;
- diagnose execution, interaction, or visual failures;
- revise the code based on collected evidence.

## Pre-defense Scope

For the pre-defense, we focus on a minimal runnable prototype rather than a full autonomous agent.

The planned prototype should include:

- a script that runs one or two demo web coding tasks end-to-end;
- Playwright-based browser execution;
- artifact logging for screenshots, DOM snapshots, console logs, and test results;
- one or two simple demo tasks;
- a clear evaluation plan comparing different feedback signals and agent variants.

## Planned Agent Variants

We plan to compare the following variants:

1. **Base Agent**  
   One-shot code generation or editing without browser feedback.

2. **Browser-Feedback Agent**  
   Uses browser evidence such as logs, DOM snapshots, screenshots, and runtime errors.

3. **Test-Synthesis Agent**  
   Adds generated Playwright tests for interaction checking.

4. **Visual-Reflection Agent**  
   Adds screenshot-based visual critique for layout and design issues.

## Evaluation Plan

We plan to evaluate the system using the following metric groups:

- **Executability**: whether the project installs, builds, launches, and renders without fatal errors.
- **Interaction correctness**: whether core user flows pass Playwright or DOM-based checks.
- **Visual quality**: whether the rendered page is visually coherent and aligned with the task instruction or reference screenshot.
- **Patch quality**: whether the generated patch is localized, does not introduce regressions, and addresses the root cause.

## Initial Tech Stack

Planned stack for the first prototype:

- **LangGraph** — agent workflow and iterative repair loop;
- **Playwright** — browser automation, screenshots, DOM inspection, console logs, and interaction tests;
- **Pydantic** — typed task/result/artifact schemas;
- **React/Vite** — simple frontend demo applications;
- **JSON + filesystem logging** — structured artifact storage.

## Repository Structure

Planned structure:

```text
SMILES-2026-WebPilot/
  README.md
  .gitignore
  tasks/
    repair_counter_001.json
  examples/
    broken_counter/
  webpilot/
    __init__.py
    runner.py
    browser.py
    schemas.py
    logger.py
    evaluator.py
  scripts/
    run_task.py
  outputs/
    .gitkeep
  docs/
    roadmap.md
```

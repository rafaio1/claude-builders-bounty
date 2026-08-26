# Senior Development Pipeline

Orchestrates a multi-agent development workflow enforcing SOLID, Object Calisthenics, and rigorous validation to prevent hallucinations.

## When to Use
Use this skill when implementing code changes that require senior-level quality, including:
- Bounty fixes requiring production-grade code
- Refactoring tasks with SOLID/Calisthenics requirements
- Any implementation where hallucination risk must be minimized

## Pipeline Stages (Sub-Agents)

### 1. Architect Agent
**Role:** Map dependencies, analyze existing code, design solution
**Validation Gate:** Must produce structured JSON with `files_to_modify` list
**Anti-Hallucination:** Cross-references actual file map before designing

### 2. Senior Developer Agent
**Role:** Implement solution following Architect's design
**Validation Gate:** Code must reference only files from Architect's approved list
**Anti-Hallucination:** Cannot invent new files or functions not in codebase map

### 3. Code Reviewer Agent
**Role:** Review for SOLID compliance, edge cases, security
**Validation Gate:** Must return explicit `{"approved": true/false}` JSON
**Anti-Hallucination:** Reviews actual diff, not imagined code

### 4. QA Engineer Agent
**Role:** Generate unit, integration, and functional tests
**Validation Gate:** Tests must reference actual function signatures from codebase
**Anti-Hallucination:** Test imports validated against real module structure

### 5. Product Specialist Agent
**Role:** Validate acceptance criteria and UX impact
**Validation Gate:** Must return explicit `{"accepted": true/false}` JSON
**Anti-Hallucination:** Validates against original issue text, not assumptions

### 6. Release Manager Agent
**Role:** Semantic commit message in project language (pt-br/en/ja)
**Validation Gate:** Commit type (feat/fix) derived from issue keywords
**Anti-Hallucination:** Message references actual issue number and scope

## Orchestration Rules
- Each stage MUST validate the previous stage's output before proceeding
- If any validation gate fails, pipeline halts and reports specific failure reason
- All agent calls use GhostCLI API with structured JSON responses enforced
- Language detection runs once at start; all comments/docs follow detected language
- File mapping is authoritative — agents cannot reference unmapped files

## Integration with Bounty Engine
Replace direct GhostCLI fix generation in `bounty_engine.py` with:
```python
from scripts.senior_dev_pipeline import run_pipeline
result = run_pipeline(work_dir, issue_body, repo_name)
if result and result["status"] == "success":
    # Proceed with commit/PR using result["commit_msg"] and result["pr_body"]
else:
    log(f"Pipeline rejected: {result}")
```

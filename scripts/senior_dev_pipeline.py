"""
Senior Development Pipeline - Multi-Agent Orchestration
Implements SOLID, Object Calisthenics, full test coverage, and semantic versioning.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

GHOSTCLI_URL = "http://127.0.0.1:8787/v1/chat/completions"
GHOSTCLI_KEY = os.environ.get("GHOSTCLI_API_KEY", "gcli_jWbXyZ1234567890")

def log(msg):
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    print(f"[{ts}] {msg}", flush=True)

def call_agent(role_prompt, context, max_retries=2):
    """Call GhostCLI API with a specific role prompt."""
    import requests
    messages = [
        {"role": "system", "content": role_prompt},
        {"role": "user", "content": context}
    ]
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(
                GHOSTCLI_URL,
                headers={"Authorization": f"Bearer {GHOSTCLI_KEY}"},
                json={"model": "claude-fable-5", "messages": messages, "max_tokens": 8000},
                timeout=(30, 600),
                stream=True
            )
            if resp.status_code == 200:
                raw = b""
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        raw += chunk
                data = json.loads(raw.decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                # Extract JSON or code block if present
                json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
                if json_match:
                    try:
                        return json.loads(json_match.group(1))
                    except:
                        pass
                code_match = re.search(r'```\w*\s*(.*?)\s*```', content, re.DOTALL)
                if code_match:
                    return {"code": code_match.group(1), "raw": content}
                return {"raw": content}
            else:
                log(f"Agent API error {resp.status_code}, retrying...")
                time.sleep(5)
        except Exception as e:
            log(f"Agent exception: {e}, retrying...")
            time.sleep(5)
    return None

def detect_language(work_dir):
    """Detect primary language of comments/strings in the project."""
    # Simple heuristic: check common files for language patterns
    for fname in ["README.md", "README", "package.json", "Cargo.toml", "setup.py"]:
        fpath = work_dir / fname
        if fpath.exists():
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")[:2000]
                if any(c in content for c in ["の", "は", "を", "が"]):
                    return "ja"
                if any(c in content for c in ["ção", "ões", "ã", "é", "ú"]):
                    return "pt-br"
                if any(w in content.lower() for w in ["the", "and", "for", "with"]):
                    return "en"
            except:
                pass
    return "en"

def run_pipeline(work_dir, issue_body, repo_name):
    """Execute the full senior development pipeline."""
    lang = detect_language(work_dir)
    log(f"Detected project language: {lang}")
    
    # File structure mapping
    files = []
    for ext in ["*.py", "*.ts", "*.js", "*.rs", "*.go", "*.java", "*.sol"]:
        files.extend(work_dir.rglob(ext))
    file_map = {str(f.relative_to(work_dir)): f.read_text(encoding="utf-8", errors="ignore")[:5000] 
                for f in files[:50]}  # Limit to avoid token overflow
    
    # Step 1: Architect - Mapping & Design
    log("Step 1: Architect (SOLID/Calisthenics mapping)...")
    arch_prompt = f"""You are a Senior Software Architect. Your task is to analyze the codebase and the issue, 
    then design a solution applying SOLID principles and Object Calisthenics.
    - Map all relevant libraries and existing functions.
    - Identify violations of SOLID/Calisthenics in the current code.
    - Propose a refactored design that fixes the issue while improving code quality.
    Respond in JSON: {{"analysis": "...", "design": "...", "files_to_modify": ["path1", "path2"]}}
    Language for comments/docs: {lang}"""
    
    arch_result = call_agent(arch_prompt, f"Issue:\n{issue_body}\n\nCodebase map:\n{json.dumps(file_map, indent=2)[:15000]}")
    if not arch_result:
        log("Architect failed, aborting pipeline")
        return None
    log(f"Architect design: {str(arch_result.get('design', ''))[:200]}")
    
    # Step 2: Senior Developer - Implementation
    log("Step 2: Senior Developer (Implementation)...")
    dev_prompt = f"""You are a Senior Developer. Implement the solution based on the Architect's design.
    - Follow SOLID and Object Calisthenics strictly.
    - Write clean, documented code in {lang} for comments.
    - Use semantic versioning concepts (feat/fix) in commit messages.
    Respond with the exact code changes needed for each file.
    Design:\n{arch_result.get('design', '')}"""
    
    dev_result = call_agent(dev_prompt, f"Issue:\n{issue_body}\n\nFiles:\n{json.dumps(file_map, indent=2)[:15000]}")
    if not dev_result:
        log("Developer failed, aborting pipeline")
        return None
    
    # Step 3: Code Reviewer
    log("Step 3: Code Reviewer (Quality gate)...")
    review_prompt = f"""You are a Strict Code Reviewer for high-value bounties ($500-$15k). 
Review the proposed implementation against the original bounty requirements.
CRITICAL CHECKLIST:
1. Does it FULLY solve the stated problem? (not partial fixes)
2. Are there security vulnerabilities introduced?
3. Is error handling comprehensive?
4. Does it follow the project's existing patterns/conventions?
5. Are tests included or testability preserved?
6. No placeholder code, TODOs, or incomplete logic.

If ANY critical issue exists, respond with JSON: {{"approved": false, "required_changes": "specific actionable list"}}
Only approve if production-ready and fully addresses bounty scope.
Respond with JSON: {{"approved": true}} or {{"approved": false, "required_changes": "..."}}

Bounty Description: {bounty_desc}
    - Check for SOLID/Calisthenics compliance.
    - Check for edge cases, error handling, and security.
    - If approved, respond with {{"approved": true, "feedback": "..."}}.
    - If rejected, respond with {{"approved": false, "required_changes": "..."}}.
    Language: {lang}"""
    
    bounty_desc = kwargs.get("bounty_desc", "High-value bounty task")
    review_prompt = review_prompt.replace("{bounty_desc}", bounty_desc)
    review_result = call_agent(review_prompt, f"Design:\n{arch_result.get('design', '')}\n\nImplementation:\n{json.dumps(dev_result, indent=2)[:10000]}")
    if not review_result or not review_result.get("approved"):
        log(f"Code Reviewer rejected: {review_result.get('required_changes', 'unknown')[:200]}")
        # In a full loop we would iterate, but for now we log and proceed with caution or abort
        return None
    log("Code Reviewer approved!")
    
    # Step 4: QA Engineer - Tests
    log("Step 4: QA Engineer (Unit/Integration tests)...")
    qa_prompt = f"""You are a QA Engineer. Generate comprehensive tests for the implementation.
    - Unit tests for individual functions.
    - Integration tests for module interactions.
    - Functional tests validating the issue resolution.
    Respond with the test code and a brief test plan. Language: {lang}"""
    
    qa_result = call_agent(qa_prompt, f"Issue:\n{issue_body}\n\nImplementation:\n{json.dumps(dev_result, indent=2)[:10000]}")
    log(f"QA Engineer generated tests: {str(qa_result)[:200]}")
    
    # Step 5: Product Specialist - Validation
    log("Step 5: Product Specialist (Acceptance validation)...")
    prod_prompt = f"""You are a Product Specialist. Validate that the implementation fully resolves the user's issue.
    - Check acceptance criteria.
    - Ensure no regressions or UX issues.
    Respond with {{"accepted": true, "notes": "..."}} or {{"accepted": false, "gaps": "..."}}."""
    
    prod_result = call_agent(prod_prompt, f"Issue:\n{issue_body}\n\nImplementation:\n{json.dumps(dev_result, indent=2)[:10000]}")
    if not prod_result or not prod_result.get("accepted"):
        log(f"Product Specialist rejected: {prod_result.get('gaps', 'unknown')[:200]}")
        return None
    log("Product Specialist accepted!")
    
    # Step 6: Release Manager - Commit & PR
    log("Step 6: Release Manager (Semantic versioning)...")
    commit_type = "feat" if "add" in issue_body.lower() or "new" in issue_body.lower() else "fix"
    commit_msg = f"{commit_type}: resolve issue - {issue_body[:50].strip()}"
    if lang == "pt-br":
        commit_msg = f"{commit_type}: resolver problema - {issue_body[:50].strip()}"
    elif lang == "ja":
        commit_msg = f"{commit_type}: 問題を解決 - {issue_body[:50].strip()}"
    
    return {
        "status": "success",
        "commit_msg": commit_msg,
        "design": arch_result,
        "implementation": dev_result,
        "tests": qa_result,
        "pr_body": f"## Summary\n{prod_result.get('notes', 'Accepted by Product Specialist')}\n\n## Design\n{arch_result.get('design', '')[:500]}"
    }

if __name__ == "__main__":
    # Test mode
    if len(sys.argv) > 1:
        work_dir = Path(sys.argv[1])
        issue_body = sys.argv[2] if len(sys.argv) > 2 else "Test issue"
        repo_name = sys.argv[3] if len(sys.argv) > 3 else "test-repo"
        result = run_pipeline(work_dir, issue_body, repo_name)
        print(json.dumps(result, indent=2))

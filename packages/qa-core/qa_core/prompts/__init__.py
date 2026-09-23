from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    version: str
    system_instruction: str
    user_template: str

    def format(self, **kwargs: Any) -> str:
        return self.user_template.format(**kwargs)


REQUIREMENT_ANALYSIS_PROMPT = PromptTemplate(
    prompt_id="requirement_analysis",
    version="v1.0",
    system_instruction="You are an expert QA Software Architect. Analyze software requirements for testability, risks, ambiguities, and coverage dimensions. Respond with valid JSON strictly matching the schema.",
    user_template="""Analyze the following software requirement for testability and quality risks:

Title: {title}
Description: {description}
Acceptance Criteria:
{acceptance_criteria}

Project Context:
{project_context}

Provide a structured JSON output with fields:
- summary: string (high-level testing summary)
- risks: list of strings (potential testing or technical risks)
- ambiguities: list of strings (unclear or missing requirements)
- suggested_test_dimensions: list of strings (e.g. FUNCTIONAL, BOUNDARY, SECURITY, PERFORMANCE, NEGATIVE)
""",
)

TEST_DESIGN_PROMPT = PromptTemplate(
    prompt_id="test_design",
    version="v1.0",
    system_instruction="You are an expert QA Design Lead. Generate structured test design ideas covering functional, boundary, negative, API, UI, and analytics dimensions. Respond with valid JSON strictly matching the schema.",
    user_template="""Generate structured test design proposals for the following requirement:

Requirement: {title}
Description: {description}
Acceptance Criteria:
{acceptance_criteria}
Existing Test Designs:
{existing_designs}

Provide a structured JSON output with fields:
- suggestions: list of objects, each containing:
  - title: string
  - category: one of ["FUNCTIONAL", "BOUNDARY", "NEGATIVE", "API", "UI", "ANALYTICS"]
  - description: string
  - risk: string (e.g., "High", "Medium", "Low")
""",
)

TEST_CASE_GENERATION_PROMPT = PromptTemplate(
    prompt_id="test_case_generation",
    version="v1.0",
    system_instruction="You are an expert QA Test Engineer. Generate comprehensive manual/automation-ready test cases based on requirement and test design. Respond with valid JSON strictly matching the schema.",
    user_template="""Generate comprehensive test cases for the following test design:

Requirement: {requirement_title}
Test Design: {design_title} ({category})
Description: {design_description}
Acceptance Criteria:
{acceptance_criteria}

Provide a structured JSON output with fields:
- test_cases: list of objects, each containing:
  - title: string
  - preconditions: string
  - steps: list of strings
  - expected_result: string
  - priority: one of ["P0", "P1", "P2", "P3"]
  - tags: list of strings
""",
)

TEST_AUTHOR_PROMPT = PromptTemplate(
    prompt_id="test_author",
    version="v1.0",
    system_instruction="You are a Senior Automation Engineer proficient in Playwright and Pytest. Generate clean, robust, deterministic pytest test scripts utilizing grounded workspace page objects and fixtures. Never invent nonexistent page methods or fixtures. Respond with valid JSON strictly matching the schema.",
    user_template="""Generate a robust pytest Playwright automation test script:

Test Case: {title}
Preconditions: {preconditions}
Steps:
{steps}
Expected Result: {expected_result}

Grounded Workspace Knowledge:
- Available Pages: {available_pages}
- Available Locators: {available_locators}
- Available Flows/Fixtures: {available_flows}

Provide a structured JSON output with fields:
- suggested_file_path: string (e.g. "tests/test_*.py")
- generated_code: string (valid python code with pytest and playwright.sync_api)
- explanation: string
""",
)

FAILURE_DIAGNOSIS_PROMPT = PromptTemplate(
    prompt_id="failure_diagnosis",
    version="v1.0",
    system_instruction="You are an expert Test Failure Diagnoser. Distinguish strictly between factual Evidence (from logs, stack traces, DOM) and Hypotheses. Classify root cause into LOCATOR_CHANGED, TIMING_ISSUE, ASSERTION_FAILURE, ENVIRONMENT_ERROR, or UNKNOWN. Respond with valid JSON strictly matching the schema.",
    user_template="""Diagnose the following test failure:

Test Node ID: {nodeid}
Error Message: {error_message}
Stack Trace:
{stack_trace}
Failing Locator: {failing_locator}

Historical Context (Reference only, not current proof):
{historical_context}

Provide a structured JSON output with fields:
- classification: one of ["LOCATOR_CHANGED", "TIMING_ISSUE", "ASSERTION_FAILURE", "ENVIRONMENT_ERROR", "UNKNOWN"]
- root_cause: string
- evidence: list of strings (direct facts observed in current error/trace)
- hypotheses: list of strings (reasoned possibilities to investigate)
- recommended_actions: list of strings (concrete remediation steps)
- confidence: float between 0.0 and 1.0
""",
)

LOCATOR_REVIEW_PROMPT = PromptTemplate(
    prompt_id="locator_review",
    version="v1.0",
    system_instruction="You are a Semantic DOM Reviewer for Test Automation. Review proposed locator repairs to ensure semantic intent is preserved (e.g., verifying 'Add to Cart' is not mistakenly replaced with 'Add to Wishlist'). Respond with valid JSON strictly matching the schema.",
    user_template="""Perform semantic equivalence review on the following locator repair proposal:

Old Locator: {old_locator}
Proposed Candidate: {proposed_locator}
Strategy: {strategy}
DOM Snapshot Snippet:
{dom_snippet}
Error Message: {error_message}

Provide a structured JSON output with fields:
- is_semantically_equivalent: boolean
- confidence: float between 0.0 and 1.0
- explanation: string
- risk_warning: string or null
""",
)

CODE_ASSISTANT_PROMPT = PromptTemplate(
    prompt_id="code_assistant",
    version="v1.0",
    system_instruction="You are an expert QA Assistant inside Automation Studio. Provide concise, high-value code explanations, refactor suggestions, syntax fixes, or automation drafts. Respond with valid JSON strictly matching the schema.",
    user_template="""QA Assistant Request:

Action: {action}
User Message: {message}

Context:
- Current File: {current_file}
- Selected Code:
{selected_code}
- Project: {project_name}
- Requirement: {requirement_title}
- Test Case: {test_case_title}
- Validation Issues: {validation_issues}
- Git Diff: {git_diff}

Provide a structured JSON output with fields:
- reply: string
- suggested_code: string or null
- target_file: string or null
- action_type: string
- suggestions: list of strings
""",
)

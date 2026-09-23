from __future__ import annotations

import os
from dataclasses import dataclass, field


class BudgetExceededError(Exception):
    """Raised when an AI execution budget limit is exceeded."""

    pass


@dataclass
class AIBudgetGuard:
    max_requests: int = field(default_factory=lambda: int(os.getenv("QA_AI_MAX_REQUESTS_PER_RUN", "50")))
    max_input_tokens: int = field(default_factory=lambda: int(os.getenv("QA_AI_MAX_INPUT_TOKENS_PER_RUN", "100000")))
    max_output_tokens: int = field(default_factory=lambda: int(os.getenv("QA_AI_MAX_OUTPUT_TOKENS_PER_RUN", "50000")))

    requests_count: int = 0
    input_tokens_count: int = 0
    output_tokens_count: int = 0

    def check_and_record_request(self) -> None:
        if self.requests_count >= self.max_requests:
            raise BudgetExceededError(
                f"AI request budget exceeded: {self.requests_count}/{self.max_requests} requests executed."
            )
        self.requests_count += 1

    def record_tokens(self, input_tokens: int | None, output_tokens: int | None) -> None:
        if input_tokens:
            self.input_tokens_count += input_tokens
            if self.input_tokens_count > self.max_input_tokens:
                raise BudgetExceededError(
                    f"AI input token budget exceeded: {self.input_tokens_count}/{self.max_input_tokens} tokens."
                )
        if output_tokens:
            self.output_tokens_count += output_tokens
            if self.output_tokens_count > self.max_output_tokens:
                raise BudgetExceededError(
                    f"AI output token budget exceeded: {self.output_tokens_count}/{self.max_output_tokens} tokens."
                )

    def is_within_budget(self) -> bool:
        return (
            self.requests_count < self.max_requests
            and self.input_tokens_count < self.max_input_tokens
            and self.output_tokens_count < self.max_output_tokens
        )

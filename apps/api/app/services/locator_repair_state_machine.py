from __future__ import annotations

import re

from project_model.models import FailureRepairState

from app.persistence.models import LocatorRepairORM, utc_now


class IllegalLocatorRepairTransition(ValueError):
    def __init__(self, current: FailureRepairState, target: FailureRepairState) -> None:
        super().__init__(f"Illegal LocatorRepair transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


class LocatorRepairStateMachine:
    """The sole authority for validating and persisting LocatorRepair state transitions."""

    TRANSITIONS: dict[FailureRepairState, frozenset[FailureRepairState]] = {
        FailureRepairState.CREATED: frozenset(
            {FailureRepairState.ANALYZING, FailureRepairState.BLOCKED, FailureRepairState.NOT_APPLICABLE}
        ),
        FailureRepairState.ANALYZING: frozenset(
            {
                FailureRepairState.DECIDING,
                FailureRepairState.BLOCKED,
                FailureRepairState.FAILED,
                FailureRepairState.NOT_APPLICABLE,
            }
        ),
        FailureRepairState.DECIDING: frozenset(
            {
                FailureRepairState.VERIFYING_CANDIDATE,
                FailureRepairState.BLOCKED,
                FailureRepairState.FAILED,
                FailureRepairState.NOT_APPLICABLE,
            }
        ),
        FailureRepairState.VERIFYING_CANDIDATE: frozenset(
            {FailureRepairState.PATCH_READY, FailureRepairState.BLOCKED, FailureRepairState.FAILED}
        ),
        FailureRepairState.PATCH_READY: frozenset(
            {
                FailureRepairState.APPLYING,
                FailureRepairState.PATCH_APPLIED,
                FailureRepairState.BLOCKED,
                FailureRepairState.FAILED,
            }
        ),
        FailureRepairState.APPLYING: frozenset(
            {
                FailureRepairState.PATCH_READY,
                FailureRepairState.PATCH_APPLIED,
                FailureRepairState.BLOCKED,
                FailureRepairState.FAILED,
            }
        ),
        FailureRepairState.PATCH_APPLIED: frozenset(
            {
                FailureRepairState.VERIFYING_FIX,
                FailureRepairState.VERIFIED,
                FailureRepairState.FAILED,
                FailureRepairState.ROLLED_BACK,
            }
        ),
        FailureRepairState.VERIFYING_FIX: frozenset(
            {FailureRepairState.VERIFIED, FailureRepairState.FAILED, FailureRepairState.ROLLED_BACK}
        ),
        FailureRepairState.VERIFIED: frozenset({FailureRepairState.ROLLED_BACK}),
        FailureRepairState.FAILED: frozenset({FailureRepairState.VERIFYING_FIX, FailureRepairState.ROLLED_BACK}),
        FailureRepairState.BLOCKED: frozenset(),
        FailureRepairState.NOT_APPLICABLE: frozenset(),
        FailureRepairState.ROLLED_BACK: frozenset(),
    }

    @staticmethod
    def _state(value: FailureRepairState | str) -> FailureRepairState:
        if isinstance(value, FailureRepairState):
            return value
        return FailureRepairState(value)

    @staticmethod
    def _reason_code(reason: str | None, state: FailureRepairState) -> str | None:
        if state not in {FailureRepairState.BLOCKED, FailureRepairState.FAILED}:
            return None
        if isinstance(reason, str) and re.fullmatch(r"[A-Z0-9_:-]{1,128}", reason):
            return reason
        return "UNSPECIFIED_BLOCK" if state == FailureRepairState.BLOCKED else "UNSPECIFIED_FAILURE"

    @staticmethod
    def _candidate_id(value: str | None) -> str | None:
        return value if isinstance(value, str) and 0 < len(value) <= 128 else None

    async def create(
        self,
        repository,
        *,
        failure_id: str,
        analysis_id: str | None = None,
        initial_state: FailureRepairState = FailureRepairState.CREATED,
        block_reason: str | None = None,
        candidate_id: str | None = None,
        verification_run_id: str | None = None,
    ) -> LocatorRepairORM:
        existing = await repository.get_by_analysis(analysis_id) if analysis_id else None
        if existing is not None:
            return existing
        now = utc_now()
        return await repository.create(
            failure_id,
            analysis_id=analysis_id,
            state=initial_state,
            block_reason=self._reason_code(block_reason, initial_state),
            candidate_id=self._candidate_id(candidate_id),
            verification_run_id=verification_run_id,
            finished_at=(
                now
                if initial_state
                in {
                    FailureRepairState.BLOCKED,
                    FailureRepairState.FAILED,
                    FailureRepairState.NOT_APPLICABLE,
                    FailureRepairState.VERIFIED,
                    FailureRepairState.ROLLED_BACK,
                }
                else None
            ),
        )

    async def move(
        self,
        repository,
        repair_id: str,
        target: FailureRepairState | str,
        *,
        block_reason: str | None = None,
        candidate_id: str | None = None,
        verification_run_id: str | None = None,
    ) -> LocatorRepairORM:
        repair = await repository.get_by_id(repair_id)
        if repair is None:
            raise ValueError(f"LocatorRepair record not found: {repair_id}")
        current_state = repair.state
        next_state = self.transition(current_state, target)
        now = utc_now()
        if next_state != current_state:
            repair.state = next_state
            repair.updated_at = now
            repair.finished_at = (
                now
                if next_state
                in {
                    FailureRepairState.BLOCKED,
                    FailureRepairState.FAILED,
                    FailureRepairState.NOT_APPLICABLE,
                    FailureRepairState.VERIFIED,
                    FailureRepairState.ROLLED_BACK,
                }
                else None
            )
            if next_state in {FailureRepairState.BLOCKED, FailureRepairState.FAILED}:
                repair.block_reason = self._reason_code(block_reason, next_state)
            elif not (next_state == FailureRepairState.ROLLED_BACK and current_state == FailureRepairState.FAILED):
                repair.block_reason = None
        elif next_state in {FailureRepairState.BLOCKED, FailureRepairState.FAILED} and block_reason is not None:
            repair.block_reason = self._reason_code(block_reason, next_state)
        if candidate_id is not None:
            repair.candidate_id = self._candidate_id(candidate_id)
        if verification_run_id is not None:
            repair.verification_run_id = verification_run_id
        await repository.flush()
        return repair

    async def move_if_current(
        self,
        repository,
        repair_id: str,
        expected: FailureRepairState | str,
        target: FailureRepairState | str,
        *,
        block_reason: str | None = None,
        candidate_id: str | None = None,
        verification_run_id: str | None = None,
    ) -> bool:
        expected_state = self._state(expected)
        target_state = self.transition(expected_state, target)
        return await repository.transition_if_current(
            repair_id,
            expected_state,
            target_state,
            block_reason=self._reason_code(block_reason, target_state),
            candidate_id=self._candidate_id(candidate_id),
            verification_run_id=verification_run_id,
        )

    def transition(
        self,
        current: FailureRepairState | str,
        target: FailureRepairState | str,
    ) -> FailureRepairState:
        current_state = self._state(current)
        target_state = self._state(target)
        if current_state == target_state:
            return target_state
        if target_state not in self.TRANSITIONS[current_state]:
            raise IllegalLocatorRepairTransition(current_state, target_state)
        return target_state

    @classmethod
    def states(cls) -> tuple[FailureRepairState, ...]:
        return tuple(cls.TRANSITIONS)

    @classmethod
    def allowed_actions(cls, state: FailureRepairState | str) -> tuple[str, ...]:
        value = cls._state(state)
        actions = {
            FailureRepairState.CREATED: ("START_ANALYSIS",),
            # An in-flight analysis is owned by the analysis runtime, so these are the states where the
            # operator can still stop it instead of watching a request that never reports back.
            FailureRepairState.ANALYZING: ("CANCEL",),
            FailureRepairState.DECIDING: ("CANCEL",),
            FailureRepairState.VERIFYING_CANDIDATE: ("CANCEL",),
            FailureRepairState.PATCH_READY: ("APPLY", "REJECT", "START_ANALYSIS"),
            FailureRepairState.APPLYING: (),
            FailureRepairState.PATCH_APPLIED: ("VERIFY", "ROLLBACK"),
            FailureRepairState.VERIFYING_FIX: (),
            FailureRepairState.VERIFIED: ("ROLLBACK",),
            FailureRepairState.FAILED: ("VERIFY", "ROLLBACK", "START_ANALYSIS"),
            FailureRepairState.BLOCKED: ("START_ANALYSIS",),
            FailureRepairState.NOT_APPLICABLE: ("START_ANALYSIS",),
            FailureRepairState.ROLLED_BACK: ("START_ANALYSIS",),
        }
        return actions[value]

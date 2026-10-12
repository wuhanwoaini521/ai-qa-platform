from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from project_model.task_models import TaskCreate, TaskType
from qa_core.failure.redactor import SensitiveRedactor

from app.services.quality_discovery_models import DiscoveryStatus
from app.services.recorder_service import RecorderLocator, RecorderStep


class QualityDiscoveryDraftMixin:
    """Build human-reviewed pytest proposals from verified Discovery graph edges."""

    async def create_pytest_draft(self, run_id: str, journey_id: str, owner_id: str, task_commands):
        run = await self.get(run_id)
        if run is None:
            raise ValueError("Quality Discovery run not found.")
        if run.status != DiscoveryStatus.COMPLETED.value:
            raise ValueError("A pytest draft requires a completed Quality Discovery run.")

        if not journey_id or len(journey_id) > 100:
            raise ValueError("Invalid Quality Discovery journey ID.")
        result = run.result or {}
        journey = next(
            (item for item in result.get("journeys", []) if item.get("journey_id") == journey_id),
            None,
        )
        if journey is None:
            raise ValueError("Quality Discovery journey not found.")
        steps = self._journey_recording_steps(run, result, journey)

        slug = re.sub(r"[^a-z0-9]+", "_", journey_id.casefold()).strip("_")[:32] or "journey"
        run_key = re.sub(r"[^a-z0-9]", "", run.id.casefold())[:8] or "discovery"
        name = f"test_discovery_{run_key}_{slug}"
        file_path = f"tests/{name}.py"
        task = TaskCreate(
            type=TaskType.CREATE_TEST,
            goal=f"Prepare a pytest draft from Quality Discovery journey {journey_id}.",
            project_id=run.project_id,
            workspace_id=run.project_id,
            max_ai_calls=0,
            inputs={
                "case_name": f"Quality Discovery {journey_id}",
                "file_path": file_path,
                "test_name": name,
                "recorded_steps": [step.model_dump(mode="json", exclude_none=True) for step in steps],
                "assertion_bypass_check": True,
                "discovery_run_id": run.id,
                "discovery_journey_id": journey_id,
            },
        )
        return await task_commands.create(task, owner_id)

    def _journey_recording_steps(self, run: Any, result: dict[str, Any], journey: dict[str, Any]) -> list[RecorderStep]:
        start_url = str(run.start_url or "").strip()
        try:
            parsed_start = urlsplit(start_url)
        except ValueError as error:
            raise ValueError("The Discovery start URL is not safe to replay.") from error
        if (
            parsed_start.scheme not in {"http", "https"}
            or not parsed_start.hostname
            or parsed_start.username
            or parsed_start.password
            or parsed_start.query
            or parsed_start.fragment
            or not self._host_allowed(start_url, self._allowed_hosts(run))
        ):
            raise ValueError("The Discovery start URL is not safe to replay.")

        journey_steps = journey.get("steps")
        if (
            not isinstance(journey_steps, list)
            or len(journey_steps) < 2
            or any(not isinstance(item, dict) or not item.get("state_id") for item in journey_steps)
        ):
            raise ValueError("The selected journey has no verified state-changing transition to replay.")
        state_rows = result.get("states")
        if not isinstance(state_rows, list):
            raise ValueError("Discovery state evidence is incomplete; refusing to create a replay draft.")
        states = {item.get("state_id"): item for item in state_rows if isinstance(item, dict) and item.get("state_id")}
        if len(states) != len(state_rows):
            raise ValueError("Discovery state evidence is incomplete; refusing to create a replay draft.")
        edges = result.get("edges") or []
        actions = result.get("actions") or []
        if (
            not isinstance(edges, list)
            or not isinstance(actions, list)
            or any(not isinstance(item, dict) for item in [*edges, *actions])
        ):
            raise ValueError("Discovery transition evidence is incomplete; refusing to create a replay draft.")
        replay_steps = [RecorderStep(action="navigate", url=start_url, description="Open the observed start page")]

        for source_step, target_step in zip(journey_steps, journey_steps[1:]):
            source_id = source_step.get("state_id")
            target_id = target_step.get("state_id")
            source_state, target_state = states.get(source_id), states.get(target_id)
            if (
                source_state is None
                or target_state is None
                or not source_state.get("evidence_id")
                or not target_state.get("evidence_id")
            ):
                raise ValueError("The selected journey is missing observed state evidence.")
            matching_edges = [
                edge
                for edge in edges
                if edge.get("from_state_id") == source_id
                and edge.get("to_state_id") == target_id
                and (not target_step.get("action") or edge.get("label") == target_step.get("action"))
            ]
            if len(matching_edges) != 1:
                raise ValueError("The selected journey does not map to one unambiguous recorded transition.")
            edge = matching_edges[0]
            matching_actions = [
                action
                for action in actions
                if action.get("candidate_id") == edge.get("candidate_id")
                and action.get("from_state_id") == source_id
                and action.get("action_type") == edge.get("action")
                and action.get("status") == "EXECUTED"
                and action.get("state_changed") is True
                and action.get("to_fingerprint") == target_state.get("fingerprint")
            ]
            if len(matching_actions) != 1:
                raise ValueError(
                    "A journey transition was not successfully executed and verified; refusing to replay it."
                )
            action = matching_actions[0]
            self._append_replay_action(replay_steps, action, source_state)

        if len(replay_steps) < 2:
            raise ValueError("The selected journey has no verified transition to replay.")
        assertion = self._observed_final_assertion(states[journey_steps[-1]["state_id"]])
        replay_steps.append(assertion)
        if len(replay_steps) > 500:
            raise ValueError("The selected journey is too long to draft safely.")
        return replay_steps

    def _append_replay_action(
        self, steps: list[RecorderStep], action: dict[str, Any], source_state: dict[str, Any]
    ) -> None:
        action_type = str(action.get("action_type") or "")
        if action_type in {"scroll", "back"}:
            steps.append(
                RecorderStep(
                    action=action_type,
                    value="down" if action_type == "scroll" else None,
                    description=SensitiveRedactor.redact_text(str(action.get("target") or action_type))[:160],
                )
            )
            return

        target_id = str(action.get("target_id") or "")
        match = re.fullmatch(r"el_(\d+)", target_id)
        if not match:
            raise ValueError("A verified interaction has no stable observed control reference.")
        control_index = int(match.group(1))
        observed_controls = source_state.get("controls")
        if not isinstance(observed_controls, list) or any(not isinstance(item, dict) for item in observed_controls):
            raise ValueError("The source state has no valid observed-control evidence for replay.")
        controls = [
            item
            for item in observed_controls
            if item.get("index") == control_index and item.get("visible") and item.get("enabled", True)
        ]
        if len(controls) != 1:
            raise ValueError("A verified interaction no longer maps to one visible, enabled observed control.")
        control = controls[0]
        raw_locator = self._locator_for_control(control)
        if raw_locator is None:
            raise ValueError("A verified interaction has no replayable observed locator.")
        locator = RecorderLocator.model_validate(raw_locator)
        description = SensitiveRedactor.redact_text(str(action.get("target") or action_type))[:160]

        if action_type in {"click", "navigate"}:
            steps.append(RecorderStep(action="click", locator=locator, description=description))
        elif action_type == "search":
            if control.get("tag") != "input" or str(control.get("type") or "").lower() not in {"search", "text"}:
                raise ValueError("The observed search action does not target a replayable text input.")
            value = self._safe_replay_value(action.get("search_value"), "search value")
            steps.extend(
                [
                    RecorderStep(action="fill", locator=locator, value=value, description=f"Enter {description}"),
                    RecorderStep(action="press", locator=locator, key="Enter", description=f"Submit {description}"),
                ]
            )
        elif action_type == "select":
            if control.get("tag") != "select":
                raise ValueError("The observed selection target is not a select control.")
            value = self._safe_replay_value(action.get("selected_value"), "selected option")
            steps.append(
                RecorderStep(
                    action="select",
                    locator=locator,
                    value=value,
                    select_by_value=True,
                    description=description,
                )
            )
        else:
            raise ValueError(f"Discovery action '{action_type}' is not supported by the recorder replay path.")

    @staticmethod
    def _safe_replay_value(value: Any, label: str) -> str:
        text = str(value or "").strip()
        redacted = SensitiveRedactor.redact_text(text)
        if not text or len(text) > 200 or redacted != text:
            raise ValueError(f"The observed {label} is empty, too long, or contains sensitive data.")
        return text

    @staticmethod
    def _observed_final_assertion(state: dict[str, Any]) -> RecorderStep:
        if not state.get("evidence_id"):
            raise ValueError("The final journey state has no evidence for a grounded assertion.")
        landmarks = str(state.get("landmarks") or "")
        heading = re.search(r'heading\s+"([^"\r\n]{1,160})"\s+\[level=1\]', landmarks, re.I)
        if heading is None:
            heading = re.search(r'heading\s+"([^"\r\n]{1,160})"\s+\[level=\d+\]', landmarks, re.I)
        if heading:
            value = heading.group(1).strip()
            if value and SensitiveRedactor.redact_text(value) == value:
                return RecorderStep(
                    action="assert_text",
                    locator=RecorderLocator(kind="role", value="heading", name=value, exact=True),
                    value=value,
                    description="Assert the heading observed in the final Discovery state",
                )

        title = str(state.get("title") or "").strip()
        if title and len(title) <= 160 and SensitiveRedactor.redact_text(title) == title:
            return RecorderStep(
                action="assert_title",
                value=re.escape(title),
                description="Assert the title observed in the final Discovery state",
            )
        raise ValueError("The final journey state has no safe observable heading or title for an assertion.")

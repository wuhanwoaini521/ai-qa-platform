from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

import httpx
from project_model.models import RunnerHealthStatus, RunnerType, RunStatus
from qa_core.execution.runner_backend import (
    RunnerBackend,
    RunnerStatusResult,
    RunnerTriggerRequest,
    RunnerTriggerResult,
)
from qa_core.failure.redactor import SensitiveRedactor

logger = logging.getLogger("integrations.jenkins")


@dataclass
class JenkinsConfig:
    base_url: str = field(default_factory=lambda: os.getenv("JENKINS_BASE_URL", "http://localhost:8080"))
    job_name: str = "qa-automation-suite"
    user: str | None = field(default_factory=lambda: os.getenv("JENKINS_USER", None))
    api_token: str | None = field(default_factory=lambda: os.getenv("JENKINS_API_TOKEN", None))
    credential_reference: str | None = None
    default_parameters: dict[str, Any] = field(default_factory=dict)
    parameter_mapping: dict[str, str] = field(
        default_factory=lambda: {
            "region": "REGION",
            "brand": "BRAND",
            "mode": "MODE",
            "markers": "CASES_SPECIFIED",
            "workers": "NUM_PROCESSES",
            "reruns": "RERUNS",
            "nodeids": "TARGET_NODEIDS",
        }
    )
    timeout_seconds: float = 60.0
    poll_interval_seconds: float = 1.0


class JenkinsRunnerBackend(RunnerBackend):
    """Jenkins CI/CD Runner Platform Adapter."""

    def __init__(self, config: JenkinsConfig | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.config = config or JenkinsConfig()
        self.client = client
        self.base_url = self.config.base_url.rstrip("/")

    def _get_auth(self) -> tuple[str, str] | None:
        user = self.config.user or os.getenv("JENKINS_USER")
        token = self.config.api_token or os.getenv("JENKINS_API_TOKEN")
        if user and token:
            return (user, token)
        return None

    def _apply_parameter_mapping(self, request: RunnerTriggerRequest) -> dict[str, Any]:
        params = dict(self.config.default_parameters)

        # Merge custom payload parameters
        params.update(request.parameters)

        # Map platform fields according to configured ParameterMapping
        mapping = self.config.parameter_mapping
        if request.markers and "markers" in mapping:
            params[mapping["markers"]] = " and ".join(request.markers)
        if request.nodeids and "nodeids" in mapping:
            params[mapping["nodeids"]] = " ".join(request.nodeids)

        return params

    async def check_health(self) -> RunnerHealthStatus:
        if not self.config.base_url:
            return RunnerHealthStatus(
                runner_id="jenkins",
                type=RunnerType.JENKINS,
                status="DISABLED",
                message="Jenkins URL is not configured.",
                base_url=self.config.base_url,
            )

        auth = self._get_auth()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(
                    f"{self.base_url}/api/json",
                    auth=auth,
                )
                if res.status_code == 200:
                    return RunnerHealthStatus(
                        runner_id="jenkins",
                        type=RunnerType.JENKINS,
                        status="AVAILABLE",
                        message="Jenkins instance is accessible and healthy.",
                        base_url=self.base_url,
                    )
                elif res.status_code in (401, 403):
                    return RunnerHealthStatus(
                        runner_id="jenkins",
                        type=RunnerType.JENKINS,
                        status="AUTH_ERROR",
                        message="Authentication failed for Jenkins user credentials.",
                        base_url=self.base_url,
                    )
                else:
                    return RunnerHealthStatus(
                        runner_id="jenkins",
                        type=RunnerType.JENKINS,
                        status="UNAVAILABLE",
                        message=f"Jenkins returned HTTP {res.status_code}",
                        base_url=self.base_url,
                    )
        except httpx.TimeoutException:
            return RunnerHealthStatus(
                runner_id="jenkins",
                type=RunnerType.JENKINS,
                status="TIMEOUT",
                message="Health check timed out connecting to Jenkins.",
                base_url=self.base_url,
            )
        except Exception as e:
            redacted = SensitiveRedactor.redact_text(str(e))
            return RunnerHealthStatus(
                runner_id="jenkins",
                type=RunnerType.JENKINS,
                status="UNAVAILABLE",
                message=f"Connection error: {redacted}",
                base_url=self.base_url,
            )

    async def trigger(self, request: RunnerTriggerRequest) -> RunnerTriggerResult:
        auth = self._get_auth()
        params = self._apply_parameter_mapping(request)

        endpoint = (
            f"{self.base_url}/job/{self.config.job_name}/buildWithParameters"
            if params
            else f"{self.base_url}/job/{self.config.job_name}/build"
        )

        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            resp = await client.post(endpoint, data=params, auth=auth)
            if resp.status_code in (401, 403):
                raise PermissionError("Unauthorized to trigger Jenkins job. Check API credentials.")
            resp.raise_for_status()

            queue_location = resp.headers.get("Location")
            queue_id = None
            if queue_location:
                match = re.search(r"/queue/item/(\d+)/?", queue_location)
                if match:
                    queue_id = match.group(1)

            external_id = f"queue:{queue_id}" if queue_id else "queue:pending"
            return RunnerTriggerResult(
                run_id=request.run_id,
                external_job_id=external_id,
                status=RunStatus.RUNNING,
                message="Jenkins job triggered and queued successfully.",
            )

    async def resolve_build_number(self, queue_id: str, max_wait: float = 30.0) -> tuple[int | None, str | None]:
        auth = self._get_auth()
        start = time.perf_counter()

        while (time.perf_counter() - start) < max_wait:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.base_url}/queue/item/{queue_id}/api/json", auth=auth)
                if res.status_code == 200:
                    data = res.json()
                    executable = data.get("executable")
                    if executable and "number" in executable:
                        build_num = executable["number"]
                        build_url = executable.get("url") or f"{self.base_url}/job/{self.config.job_name}/{build_num}/"
                        return (build_num, build_url)
            await asyncio.sleep(self.config.poll_interval_seconds)

        return (None, None)

    async def get_status(self, run_id: str, external_job_id: str | None = None) -> RunnerStatusResult:
        if not external_job_id:
            return RunnerStatusResult(run_id=run_id, status=RunStatus.ERROR, error_message="No external job ID")

        # If still in queue, check if resolved
        if external_job_id.startswith("queue:"):
            qid = external_job_id.replace("queue:", "")
            build_num, build_url = await self.resolve_build_number(qid, max_wait=2.0)
            if not build_num:
                return RunnerStatusResult(
                    run_id=run_id,
                    external_job_id=external_job_id,
                    status=RunStatus.RUNNING,
                    queue_duration_ms=1000.0,
                )
            external_job_id = str(build_num)

        build_number = external_job_id
        auth = self._get_auth()

        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                f"{self.base_url}/job/{self.config.job_name}/{build_number}/api/json",
                auth=auth,
            )
            if res.status_code != 200:
                return RunnerStatusResult(
                    run_id=run_id,
                    external_job_id=build_number,
                    status=RunStatus.RUNNING,
                )

            data = res.json()
            is_building = data.get("building", False)
            result = data.get("result")
            duration_ms = float(data.get("duration", 0.0))
            build_url = data.get("url") or f"{self.base_url}/job/{self.config.job_name}/{build_number}/"

            if is_building:
                status = RunStatus.RUNNING
            elif result == "SUCCESS":
                status = RunStatus.PASSED
            elif result in ("FAILURE", "UNSTABLE"):
                status = RunStatus.FAILED
            elif result == "ABORTED":
                status = RunStatus.CANCELLED
            else:
                status = RunStatus.RUNNING

            artifacts = []
            # Allure report link
            artifacts.append(
                {
                    "name": "Allure Report",
                    "type": "ALLURE",
                    "url": f"{build_url}allure/",
                }
            )
            # HTML Report link
            artifacts.append(
                {
                    "name": "HTML Test Report",
                    "type": "HTML_REPORT",
                    "url": f"{build_url}HTML_Report/",
                }
            )

            return RunnerStatusResult(
                run_id=run_id,
                status=status,
                duration_ms=duration_ms,
                artifacts=artifacts,
                external_job_id=build_number,
                external_build_url=build_url,
            )

    async def stream_logs(self, run_id: str, external_job_id: str | None = None) -> AsyncGenerator[str, None]:
        if not external_job_id or external_job_id.startswith("queue:"):
            yield f"[Jenkins] Build queued in item {external_job_id}...\n"
            return

        build_number = external_job_id
        auth = self._get_auth()
        offset = 0

        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                f"{self.base_url}/job/{self.config.job_name}/{build_number}/logText/progressiveText?start={offset}",
                auth=auth,
            )
            if res.status_code == 200:
                yield res.text

    async def stop(self, run_id: str, external_job_id: str | None = None) -> bool:
        if not external_job_id or external_job_id.startswith("queue:"):
            return True

        auth = self._get_auth()
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(
                f"{self.base_url}/job/{self.config.job_name}/{external_job_id}/stop",
                auth=auth,
            )
            return res.status_code in (200, 302)


class FakeJenkinsServer:
    """In-memory mock Jenkins server simulating builds, logs, and queue transitions for CI testing."""

    def __init__(self, base_url: str = "http://fake-jenkins.local:8080", job_name: str = "qa-suite") -> None:
        self.base_url = base_url.rstrip("/")
        self.job_name = job_name
        self.next_queue_id = 100
        self.next_build_number = 42
        self.queue: dict[str, dict[str, Any]] = {}
        self.builds: dict[str, dict[str, Any]] = {}

    def handle_request(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path

        # Health check: /api/json
        if path == "/api/json":
            auth = req.headers.get("Authorization")
            if auth and "invalid" in auth:
                return httpx.Response(401, json={"error": "Invalid credentials"})
            return httpx.Response(200, json={"_class": "hudson.model.Hudson", "jobs": [{"name": self.job_name}]})

        # Trigger build: /job/{job_name}/buildWithParameters or /build
        if f"/job/{self.job_name}/build" in path:
            auth = req.headers.get("Authorization")
            if auth and "invalid" in auth:
                return httpx.Response(401, json={"error": "Unauthorized"})

            qid = str(self.next_queue_id)
            self.next_queue_id += 1
            bnum = str(self.next_build_number)
            self.next_build_number += 1

            self.queue[qid] = {
                "executable": {
                    "number": int(bnum),
                    "url": f"{self.base_url}/job/{self.job_name}/{bnum}/",
                }
            }
            self.builds[bnum] = {
                "building": False,
                "result": "SUCCESS",
                "duration": 4500,
                "url": f"{self.base_url}/job/{self.job_name}/{bnum}/",
            }

            headers = {"Location": f"{self.base_url}/queue/item/{qid}/"}
            return httpx.Response(201, headers=headers)

        # Queue poll: /queue/item/{id}/api/json
        queue_match = re.match(r"/queue/item/(\d+)/api/json", path)
        if queue_match:
            qid = queue_match.group(1)
            item = self.queue.get(
                qid, {"executable": {"number": 42, "url": f"{self.base_url}/job/{self.job_name}/42/"}}
            )
            return httpx.Response(200, json=item)

        # Build status: /job/{job_name}/{bnum}/api/json
        build_match = re.match(r"/job/[^/]+/(\d+)/api/json", path)
        if build_match:
            bnum = build_match.group(1)
            build = self.builds.get(
                bnum,
                {
                    "building": False,
                    "result": "SUCCESS",
                    "duration": 3500,
                    "url": f"{self.base_url}/job/{self.job_name}/{bnum}/",
                },
            )
            return httpx.Response(200, json=build)

        # Console logs: /job/{job_name}/{bnum}/logText/progressiveText
        if "/logText/progressiveText" in path:
            return httpx.Response(
                200, text="[pytest] Running automated test suite on Jenkins runner...\n[pytest] 5 passed in 4.2s\n"
            )

        # Stop build: /job/{job_name}/{bnum}/stop
        if "/stop" in path:
            return httpx.Response(200, text="Build aborted")

        return httpx.Response(404)

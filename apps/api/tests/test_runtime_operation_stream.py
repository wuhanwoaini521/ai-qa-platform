import asyncio
import json

import pytest
from app.services.operation_trace import stream_operation, trace_progress


async def test_progress_observes_real_boundaries_and_result_is_separate_from_trace():
    async def operation():
        await trace_progress("context.loaded", "Loaded context", metadata={"provider": "real", "prompt": "private"})
        return {"summary": "actual result"}

    frames = [frame async for frame in stream_operation(operation, "Analyze")]
    events = [json.loads(frame.split("data: ", 1)[1]) for frame in frames]
    assert [event["type"] for event in events] == ["run.started", "context.loaded", "operation.result", "run.completed"]
    assert events[1]["metadata"] == {"provider": "real"}
    assert json.loads(events[2]["content"]) == {"summary": "actual result"}
    assert "private" not in "".join(frames)


async def test_stream_cancel_cleans_up_operation_even_when_progress_queue_is_full():
    stopped = asyncio.Event()

    async def operation():
        try:
            for _ in range(100):
                await trace_progress("model.started", "Running")
        finally:
            stopped.set()

    stream = stream_operation(operation, "Start")
    await anext(stream)
    await asyncio.sleep(0)
    await asyncio.wait_for(stream.aclose(), timeout=1)
    assert stopped.is_set()


async def test_operation_result_keeps_json_valid_when_generated_code_contains_password_assignment():
    generated_code = """def test_sign_in():
    password = "demo_password"
    assert password
"""

    async def operation():
        return {"suggested_code": generated_code}

    frames = [frame async for frame in stream_operation(operation, "Generate automation")]
    result_event = next(
        json.loads(frame.split("data: ", 1)[1]) for frame in frames if "event: operation.result" in frame
    )

    assert json.loads(result_event["content"]) == {"suggested_code": generated_code}


@pytest.mark.parametrize("error", [RuntimeError, ValueError])
async def test_stream_failure_does_not_leak_provider_exception_bodies(error):
    async def operation():
        raise error("raw prompt and hidden reasoning and api_key=secret")

    frames = [frame async for frame in stream_operation(operation, "Start")]
    failure = next(frame for frame in frames if "run.failed" in frame)
    assert f"执行失败 ({error.__name__})；请检查输入和生成结果。" in failure
    assert "provider" not in failure.lower()
    assert "hidden reasoning" not in "".join(frames) and "api_key=" not in "".join(frames)


def test_runtime_services_import_without_initializing_api_router_package():
    import os
    import subprocess
    import sys
    from pathlib import Path

    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.services.runtime_projection import RuntimeProjection; from app.services.operation_trace import stream_operation",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr

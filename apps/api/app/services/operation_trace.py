"""Observe existing operations at their actual boundaries, without a second execution engine."""

import asyncio
import json
from contextvars import ContextVar
from uuid import uuid4

from qa_core.ai.trace import make_trace_event

from app.event_stream import event_frame
from app.services.event_normalizer import public_metadata

active_trace = ContextVar("active_operation_trace", default=None)


async def trace_progress(event_type, title, *, metadata=None, duration_ms=None):
    trace = active_trace.get()
    if trace is None:
        return
    run_id, queue = trace
    event = make_trace_event(
        run_id,
        event_type,
        stage=event_type.split(".")[0],
        title=title,
        status="RUNNING" if event_type.endswith("started") else "COMPLETED",
        metadata=public_metadata(metadata),
        duration_ms=duration_ms,
    )
    await queue.put(event)


async def stream_operation(operation, title):
    queue = asyncio.Queue(maxsize=16)
    run_id = uuid4().hex

    async def execute():
        token = active_trace.set((run_id, queue))
        try:
            await trace_progress("run.started", title)
            result = await operation()

            def encode(value):
                return value.model_dump(mode="json") if hasattr(value, "model_dump") else value

            payload = json.dumps(result, default=encode, ensure_ascii=False)
            await queue.put(
                make_trace_event(run_id, "operation.result", stage="result", title="Result", content=payload)
            )
            await trace_progress("run.completed", "执行完成")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Provider exception bodies may contain prompts or credentials. Publish only their class.
            message = f"执行失败 ({type(error).__name__})；请检查输入及 AI provider 状态。"
            await queue.put(
                make_trace_event(
                    run_id, "run.failed", stage="operation", title="执行失败", status="FAILED", message=message
                )
            )
        finally:
            active_trace.reset(token)
            if not asyncio.current_task().cancelling():
                await queue.put(None)

    task = asyncio.create_task(execute())
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event_frame(event.type, event, event_id=event.event_id)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

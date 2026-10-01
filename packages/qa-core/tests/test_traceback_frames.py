from pathlib import Path

from qa_core.failure.traceback_frames import last_user_code_frame


def test_last_user_frame_ignores_dependency_frames_and_returns_workspace_relative_path(tmp_path: Path):
    test_file = tmp_path / "tests" / "test_cart.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_cart():\n    assert False\n", encoding="utf-8")
    stack_trace = (
        'File "C:/python/Lib/site-packages/playwright/_impl/_sync_base.py", line 70, in _sync\n'
        f'File "{test_file.as_posix()}", line 2, in test_cart\n'
    )

    assert last_user_code_frame(stack_trace, tmp_path) == ("tests/test_cart.py", 2)


def test_last_user_frame_rejects_outside_workspace_and_missing_source(tmp_path: Path):
    stack_trace = 'File "C:/python/Lib/site-packages/pytest/runner.py", line 10, in run\n'

    assert last_user_code_frame(stack_trace, tmp_path) is None

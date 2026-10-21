"""Errors a workflow authoring operation can raise, shared by the repository, the service and the
routes. They live here so an API router never has to import the repository layer (see
`apps/api/tests/test_architecture_boundaries.py`).
"""


class WorkflowVersionConflict(RuntimeError):
    """The definition changed under the caller (stale version or an already published version)."""


class WorkflowVersionNotFound(LookupError):
    """A requested definition, version or related row does not exist."""

"""Compatibility names for the shared repository scope application port."""

from app.ports.repository_scope import RepositoryScope, RepositoryScopeFactory

TaskUnitOfWork = RepositoryScope
TaskUnitOfWorkFactory = RepositoryScopeFactory

from __future__ import annotations

import os

from qa_core.failure.redactor import SensitiveRedactor

_PLATFORM_PREFIXES = ("QA_", "AI_QA_", "JEV_", "APP_", "WORKER_", "JIRA_", "TESTRAIL_", "JENKINS_", "GITHUB_", "GH_")
_CLOUD_PREFIXES = ("AWS_", "AZURE_", "GOOGLE_", "GCP_", "CLOUDSDK_AUTH_")
_CREDENTIAL_SUFFIXES = ("_KEY", "_KEY_ID", "_CREDENTIALS", "_CONNECTION_STRING")
_CREDENTIAL_NAMES = {"SSH_AUTH_SOCK", "GIT_ASKPASS", "DATABASE_URL", "QA_DATABASE_URL"}
_RUN_CAPABILITY_KEYS = {"QA_FAILURE_SNAPSHOT_ENCRYPTION_KEY"}
# Recorder secrets are named explicitly per recording step and supplied per run;
# they are the one credential-shaped group the generated test requires.
_RECORDER_SECRET_PREFIX = "QA_RECORDER_SECRET_"
# API cases fetch their credentials from the run environment on purpose, same as recorder secrets.
_API_SECRET_PREFIX = "QA_API_SECRET_"


def _credential_name(key: str) -> bool:
    name = key.upper()
    return bool(
        SensitiveRedactor.SENSITIVE_KEYS.search(name)
        or name.endswith(_CREDENTIAL_SUFFIXES)
        or name in _CREDENTIAL_NAMES
    )


def project_subprocess_environment(environment: dict[str, str] | None = None) -> dict[str, str]:
    """Forward explicit test settings without inheriting the platform's ambient credentials."""
    result = {
        key: value
        for key, value in os.environ.items()
        if not _credential_name(key) and not key.upper().startswith(_CLOUD_PREFIXES)
    }
    for key, value in (environment or {}).items():
        name = key.upper()
        if (
            name not in _RUN_CAPABILITY_KEYS
            and not name.startswith(_RECORDER_SECRET_PREFIX)
            and not name.startswith(_API_SECRET_PREFIX)
            and name.startswith(_PLATFORM_PREFIXES)
            and _credential_name(name)
        ):
            continue
        result[key] = value
    return result

"""Onboarding a real QA repository: describing, detecting, importing and piloting it.

Nothing in this package writes to, or executes inside, the inspected project: detection is
read-only, imports copy into an isolated workspace, and execution goes through an explicit
safety policy plus a per-project runtime.
"""

from qa_core.onboarding.allure import (
    AllureAttachment,
    AllureImportReport,
    AllureResultImporter,
    AllureTestCaseResult,
)
from qa_core.onboarding.collector import (
    CollectedTest,
    CollectionOutcome,
    CollectionStatus,
    LogicalTestOutcome,
    QAProjectCollector,
    QAProjectRunner,
    RunStatus,
    SuiteRunOutcome,
    parse_collection,
    parse_execution,
    parse_nodeid,
    parse_report_log,
    run_project_command,
)
from qa_core.onboarding.contract import (
    CaseIdStrategy,
    PackageManager,
    QAProjectContract,
    QAProjectFramework,
    QARuntimeProfile,
    load_contract_file,
    render_contract,
)
from qa_core.onboarding.detector import DetectionEvidence, QAProjectDetection, QAProjectDetector
from qa_core.onboarding.identity import (
    CaseIdentity,
    CaseIdSource,
    IdentityReport,
    NodeIdCaseMapper,
    normalise_case_id,
)
from qa_core.onboarding.importing import (
    ImportConflict,
    ImportPlan,
    ImportResult,
    QAProjectImporter,
)
from qa_core.onboarding.pytest_plugin import PLUGIN_SOURCE, write_plugin
from qa_core.onboarding.runtime import (
    ProvisioningStatus,
    QARuntimeProvisioner,
    RuntimeProvisioningResult,
)
from qa_core.onboarding.safety import SafetyPolicy, SafetyVerdict

__all__ = [
    "AllureAttachment",
    "AllureImportReport",
    "AllureResultImporter",
    "AllureTestCaseResult",
    "CaseIdSource",
    "CaseIdStrategy",
    "CaseIdentity",
    "CollectedTest",
    "CollectionOutcome",
    "CollectionStatus",
    "DetectionEvidence",
    "IdentityReport",
    "ImportConflict",
    "ImportPlan",
    "ImportResult",
    "LogicalTestOutcome",
    "PackageManager",
    "ProvisioningStatus",
    "QAProjectCollector",
    "QAProjectContract",
    "QAProjectDetection",
    "QAProjectDetector",
    "QAProjectFramework",
    "QAProjectImporter",
    "QAProjectRunner",
    "QARuntimeProfile",
    "QARuntimeProvisioner",
    "RunStatus",
    "RuntimeProvisioningResult",
    "SafetyPolicy",
    "SafetyVerdict",
    "SuiteRunOutcome",
    "NodeIdCaseMapper",
    "load_contract_file",
    "normalise_case_id",
    "parse_collection",
    "parse_execution",
    "parse_nodeid",
    "PLUGIN_SOURCE",
    "parse_report_log",
    "render_contract",
    "run_project_command",
    "write_plugin",
]

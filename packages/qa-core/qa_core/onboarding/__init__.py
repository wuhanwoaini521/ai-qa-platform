"""Onboarding a real QA repository: describing, detecting and importing it without writing to it."""

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

__all__ = [
    "CaseIdStrategy",
    "DetectionEvidence",
    "PackageManager",
    "QAProjectContract",
    "QAProjectDetection",
    "QAProjectDetector",
    "QAProjectFramework",
    "QARuntimeProfile",
    "load_contract_file",
    "render_contract",
]

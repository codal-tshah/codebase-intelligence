from ci_adapters_django.adapter import (
    ADAPTER_VERSION,
    DjangoAnalysisResult,
    analyze_django_project,
    detect_django,
)
from ci_adapters_django.analyzer import ANALYZER, PythonAnalyzer

__all__ = [
    "ADAPTER_VERSION",
    "ANALYZER",
    "DjangoAnalysisResult",
    "PythonAnalyzer",
    "analyze_django_project",
    "detect_django",
]

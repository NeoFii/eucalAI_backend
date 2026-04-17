"""Testing service ORM models."""

from testing_service.models.model import (
    AdminProbeAuditLog,
    BenchmarkJob,
    Model,
    ModelCategory,
    ModelCategoryMap,
    ModelProviderOffering,
    ModelVendor,
    Provider,
    ProviderPerformanceDailyStat,
    ProviderPerformanceMetric,
    ProviderProbeConfig,
    ProviderMetricsRanked,
)

SERVICE_MODELS = [
    ModelCategory,
    ModelVendor,
    Model,
    ModelCategoryMap,
    Provider,
    ProviderProbeConfig,
    ModelProviderOffering,
    ProviderPerformanceMetric,
    ProviderPerformanceDailyStat,
    BenchmarkJob,
    AdminProbeAuditLog,
]

__all__ = [
    "ModelCategory",
    "ModelVendor",
    "Model",
    "ModelCategoryMap",
    "Provider",
    "ProviderProbeConfig",
    "ModelProviderOffering",
    "ProviderPerformanceMetric",
    "ProviderPerformanceDailyStat",
    "BenchmarkJob",
    "AdminProbeAuditLog",
    "ProviderMetricsRanked",
    "SERVICE_MODELS",
]

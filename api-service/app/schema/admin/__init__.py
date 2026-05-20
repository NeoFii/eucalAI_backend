"""Admin-domain schema aggregator.

Plan 05-01 / Task 2 ships the auth + admin_user + audit_log schemas. Plans
05-02 and 05-03 will append additional schema modules (pool / model_catalog
/ routing_setting / route_monitor / service_logs / user_management /
voucher) BELOW their respective anchor lines so Wave 2 inserts are
deterministic and there is no concurrent-modification race (Warning 3
Option A).

The two anchor lines at the bottom of this file MUST appear EXACTLY as
written — Wave 2 plans (05-02 / 05-03) grep for these strings as the
`old_string` of their Edit calls.
"""

from __future__ import annotations

from app.schema.admin.admin_user import (
    AdminListItem,
    AdminListResponse,
    CreateAdminRequest,
    CreateAdminResponse,
    CreateAdminResponseData,
    ResetAdminPasswordRequest,
    UpdateAdminRoleRequest,
    UpdateAdminStatusRequest,
)
from app.schema.admin.audit_log import (
    AdminAuditActor,
    AdminAuditCategory,
    AdminAuditLogItem,
    AdminAuditLogListResponse,
    AdminAuditLogMetaData,
    AdminAuditLogMetaResponse,
    UpdateActionLabelRequest,
    UpdateActionLabelResponse,
)
from app.schema.admin.auth import (
    AdminChangePasswordRequest,
    AdminChangePasswordResponse,
    AdminInfoResponse,
    AdminInfoResponseData,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminLoginResponseData,
    AdminLogoutResponse,
    AdminRefreshResponse,
    AdminRefreshResponseData,
    AdminUserData,
)

__all__ = [
    "AdminAuditActor",
    "AdminAuditCategory",
    "AdminAuditLogItem",
    "AdminAuditLogListResponse",
    "AdminAuditLogMetaData",
    "AdminAuditLogMetaResponse",
    "AdminChangePasswordRequest",
    "AdminChangePasswordResponse",
    "AdminInfoResponse",
    "AdminInfoResponseData",
    "AdminListItem",
    "AdminListResponse",
    "AdminLoginRequest",
    "AdminLoginResponse",
    "AdminLoginResponseData",
    "AdminLogoutResponse",
    "AdminRefreshResponse",
    "AdminRefreshResponseData",
    "AdminUserData",
    "CreateAdminRequest",
    "CreateAdminResponse",
    "CreateAdminResponseData",
    "ResetAdminPasswordRequest",
    "UpdateActionLabelRequest",
    "UpdateActionLabelResponse",
    "UpdateAdminRoleRequest",
    "UpdateAdminStatusRequest",
]

# === Plan 05-02 imports (Wave 2) ===
# (05-02 inserts schema re-exports below this line)
from app.schema.admin.pool import (  # noqa: E402
    AccountBalanceResult,
    AvailableModelSlugItem,
    AvailableModelSlugsResponse,
    CheckBalancesResponse,
    CheckBalancesResult,
    ModelCostInfo,
    ModelCostPoolItem,
    ModelCostResponse,
    PoolAccountCreate,
    PoolAccountItem,
    PoolAccountResponse,
    PoolAccountUpdate,
    PoolCreate,
    PoolDetail,
    PoolDetailResponse,
    PoolItem,
    PoolListResponse,
    PoolModelCreate,
    PoolModelItem,
    PoolModelResponse,
    PoolModelUpdate,
    PoolResponse,
    PoolUpdate,
    SyncModelsResponse,
    SyncModelsResult,
)
from app.schema.admin.model_catalog import (  # noqa: E402
    ModelCatalogOperationResponse,
    ModelCategoryCreate,
    ModelCategoryListResponse,
    ModelCategoryResponse,
    ModelCategoryUpdate,
    ModelVendorCreate,
    ModelVendorListResponse,
    ModelVendorResponse,
    ModelVendorUpdate,
    SupportedModelCreate,
    SupportedModelListResponse,
    SupportedModelResponse,
    SupportedModelUpdate,
)
from app.schema.admin.routing_setting import (  # noqa: E402
    RoutingSettingBatchItem,
    RoutingSettingBatchUpdate,
    RoutingSettingGroupResponse,
    RoutingSettingItem,
    RoutingSettingResponse,
    RoutingSettingUpdate,
)
# === Plan 05-03 imports (Wave 2) ===
# (05-03 inserts schema re-exports below this line)
from app.schema.admin.user_management import (  # noqa: E402
    AdjustUserBalanceRequest,
    ResetUserPasswordRequest,
    TopupUserRequest,
    UpdateUserRpmRequest,
    UpdateUserStatusRequest,
    UserApiKeyItem,
    UserApiKeyListResponse,
    UserDetailData,
    UserDetailResponse,
    UserListItem,
    UserListResponse,
    UserOperationResponse,
    UserTransactionItem,
    UserTransactionListResponse,
    UserUsageAnalyticsResponse,
    UserUsageLogItem,
    UserUsageLogListResponse,
    UserUsageStatItem,
    UserUsageStatListResponse,
)
from app.schema.admin.voucher import (  # noqa: E402
    GenerateVoucherCodesRequest,
    VoucherCodeCreateResponse,
    VoucherCodeItem,
    VoucherCodeListResponse,
    VoucherCodeResponse,
    VoucherOperationResponse,
)
from app.schema.admin.route_monitor import (  # noqa: E402
    RouteAggregateResponse,
    RouteCompareResponse,
    RouteRequestDetailResponse,
    RouteRequestListResponse,
)
from app.schema.admin.service_logs import (  # noqa: E402
    ServiceLogEntry,
    ServiceLogResult,
    ServiceLogsResponseData,
)

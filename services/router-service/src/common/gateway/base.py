"""Gateway base — intentionally empty.

All gateways in router-service are standalone classes with injected
dependencies (settings, buffers). No shared base class is needed; the
real abstraction layer is `common.internal.request_internal_json`.
"""

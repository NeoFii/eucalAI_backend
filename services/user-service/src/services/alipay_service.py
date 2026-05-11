"""Alipay payment gateway operations."""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any

from alipay.aop.api.AlipayClientConfig import AlipayClientConfig
from alipay.aop.api.DefaultAlipayClient import DefaultAlipayClient
from alipay.aop.api.domain.AlipayTradePagePayModel import AlipayTradePagePayModel
from alipay.aop.api.domain.AlipayTradeQueryModel import AlipayTradeQueryModel
from alipay.aop.api.domain.AlipayTradeWapPayModel import AlipayTradeWapPayModel
from alipay.aop.api.request.AlipayTradePagePayRequest import AlipayTradePagePayRequest
from alipay.aop.api.request.AlipayTradeQueryRequest import AlipayTradeQueryRequest
from alipay.aop.api.request.AlipayTradeWapPayRequest import AlipayTradeWapPayRequest
from alipay.aop.api.response.AlipayTradeQueryResponse import AlipayTradeQueryResponse
from alipay.aop.api.util.SignatureUtils import verify_with_rsa

from common.utils.log import log_event
from core.config import settings

logger = logging.getLogger(__name__)

_client: DefaultAlipayClient | None = None


def _get_client() -> DefaultAlipayClient:
    global _client
    if _client is not None:
        return _client
    config = AlipayClientConfig()
    config.server_url = settings.ALIPAY_GATEWAY
    config.app_id = settings.ALIPAY_APP_ID
    config.app_private_key = settings.ALIPAY_PRIVATE_KEY
    config.alipay_public_key = settings.ALIPAY_PUBLIC_KEY
    config.sign_type = "RSA2"
    _client = DefaultAlipayClient(alipay_client_config=config)
    return _client


def _micro_to_yuan(micro_amount: int) -> str:
    return str(Decimal(micro_amount) / Decimal(1_000_000))


class AlipayService:
    """Alipay payment gateway operations."""

    @staticmethod
    def create_page_pay(order_no: str, amount: int, subject: str) -> str:
        """Generate PC payment form HTML via alipay.trade.page.pay."""
        model = AlipayTradePagePayModel()
        model.out_trade_no = order_no
        model.total_amount = _micro_to_yuan(amount)
        model.subject = subject
        model.product_code = "FAST_INSTANT_TRADE_PAY"
        model.timeout_express = settings.ALIPAY_ORDER_TIMEOUT

        request = AlipayTradePagePayRequest(biz_model=model)
        request.notify_url = settings.ALIPAY_NOTIFY_URL
        request.return_url = settings.ALIPAY_RETURN_URL

        form_html = _get_client().page_execute(request, http_method="GET")
        log_event(logger, "info", "alipayPagePayCreated", order_no=order_no)
        return form_html

    @staticmethod
    def create_wap_pay(order_no: str, amount: int, subject: str) -> str:
        """Generate mobile payment form HTML via alipay.trade.wap.pay."""
        model = AlipayTradeWapPayModel()
        model.out_trade_no = order_no
        model.total_amount = _micro_to_yuan(amount)
        model.subject = subject
        model.product_code = "QUICK_WAP_WAY"
        model.timeout_express = settings.ALIPAY_ORDER_TIMEOUT

        request = AlipayTradeWapPayRequest(biz_model=model)
        request.notify_url = settings.ALIPAY_NOTIFY_URL
        request.return_url = settings.ALIPAY_RETURN_URL

        form_html = _get_client().page_execute(request, http_method="GET")
        log_event(logger, "info", "alipayWapPayCreated", order_no=order_no)
        return form_html

    @staticmethod
    def verify_notify(params: dict[str, str]) -> bool:
        """Verify async notification signature using Alipay public key."""
        sign = params.get("sign", "")
        sign_type = params.get("sign_type", "RSA2")
        if not sign:
            return False

        # Build the string to verify: sorted key=value pairs excluding sign/sign_type
        filtered = {
            k: v for k, v in params.items()
            if k not in ("sign", "sign_type") and v
        }
        sorted_params = sorted(filtered.items())
        unsigned_str = "&".join(f"{k}={v}" for k, v in sorted_params)

        try:
            return verify_with_rsa(
                settings.ALIPAY_PUBLIC_KEY,
                unsigned_str.encode("utf-8"),
                sign,
            )
        except Exception:
            log_event(logger, "warning", "alipayVerifyFailed")
            return False

    @staticmethod
    async def query_trade(order_no: str) -> dict[str, Any] | None:
        """Query trade status via alipay.trade.query. Wrapped in thread for async."""
        def _sync_query() -> dict[str, Any] | None:
            model = AlipayTradeQueryModel()
            model.out_trade_no = order_no
            request = AlipayTradeQueryRequest(biz_model=model)

            try:
                response_content = _get_client().execute(request)
            except Exception:
                log_event(logger, "error", "alipayQueryFailed", order_no=order_no)
                return None

            if not response_content:
                return None

            response = AlipayTradeQueryResponse()
            response.parse_response_content(response_content)
            if response.is_success():
                return {
                    "trade_no": response.trade_no,
                    "trade_status": response.trade_status,
                    "total_amount": response.total_amount,
                    "out_trade_no": response.out_trade_no,
                }
            return None

        return await asyncio.to_thread(_sync_query)

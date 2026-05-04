"""Schemas for core internal endpoints."""

from pydantic import BaseModel


class InternalUserResponse(BaseModel):
    id: int
    uid: str
    email: str
    status: int


class InternalUserStatsResponse(BaseModel):
    total_users: int


class InternalApiKeyValidateRequest(BaseModel):
    key: str
    model: str | None = None
    client_ip: str | None = None


class InternalApiKeyValidateResponse(BaseModel):
    id: int
    user_id: int
    name: str
    balance: int
    user_rpm_limit: int | None = None

"""Model vendor schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class ModelVendorResponse(BaseModel):
    id: int
    slug: str
    name: str
    logo_url: Optional[str] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ModelVendorBrief(BaseModel):
    id: int
    slug: str
    name: str
    logo_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class VendorCreate(BaseModel):
    slug: str
    name: str
    logo_url: Optional[str] = None
    is_active: bool = True


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    is_active: Optional[bool] = None

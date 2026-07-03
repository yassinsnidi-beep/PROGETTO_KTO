"""Pydantic document models used before MongoDB writes."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class EmbeddingPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = ""
    vector: list[float] = Field(default_factory=list)
    model: Optional[str] = None


class MultiLangEmbeddings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    it: EmbeddingPayload = Field(default_factory=EmbeddingPayload)
    en: EmbeddingPayload = Field(default_factory=EmbeddingPayload)


class CompanyDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(alias="_id")
    source: str
    company_name: Optional[str] = None
    normalized_name: Optional[str] = None
    tax_code: Optional[str] = None
    cciaa_number: Optional[str] = None
    location: dict[str, Any]
    industry_classification: dict[str, Any]
    business_profile: dict[str, Any]
    embeddings: MultiLangEmbeddings
    financials: dict[str, Any]
    metrics: dict[str, Any]
    data_quality: dict[str, bool]
    created_at: str
    updated_at: str


class IndustryDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(alias="_id")
    source: str
    system: str
    code: str
    raw_code: Optional[str] = None
    level: str
    labels: dict[str, Any]
    group: dict[str, Any]
    division: dict[str, Any]
    section: dict[str, Any]
    embeddings: MultiLangEmbeddings
    created_at: str
    updated_at: str


class PatentDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(alias="_id")
    source: str
    scheda_id: str
    title: Optional[str] = None
    subtitle: Optional[str] = None
    url: Optional[str] = None
    abstract: Optional[str] = None
    short_description: Optional[str] = None
    full_description: Optional[str] = None
    advantages: list[str] = Field(default_factory=list)
    applications: list[str] = Field(default_factory=list)
    development_stage: Optional[str] = None
    trl: Optional[int] = None
    protection_type: Optional[str] = None
    patent_status: Optional[str] = None
    patent_number: Optional[str] = None
    application_number: Optional[str] = None
    kto: dict[str, Any]
    embeddings: MultiLangEmbeddings
    data_quality: dict[str, bool]
    created_at: str
    updated_at: str

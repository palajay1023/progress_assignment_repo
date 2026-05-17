from pydantic import BaseModel, field_validator
from typing import Optional, List, Any
from datetime import datetime


class RunCreate(BaseModel):
    topics: Optional[str] = ""
    urls: Optional[str] = ""
    role: Optional[str] = "general"
    discover_related: bool = False

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in ("general", "pm", "exec"):
            return "general"
        return v


class SourceFetchOut(BaseModel):
    url: str
    fetch_status: str
    extracted_text_length: int
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class ClaimOut(BaseModel):
    claim: str
    source_url: str
    verdict: str
    verdict_reason: str

    class Config:
        from_attributes = True


class RunStatusOut(BaseModel):
    run_id: str
    status: str
    current_step_detail: Optional[str] = None
    source_fetches: List[SourceFetchOut] = []
    report_json: Optional[Any] = None
    claims: List[ClaimOut] = []
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class RunListItem(BaseModel):
    id: str
    topics: List[str]
    role: str
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

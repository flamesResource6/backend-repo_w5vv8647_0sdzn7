"""
Database Schemas for API Monitoring SaaS

Each Pydantic model represents a MongoDB collection. The collection name is the lowercase
of the class name (e.g., Project -> "project").
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal

class Project(BaseModel):
    name: str = Field(..., description="Project display name")
    slug: str = Field(..., description="URL-friendly identifier")
    description: Optional[str] = Field(None, description="Short description")

class Apikey(BaseModel):
    project_id: str = Field(..., description="Associated project id (string)")
    name: str = Field(..., description="Key label")
    key: str = Field(..., description="The API key value")
    active: bool = Field(True, description="Whether key is active")

class Apievent(BaseModel):
    project_id: str = Field(..., description="Project id")
    api_key_id: Optional[str] = Field(None, description="API key id if provided")
    method: Literal["GET","POST","PUT","PATCH","DELETE","OPTIONS","HEAD"] = Field(...)
    path: str = Field(..., description="Request path")
    status: int = Field(..., ge=100, le=599)
    latency_ms: float = Field(..., ge=0)
    ip: Optional[str] = Field(None)
    user_agent: Optional[str] = Field(None)
    request_size: Optional[int] = Field(None, ge=0)
    response_size: Optional[int] = Field(None, ge=0)
    error_message: Optional[str] = Field(None)

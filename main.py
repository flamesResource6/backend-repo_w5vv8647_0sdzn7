import os
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from bson import ObjectId

from database import db, create_document, get_documents

app = FastAPI(title="API Monitoring SaaS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CreateProject(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None

class CreateApiKey(BaseModel):
    project_id: str
    name: str

class IngestEvent(BaseModel):
    project_slug: str
    api_key: Optional[str] = None
    method: str
    path: str
    status: int
    latency_ms: float
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    request_size: Optional[int] = None
    response_size: Optional[int] = None
    error_message: Optional[str] = None


def to_str_id(doc: Dict[str, Any]) -> Dict[str, Any]:
    if doc is None:
        return doc
    d = dict(doc)
    if d.get("_id"):
        d["id"] = str(d.pop("_id"))
    return d

@app.get("/")
def root():
    return {"message": "API Monitoring SaaS backend running"}

@app.get("/test")
def test_database():
    info = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "collections": []
    }
    try:
        if db is not None:
            info["database"] = "✅ Connected"
            info["collections"] = db.list_collection_names()
    except Exception as e:
        info["database"] = f"⚠️ {str(e)[:80]}"
    return info

# Projects
@app.post("/api/projects")
def create_project(payload: CreateProject):
    from schemas import Project  # type: ignore
    proj = Project(**payload.model_dump())
    pid = create_document("project", proj)
    return {"id": pid}

@app.get("/api/projects")
def list_projects():
    docs = get_documents("project", {}, 50)
    return [to_str_id(d) for d in docs]

# API Keys
@app.post("/api/keys")
def create_key(payload: CreateApiKey):
    from schemas import Apikey  # type: ignore
    import secrets
    # Validate project exists
    try:
        proj = db["project"].find_one({"_id": ObjectId(payload.project_id)})
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid project id")

    key_value = secrets.token_urlsafe(24)
    doc = Apikey(project_id=payload.project_id, name=payload.name, key=key_value, active=True)
    kid = create_document("apikey", doc)
    return {"id": kid, "key": key_value}

@app.get("/api/keys")
def list_keys(project_id: str):
    docs = get_documents("apikey", {"project_id": project_id}, 100)
    return [to_str_id(d) for d in docs]

# Ingest events
@app.post("/ingest")
def ingest(event: IngestEvent, x_forwarded_for: Optional[str] = Header(default=None), user_agent: Optional[str] = Header(default=None)):
    from schemas import Apievent  # type: ignore

    # Resolve project by slug
    proj = db["project"].find_one({"slug": event.project_slug})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    api_key_id = None
    if event.api_key:
        key_doc = db["apikey"].find_one({"key": event.api_key, "project_id": str(proj["_id"]) , "active": True})
        if key_doc:
            api_key_id = str(key_doc["_id"])        

    ip = event.ip or (x_forwarded_for.split(",")[0].strip() if x_forwarded_for else None)
    ua = event.user_agent or user_agent

    doc = Apievent(
        project_id=str(proj["_id"]),
        api_key_id=api_key_id,
        method=event.method,
        path=event.path,
        status=event.status,
        latency_ms=event.latency_ms,
        ip=ip,
        user_agent=ua,
        request_size=event.request_size,
        response_size=event.response_size,
        error_message=event.error_message,
    )
    eid = create_document("apievent", doc)
    return {"id": eid}

# Simple analytics
@app.get("/api/projects/{project_id}/stats")
def project_stats(project_id: str):
    try:
        _ = ObjectId(project_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid project id")

    # totals
    total = db["apievent"].count_documents({"project_id": project_id})

    # errors
    errors = db["apievent"].count_documents({"project_id": project_id, "status": {"$gte": 400}})

    # avg latency
    pipeline = [
        {"$match": {"project_id": project_id}},
        {"$group": {"_id": None, "avg": {"$avg": "$latency_ms"}}}
    ]
    agg = list(db["apievent"].aggregate(pipeline))
    avg_latency = agg[0]["avg"] if agg else 0

    # last 24h per hour counts
    from datetime import datetime, timedelta, timezone
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    hourly = list(db["apievent"].aggregate([
        {"$match": {"project_id": project_id, "created_at": {"$gte": since}}},
        {"$group": {
            "_id": {"$dateTrunc": {"date": "$created_at", "unit": "hour"}},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]))
    hourly_series = [{"t": h["_id"].isoformat(), "count": h["count"]} for h in hourly]

    return {
        "total": total,
        "errors": errors,
        "avg_latency": avg_latency,
        "hourly": hourly_series,
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

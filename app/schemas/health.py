from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    server_time: datetime
    message: str
    key: str | None = None


class AgentHealthRequest(BaseModel):
    text: str | None = None


class AgentHealthResponse(BaseModel):
    server_time: datetime
    healthy: bool
    message: str
    agent_response: str | None = None
    raw: dict | None = None

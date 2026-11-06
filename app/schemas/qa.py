from datetime import datetime

from pydantic import BaseModel, Field


class DashboardKpis(BaseModel):
    test_cases: int = Field(alias="testCases")
    executions_today: int = Field(alias="executionsToday")
    pass_rate: float = Field(alias="passRate")
    open_defects: int = Field(alias="openDefects")


class TrendPoint(BaseModel):
    date: str
    passed: int
    failed: int


class ReleaseReadiness(BaseModel):
    score: int
    status: str


class RecentExecution(BaseModel):
    id: str
    build: str
    branch: str
    environment: str
    status: str
    started_at: datetime = Field(alias="startedAt")


class DashboardResponse(BaseModel):
    generated_at: datetime = Field(alias="generatedAt")
    kpis: DashboardKpis
    trend: list[TrendPoint]
    release_readiness: ReleaseReadiness = Field(alias="releaseReadiness")
    recent_executions: list[RecentExecution] = Field(alias="recentExecutions")


class ChartDataResponse(BaseModel):
    generated_at: datetime = Field(alias="generatedAt")
    trend: list[TrendPoint]


class TestCase(BaseModel):
    id: str
    name: str
    suite: str
    category: str
    status: str
    duration_seconds: int = Field(alias="durationSeconds")
    environment: str
    updated_at: datetime = Field(alias="updatedAt")
    failure_reason: str | None = Field(alias="failureReason")
    logs: list[str]
    screenshot_available: bool = Field(alias="screenshotAvailable")
    test_data_reference: str = Field(alias="testDataReference")


class TestCaseListResponse(BaseModel):
    items: list[TestCase]
    total: int


class TestCaseResponse(BaseModel):
    test_case: TestCase = Field(alias="testCase")

from fastapi import APIRouter, Depends, HTTPException, Query

from ..qa_dependencies import get_current_user, require_roles
from ...core.keycloak import User
from ...schemas.qa import (
    ChartDataResponse,
    DashboardResponse,
    TestCaseListResponse,
    TestCaseResponse,
)
from ...services import qa as qa_service

router = APIRouter(prefix="/api/qa", tags=["QA mock data"])


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    _: User = Depends(
        require_roles("ADMIN", "QA_MANAGER", "QA_ENGINEER", "DEVELOPER", "VIEWER")
    ),
) -> dict:
    return qa_service.get_dashboard()


@router.get("/chart-data", response_model=ChartDataResponse)
def chart_data(
    _: User = Depends(
        require_roles("ADMIN", "QA_MANAGER", "QA_ENGINEER", "DEVELOPER", "VIEWER")
    ),
) -> dict:
    """Return chart-ready trend data for the dashboard visualization."""
    return qa_service.get_chart_data()


@router.get("/test-cases", response_model=TestCaseListResponse)
def list_test_cases(
    status: str | None = Query(default=None),
    query: str = Query(default="", max_length=100),
    _: User = Depends(require_roles("ADMIN", "QA_MANAGER", "QA_ENGINEER", "DEVELOPER")),
) -> dict:
    if not qa_service.is_supported_test_status(status):
        raise HTTPException(status_code=400, detail="Unsupported test status.")
    return qa_service.list_test_cases(status, query)


@router.get("/test-cases/{case_id}", response_model=TestCaseResponse)
def get_test_case(
    case_id: str,
    _: User = Depends(require_roles("ADMIN", "QA_MANAGER", "QA_ENGINEER", "DEVELOPER")),
) -> dict:
    case = qa_service.find_test_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Test case not found.")
    return {"testCase": case}

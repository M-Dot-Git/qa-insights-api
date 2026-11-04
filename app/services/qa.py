from ..dummy_data.qa import STATUSES, TEST_CASES, make_chart_data, make_dashboard_data


def get_dashboard() -> dict:
    return make_dashboard_data()


def get_chart_data() -> dict:
    return make_chart_data()


def list_test_cases(status: str | None, query: str) -> dict:
    normalized_query = query.strip().casefold()
    items = [
        case
        for case in TEST_CASES
        if (status is None or case["status"] == status)
        and (
            not normalized_query
            or normalized_query in case["name"].casefold()
            or normalized_query in case["suite"].casefold()
        )
    ]
    return {"items": items, "total": len(items)}


def find_test_case(case_id: str) -> dict | None:
    return next((case for case in TEST_CASES if case["id"] == case_id), None)


def is_supported_test_status(status: str | None) -> bool:
    return status is None or status in STATUSES

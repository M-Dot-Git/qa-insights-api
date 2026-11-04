import random
from datetime import datetime, timedelta, timezone

RANDOM = random.SystemRandom()
STATUSES = ("Passed", "Failed", "Flaky", "Skipped")
CASE_DEFINITIONS = [
    ("Sign in with valid credentials", "Authentication", "Functional"),
    ("Reject an expired session", "Authentication", "Functional"),
    ("Create a test run", "Test Runs", "Functional"),
    ("Filter tests by status", "Test Explorer", "Functional"),
    ("Render dashboard metrics", "Dashboard", "Functional"),
    ("Load large execution history", "Performance", "Non-functional"),
    ("Complete report within SLA", "Performance", "Non-functional"),
    ("Validate account permissions", "Authorization", "Functional"),
    ("Export a release summary", "Reporting", "Functional"),
    ("Recover after API timeout", "Resilience", "Non-functional"),
    ("Display failure diagnostics", "Test Explorer", "Functional"),
    ("Search test metadata", "Test Explorer", "Functional"),
]


def _iso_time(minutes_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def _make_test_case(index: int, name: str, suite: str, category: str) -> dict:
    status = RANDOM.choice(STATUSES)
    return {
        "id": f"QA-{index:03}",
        "name": name,
        "suite": suite,
        "category": category,
        "status": status,
        "durationSeconds": RANDOM.randint(1, 180),
        "environment": RANDOM.choice(["staging", "qa", "pre-production"]),
        "updatedAt": (
            datetime.now(timezone.utc) - timedelta(minutes=RANDOM.randint(1, 1440))
        ).isoformat(),
        "failureReason": "Expected response did not match the assertion."
        if status in {"Failed", "Flaky"}
        else None,
        "logs": [
            "Test setup completed.",
            "Request sent to mock service.",
            "Assertions completed.",
        ],
        "screenshotAvailable": RANDOM.choice([True, False]),
        "testDataReference": f"fixture-{index:03}",
    }


TEST_CASES = [
    _make_test_case(index, name, suite, category)
    for index, (name, suite, category) in enumerate(CASE_DEFINITIONS, start=1)
]


def make_dashboard_data() -> dict:
    total_tests = RANDOM.randint(280, 520)
    pass_rate = round(RANDOM.uniform(84.0, 99.5), 1)
    trend = [
        {
            "date": (datetime.now(timezone.utc) - timedelta(days=6 - day))
            .date()
            .isoformat(),
            "passed": RANDOM.randint(90, 220),
            "failed": RANDOM.randint(2, 35),
        }
        for day in range(7)
    ]
    score = max(0, min(100, round(pass_rate - RANDOM.randint(0, 14))))
    readiness = "Ready" if score >= 90 else "At risk" if score >= 75 else "Blocked"
    executions = [
        {
            "id": f"RUN-{RANDOM.randint(10000, 99999)}",
            "build": f"build-{RANDOM.randint(100, 999)}",
            "branch": RANDOM.choice(["main", "release/2.4", "feature/qa-api"]),
            "environment": RANDOM.choice(["staging", "qa", "pre-production"]),
            "status": RANDOM.choice(["Passed", "Failed", "Flaky"]),
            "startedAt": _iso_time(RANDOM.randint(1, 1440)),
        }
        for _ in range(6)
    ]
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "kpis": {
            "testCases": total_tests,
            "executionsToday": RANDOM.randint(18, 110),
            "passRate": pass_rate,
            "openDefects": RANDOM.randint(0, 27),
        },
        "trend": trend,
        "releaseReadiness": {"score": score, "status": readiness},
        "recentExecutions": executions,
    }


def make_chart_data() -> dict:
    trend = [
        {
            "date": (datetime.now(timezone.utc) - timedelta(days=6 - day))
            .date()
            .isoformat(),
            "passed": RANDOM.randint(90, 220),
            "failed": RANDOM.randint(2, 35),
        }
        for day in range(7)
    ]
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "trend": trend,
    }

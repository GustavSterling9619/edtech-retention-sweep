from datetime import datetime, timezone

from edtech_sweep import SweepRequest, decide_sweep


def test_sweep_respects_each_edtech_retention_boundary() -> None:
    request = SweepRequest.model_validate(
        {
            "as_of": "2026-09-13T00:00:00Z",
            "records": [
                {
                    "kind": "course_delivery",
                    "record_id": "course-old",
                    "status": "completed",
                    "closed_at": "2025-09-01T00:00:00Z",
                    "object_keys": ["courses/course-old/roster.csv"],
                },
                {
                    "kind": "learner_deadline",
                    "record_id": "deadline-open",
                    "status": "open",
                    "object_keys": ["deadlines/deadline-open/submission.pdf"],
                },
                {
                    "kind": "educator_report",
                    "record_id": "report-old",
                    "status": "published",
                    "published_at": "2024-08-01T00:00:00Z",
                    "object_keys": ["reports/report-old.pdf"],
                },
                {
                    "kind": "course_delivery",
                    "record_id": "course-recent",
                    "status": "completed",
                    "closed_at": "2026-08-01T00:00:00Z",
                    "object_keys": ["courses/course-recent/roster.csv"],
                },
            ],
        }
    )

    result = decide_sweep(request)

    assert request.as_of == datetime(2026, 9, 13, tzinfo=timezone.utc)
    assert result.stale_record_ids == ["course-old", "report-old"]
    assert result.delete_keys == [
        "courses/course-old/roster.csv",
        "reports/report-old.pdf",
    ]
    assert result.retained_record_ids == ["deadline-open", "course-recent"]

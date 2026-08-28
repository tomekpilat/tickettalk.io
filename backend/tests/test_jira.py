from uuid import UUID

from app.jira import parse_jira_import
from app.models import Ticket

ROOM_ID = UUID("10000000-0000-0000-0000-000000000051")


def existing_ticket(key: str = "PAY-1") -> Ticket:
    return Ticket(
        id=UUID("20000000-0000-0000-0000-000000000051"),
        room_id=ROOM_ID,
        issue_key=key,
        summary="Existing ticket",
        story_points=3,
    )


def test_parses_quoted_commas_multiline_descriptions_and_estimates() -> None:
    content = (
        "Issue key,Summary,Issue Type,Description,Story Points\n"
        'PAY-2,"Retry checkout, safely",Bug,"First line\nSecond line",8\n'
    )

    preview = parse_jira_import(content, "error", [])

    assert preview.errors == []
    assert preview.source_count == preview.saved_count == 1
    assert preview.rows[0].issue_key == "PAY-2"
    assert preview.rows[0].summary == "Retry checkout, safely"
    assert preview.rows[0].description == "First line\nSecond line"
    assert preview.rows[0].story_points == 8


def test_parses_tsv_and_reports_a_missing_summary_header() -> None:
    tsv = "Issue key\tSummary\tIssue Type\nPAY-3\tTSV ticket\tTask\n"
    parsed = parse_jira_import(tsv, "error", [])
    missing = parse_jira_import("Issue key,Description\nPAY-3,No summary\n", "error", [])

    assert parsed.rows[0].summary == "TSV ticket"
    assert missing.errors[0].row_number == 1
    assert missing.errors[0].field == "headers"
    assert "Summary" in missing.errors[0].message


def test_duplicate_rows_and_invalid_values_identify_the_source_row() -> None:
    duplicates = parse_jira_import(
        "Issue key,Summary\nPAY-4,First\nPAY-4,Second\n", "error", []
    )
    invalid = parse_jira_import(
        "Issue key,Summary,Story Points\nPAY-5,Ticket,large\n", "error", []
    )

    assert duplicates.saved_count == 1
    assert duplicates.errors[0].row_number == 3
    assert "appears more than once" in duplicates.errors[0].message
    assert invalid.errors[0].row_number == 2
    assert invalid.errors[0].field == "Story Points"
    assert "Use a number" in invalid.errors[0].fix


def test_existing_keys_require_an_explicit_duplicate_behavior() -> None:
    content = "Issue key,Summary,Story Points\nPAY-1,Imported replacement,13\n"
    existing = [existing_ticket()]

    blocked = parse_jira_import(content, "error", existing)
    skipped = parse_jira_import(content, "skip", existing)
    replaced = parse_jira_import(content, "replace", existing)

    assert blocked.errors and blocked.saved_count == 0
    assert skipped.rows[0].action == "skip"
    assert skipped.skipped_count == 1 and skipped.saved_count == 0
    assert replaced.rows[0].action == "replace"
    assert replaced.rows[0].existing_ticket_id == existing[0].id
    assert replaced.rows[0].story_points == 13
    assert replaced.saved_count == 1

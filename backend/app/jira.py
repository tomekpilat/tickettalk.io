import csv
import re
from io import StringIO

from pydantic import ValidationError

from .models import (
    DuplicateBehavior,
    JiraImportError,
    JiraImportPreview,
    JiraImportRow,
    Ticket,
)

MAX_IMPORT_BYTES = 1_000_000
MAX_IMPORT_TICKETS = 500

HEADER_ALIASES = {
    "issuekey": "issue_key",
    "key": "issue_key",
    "summary": "summary",
    "issuetype": "issue_type",
    "type": "issue_type",
    "description": "description",
    "storypoints": "story_points",
    "storypointestimate": "story_points",
}


def _header_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").strip().lower())


def _error(row: int, field: str, message: str, fix: str) -> JiraImportError:
    return JiraImportError(row_number=row, field=field, message=message, fix=fix)


def _delimiter(content: str) -> str:
    first_line = content.lstrip("\ufeff").splitlines()[0] if content.splitlines() else ""
    return "\t" if first_line.count("\t") > first_line.count(",") else ","


def _parse_row(
    raw_row: dict[str | None, str | list[str] | None],
    header_map: dict[str, str | None],
    row_number: int,
) -> tuple[JiraImportRow | None, JiraImportError | None]:
    values = {
        mapped: str(raw_row.get(header) or "").strip()
        for header, mapped in header_map.items()
        if mapped
    }
    points_value = values.get("story_points", "")
    try:
        story_points = float(points_value) if points_value else None
    except ValueError:
        return None, _error(
            row_number,
            "Story Points",
            f'"{points_value}" is not a number.',
            "Use a number such as 3, 5, or 8, or leave the cell empty.",
        )

    try:
        return JiraImportRow(
            row_number=row_number,
            issue_key=values.get("issue_key") or None,
            summary=values.get("summary", ""),
            issue_type=values.get("issue_type") or "Story",
            description=values.get("description", ""),
            story_points=story_points,
        ), None
    except ValidationError as error:
        first_error = error.errors()[0]
        field = str(first_error.get("loc", ["row"])[-1]).replace("_", " ").title()
        return None, _error(
            row_number,
            field,
            first_error["msg"],
            f"Correct the {field.lower()} value on row {row_number}.",
        )


def _append_with_duplicate_policy(
    preview: JiraImportPreview,
    row: JiraImportRow,
    existing: Ticket | None,
    duplicate_behavior: DuplicateBehavior,
) -> None:
    if existing and duplicate_behavior == "error":
        preview.errors.append(
            _error(
                row.row_number,
                "Issue key",
                f"{row.issue_key} already exists in this room.",
                "Choose Skip existing or Replace existing before importing.",
            )
        )
        return
    if existing:
        row.action = "skip" if duplicate_behavior == "skip" else "replace"
        row.existing_ticket_id = existing.id
    if row.action == "skip":
        preview.skipped_count += 1
    else:
        preview.saved_count += 1
    preview.rows.append(row)


def parse_jira_import(
    content: str,
    duplicate_behavior: DuplicateBehavior,
    existing_tickets: list[Ticket],
) -> JiraImportPreview:
    preview = JiraImportPreview()
    if len(content.encode("utf-8")) > MAX_IMPORT_BYTES:
        preview.errors.append(
            _error(0, "file", "The import is larger than 1 MB.", "Split it into smaller files.")
        )
        return preview

    try:
        reader = csv.DictReader(StringIO(content.lstrip("\ufeff")), delimiter=_delimiter(content))
        raw_headers = reader.fieldnames or []
        header_map = {header: HEADER_ALIASES.get(_header_key(header)) for header in raw_headers}
        if "summary" not in header_map.values():
            preview.errors.append(
                _error(
                    1,
                    "headers",
                    "A Summary column is required.",
                    "Add a column named Summary to the first row.",
                )
            )
            return preview

        existing_by_key = {
            ticket.issue_key.casefold(): ticket for ticket in existing_tickets if ticket.issue_key
        }
        seen_keys: set[str] = set()

        for row_number, raw_row in enumerate(reader, start=2):
            if None in raw_row:
                preview.source_count += 1
                preview.errors.append(
                    _error(
                        row_number,
                        "row",
                        "This row has more values than the header.",
                        "Remove the extra value or quote text that contains a delimiter.",
                    )
                )
                continue
            if not any(str(value or "").strip() for value in raw_row.values()):
                continue
            preview.source_count += 1
            if preview.source_count > MAX_IMPORT_TICKETS:
                preview.errors.append(
                    _error(
                        row_number,
                        "file",
                        "The import contains more than 500 tickets.",
                        "Split it into batches of 500 or fewer tickets.",
                    )
                )
                break

            row, row_error = _parse_row(raw_row, header_map, row_number)
            if row_error:
                preview.errors.append(row_error)
                continue
            assert row is not None

            normalized_key = row.issue_key.casefold() if row.issue_key else None
            if normalized_key and normalized_key in seen_keys:
                preview.errors.append(
                    _error(
                        row_number,
                        "Issue key",
                        f"{row.issue_key} appears more than once in this import.",
                        "Keep one row for each Jira issue key.",
                    )
                )
                continue
            if normalized_key:
                seen_keys.add(normalized_key)

            existing = existing_by_key.get(normalized_key) if normalized_key else None
            _append_with_duplicate_policy(preview, row, existing, duplicate_behavior)
    except csv.Error as error:
        preview.errors.append(
            _error(0, "file", f"The file could not be parsed: {error}", "Check its CSV quoting.")
        )
    return preview


def preview_jira_rows(
    rows: list[JiraImportRow],
    duplicate_behavior: DuplicateBehavior,
    existing_tickets: list[Ticket],
) -> JiraImportPreview:
    preview = JiraImportPreview(source_count=len(rows))
    existing_by_key = {
        ticket.issue_key.casefold(): ticket for ticket in existing_tickets if ticket.issue_key
    }
    for row in rows:
        existing = existing_by_key.get(row.issue_key.casefold()) if row.issue_key else None
        _append_with_duplicate_policy(preview, row, existing, duplicate_behavior)
    return preview

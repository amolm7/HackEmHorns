"""Deterministic deliverable checks. Passing these is not a judgment of factual quality."""

import csv
import io
import re
from .contracts import digest, now, require
from .db import rows_for, get


def canonical_table(text):
    return [
        [cell.strip() for cell in row]
        for row in csv.reader(io.StringIO(text.strip()))
        if any(cell.strip() for cell in row)
    ]


def acceptance_for(workflow, task, requested=None):
    requested = requested or {}
    count = re.search(r"\b(\d+)[- ]slide\b", task, re.I)
    criteria = {
        "slide_count": requested.get("slide_count")
        or (int(count.group(1)) if count else 5),
        "required_sections": requested.get(
            "required_sections", ["Recommendation", "Risks", "Next steps"]
        ),
        "min_document_words": requested.get("min_document_words", 40),
    }
    require(
        all(
            isinstance(section, str) and any(char.isalpha() for char in section)
            for section in criteria["required_sections"]
        ),
        "Document section names must include letters.",
    )
    if workflow == "launch":
        require(3 <= criteria["slide_count"] <= 20, "Launch decks support 3–20 slides.")
    return criteria


def check(c, run):
    if not run.get("work_item_id"):
        return None
    item = get(c, "work_items", run["work_item_id"])
    criteria = item.get(
        "acceptance", acceptance_for(item.get("workflow"), item.get("task", ""))
    )
    actions = [
        a
        for a in rows_for(c, "actions", "run_id", run["id"])
        if a["run_id"] == run["id"] and a["status"] == "executed" and a.get("result")
    ]
    latest = {a["tool_id"]: a for a in actions}
    checks = []

    def record(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    for tool in run.get(
        "workflow_tools",
        item.get("required_tools", ["search_tickets", "search_docs", "create_draft"]),
    ):
        action = latest.get(tool)
        record(
            "deliverable:" + tool,
            action is not None,
            "Required tool produced a saved result."
            if action
            else "Missing required result: " + tool,
        )
        if not action:
            continue
        result, args = action["result"], action["arguments"]
        if tool == "create_slideshow":
            slides = result.get("slides", [])
            record(
                "slide_count",
                len(slides) == criteria["slide_count"],
                f"Expected {criteria['slide_count']} slides; received {len(slides)}.",
            )
            record(
                "slide_content",
                all(s.get("title", "").strip() and s.get("bullets") for s in slides),
                "Every slide needs a title and at least one point.",
            )
        elif tool == "create_document":
            body = result.get("body", "")
            headings = [
                re.sub(r"[\W\d_]+", " ", h.casefold()).strip()
                for h in re.findall(r"^#+\s+(.+)$", body, re.M)
            ]
            for section in criteria["required_sections"]:
                wanted = re.sub(r"[\W\d_]+", " ", section.casefold()).strip()
                record(
                    "section:" + section,
                    any(wanted in h for h in headings),
                    "Required document heading: " + section,
                )
            record(
                "document_length",
                len(body.split()) >= criteria["min_document_words"],
                f"Document requires at least {criteria['min_document_words']} words.",
            )
        elif tool == "analyze_data":
            source = item.get("source_table")
            if not source and item.get("task"):
                from .runtime.demo import table

                try:
                    source = table(item["task"], fallback=False)
                except Exception:
                    source = None
            record(
                "analysis_source",
                bool(source)
                and canonical_table(args.get("table", ""))
                == canonical_table(source or ""),
                "Analysis must use the original job CSV without substituting rows or columns.",
            )
            record(
                "analysis_rows",
                result.get("rows", 0) > 0,
                "Analysis must contain data rows.",
            )
        elif tool == "create_draft":
            record(
                "draft_ticket",
                result.get("ticket_id") == item.get("ticket", {}).get("id")
                and result.get("sent") is False,
                "Draft must belong to the assigned ticket and remain unsent.",
            )
    return {
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "checked_at": now(),
        "criteria_hash": digest(criteria),
        "manual_review_required": True,
        "limits": "Checks verify structure, source identity and required outputs. A manager must review accuracy, reasoning and compliance with prose rules.",
    }

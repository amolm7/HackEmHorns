"""Deterministic demo planner for the workspace tools. No language model is called.

Demo mode runs the real tools on a fixed template built from the task text so the product can be
shown without an API key. Live models write their own tool arguments instead.
"""

import re
import csv
from datetime import datetime, timedelta
from ..contracts import Error

SAMPLE_CSV = "month,revenue,signups\nJan,12400,310\nFeb,15800,402\nMar,14200,377\nApr,19600,515\nMay,22100,588\nJun,24800,640"
LEAD = re.compile(
    r"^\s*(please\s+)?(can you\s+)?(make|create|build|write|draft|generate|prepare|summari[sz]e|analy[sz]e|schedule|set up|book|arrange|plan|turn)\s+(me\s+)?"
    r"((a|an|the|this)\b)?\s*(\d+[- ]slide\s+)?(slideshow|slide deck|deck|presentation|document|doc|memo|brief|report|data)?\s*"
    r"((about|on|for|covering|of)\b)?\s*:?\s*",
    re.I,
)


def topic(task):
    text = (
        LEAD.sub("", task.strip().split("\n")[0], count=1).strip(" .:") or task.strip()
    )
    text = text[:80].strip()
    return text[:1].upper() + text[1:] if text else "Untitled"


def fragments(task):
    parts = re.split(r"[.;\n]| and |, ", task)
    clean = [p.strip(" -") for p in parts if len(p.strip(" -")) > 3]
    return clean[:12]


def outline(task, slide_count=None):
    wanted = re.search(r"(\d+)[- ]slide", task, re.I)
    count = min(max(slide_count or (int(wanted.group(1)) if wanted else 5), 3), 20)
    name, bits = topic(task), fragments(task)
    slides = [
        f"# {name}",
        "> A draft deck prepared in demo mode",
        "- Overview prepared in demo mode",
        f"- Request: {task.strip()[:140]}",
        "notes: Demo template. Switch to a live model for original slides.",
    ]
    middle = [
        "Why it matters",
        "Key points",
        "Options",
        "Risks and open questions",
        "Timeline",
        "Next steps",
    ]
    for i in range(count - 2):
        title = middle[i] if i < len(middle) else f"Detail {i + 1}"
        chunk = bits[i * 2 : i * 2 + 2] or ["Replace this with your own detail"]
        slides.append(f"# {title}")
        slides.extend(f"- {c[:140]}" for c in chunk)
    slides += [
        "# Next steps",
        "- Review and edit this draft",
        "- Switch to a live model for original content",
    ]
    return "\n".join(slides)


def document(task):
    name = topic(task)
    bits = fragments(task)
    lines = [
        f"# {name}",
        "",
        f"This draft was generated in demo mode from your request: {task.strip()[:300]}",
        "",
        "# Key points",
    ]
    lines += [f"- {b[:200]}" for b in bits[:5]] or ["- Add your key points here"]
    lines += [
        "",
        "# Next steps",
        "- Review and edit this draft.",
        "- Switch to a live model for original writing.",
    ]
    return name, "\n".join(lines)


def table(task, fallback=True):
    lines = task.replace("/", "\n").splitlines()
    groups, group, width = [], [], None
    for line in lines:
        cells = next(csv.reader([line]))
        if len(cells) >= 2 and (width is None or len(cells) == width):
            group.append(line.strip())
            width = len(cells)
        else:
            if len(group) >= 2:
                groups.append(group)
            group = [line.strip()] if len(cells) >= 2 else []
            width = len(cells) if group else None
    if len(group) >= 2:
        groups.append(group)
    if groups:
        return "\n".join(max(groups, key=len))[:4000]
    if not fallback:
        raise Error(
            "Include a CSV table in this job before running analysis in demo mode.",
            422,
            "invalid_request",
        )
    return SAMPLE_CSV



EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def meeting_args(task, today=None):
    """Read an obvious date, time, duration and attendees from the request; otherwise use stated defaults."""
    today = today or datetime.now()
    text = task.strip()
    low = text.lower()
    day = None
    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if iso:
        try:
            day = datetime(int(iso[1]), int(iso[2]), int(iso[3]))
        except ValueError:
            day = None
    if day is None and "tomorrow" in low:
        day = today + timedelta(days=1)
    if day is None:
        for index, name in enumerate(WEEKDAYS):
            if re.search(rf"\b{name}\b", low):
                ahead = (index - today.weekday()) % 7 or 7
                day = today + timedelta(days=ahead + (7 if "next " + name in low and ahead < 7 and (index - today.weekday()) % 7 == 0 else 0))
                break
    if day is None:
        day = today + timedelta(days=1)
        while day.weekday() > 4:
            day += timedelta(days=1)
    hour, minute = 10, 0
    clock = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", low) or re.search(r"\b([01]?\d|2[0-3]):(\d{2})\b", low)
    if clock:
        hour = int(clock[1]); minute = int(clock[2] or 0) if clock[2] and clock[2].isdigit() else 0
        if len(clock.groups()) >= 3 and clock[3]:
            hour = hour % 12 + (12 if clock[3] == "pm" else 0)
    minutes = 30
    length = re.search(r"\b(\d+)\s*[- ]?\s*(min|minute|minutes|hour|hours|hr|hrs)\b", low)
    if length:
        minutes = int(length[1]) * (60 if length[2].startswith("h") else 1)
        minutes = min(max(minutes, 5), 480)
    title = EMAIL.sub("", text.split("\n")[0])
    title = LEAD.sub("", title, count=1)
    title = re.sub(r"\b(\d+)\s*[- ]?\s*(min|minute|minutes|hour|hours|hr|hrs)\b", "", title, flags=re.I)
    title = re.sub(r"\b(next|this|tomorrow|on|at|with|for|and)\b.*$", "", title, flags=re.I).strip(" .,:-") or "Meeting"
    title = re.sub(r"^(a|an|the)\s+", "", title, flags=re.I).strip() or "Meeting"
    return {
        "title": title[:1].upper() + title[1:],
        "start": day.replace(hour=hour, minute=minute, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M"),
        "duration_minutes": str(minutes),
        "attendees": ", ".join(dict.fromkeys(EMAIL.findall(text))),
        "agenda": "Goal and context\nDiscussion\nDecisions and owners",
    }


def email_args(task):
    people = list(dict.fromkeys(EMAIL.findall(task)))
    cleaned = re.sub(r"\s+", " ", EMAIL.sub("", task)).strip()
    cleaned = re.sub(r"^\s*(please\s+)?(draft|write|compose|send)\s+(an?\s+)?(\w+\s+)?(email|message|note)\s*(to\s+)?(asking\s+(for\s+)?|about\s+|regarding\s+|saying\s+)?", "", cleaned, flags=re.I)
    subject = topic(cleaned) or "Quick note"
    return {
        "to": ", ".join(people),
        "subject": subject[:80],
        "body": "Hi,\n\nDemo draft from your request: " + task.strip()[:300] + "\n\nPlease review and edit before sending. Switch to a live model for original writing.\n\n[Your name]",
    }


def task_args(task):
    bits = fragments(task) or ["Review this request"]
    return {"title": topic(task), "tasks": "\n".join(f"- {b[:160]}" for b in bits[:8])}


def workspace_plan(task, names, strict=False, acceptance=None):
    """Return the tool calls demo mode makes for whichever workspace tools the agent has."""
    queue = []
    if "read_url" in names:
        urls = re.findall(r"https?://[^\s)>\]\"']+", task)
        if not urls:
            raise Error(
                "Demo mode reads links you include in the task. Add a web address, or choose a live model.",
                422,
                "invalid_request",
            )
        queue.append({"name": "read_url", "args": {"url": urls[0].rstrip(".,")}})
    if "analyze_data" in names:
        queue.append(
            {
                "name": "analyze_data",
                "args": {
                    "table": table(task, fallback=not strict),
                    "question": task[:500],
                },
            }
        )
    if "create_slideshow" in names:
        queue.append(
            {
                "name": "create_slideshow",
                "args": {
                    "title": topic(task),
                    "outline": outline(task, (acceptance or {}).get("slide_count")),
                },
            }
        )
    if "create_document" in names:
        title, body = document(task)
        if strict:
            sections = (acceptance or {}).get(
                "required_sections", ["Recommendation", "Risks", "Next steps"]
            )
            body += "\n\n" + "\n\n".join(
                "# "
                + section
                + "\nDemo template: review the provided inputs and company rules before making a decision. This section needs manager review; no external action has been taken."
                for section in sections
            )
        queue.append(
            {"name": "create_document", "args": {"title": title, "body": body}}
        )
    if "schedule_meeting" in names:
        queue.append({"name": "schedule_meeting", "args": meeting_args(task)})
    if "create_task_list" in names:
        queue.append({"name": "create_task_list", "args": task_args(task)})
    if "draft_email" in names:
        queue.append({"name": "draft_email", "args": email_args(task)})
    return queue

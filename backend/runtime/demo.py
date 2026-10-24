"""Deterministic demo planner for the workspace tools. No language model is called.

Demo mode runs the real tools on a fixed template built from the task text so the product can be
shown without an API key. Live models write their own tool arguments instead.
"""

import re
from ..contracts import Error

SAMPLE_CSV = "month,revenue,signups\nJan,12400,310\nFeb,15800,402\nMar,14200,377\nApr,19600,515\nMay,22100,588\nJun,24800,640"
LEAD = re.compile(
    r"^\s*(please\s+)?(can you\s+)?(make|create|build|write|draft|generate|prepare|summari[sz]e|analy[sz]e)\s+(me\s+)?"
    r"(a|an|the|this)?\s*(\d+[- ]slide\s+)?(slideshow|slide deck|deck|presentation|document|doc|memo|brief|report|data)?\s*"
    r"(about|on|for|covering|of)?\s*:?\s*",
    re.I,
)


def topic(task):
    text = LEAD.sub("", task.strip().split("\n")[0], count=1).strip(" .:") or task.strip()
    text = text[:80].strip()
    return text[:1].upper() + text[1:] if text else "Untitled"


def fragments(task):
    parts = re.split(r"[.;\n]| and |, ", task)
    clean = [p.strip(" -") for p in parts if len(p.strip(" -")) > 3]
    return clean[:12]


def outline(task):
    wanted = re.search(r"(\d+)[- ]slide", task, re.I)
    count = min(max(int(wanted.group(1)) if wanted else 5, 3), 8)
    name, bits = topic(task), fragments(task)
    slides = [f"# {name}", "- Overview prepared in demo mode", f"- Request: {task.strip()[:140]}"]
    middle = ["Why it matters", "Key points", "Options", "Risks and open questions", "Timeline", "Next steps"]
    for i in range(count - 2):
        title = middle[i] if i < len(middle) else f"Detail {i + 1}"
        chunk = bits[i * 2 : i * 2 + 2] or ["Replace this with your own detail"]
        slides.append(f"# {title}")
        slides.extend(f"- {c[:140]}" for c in chunk)
    slides += ["# Next steps", "- Review and edit this draft", "- Switch to a live model for original content"]
    return "\n".join(slides)


def document(task):
    name = topic(task)
    bits = fragments(task)
    lines = [f"# {name}", "", f"This draft was generated in demo mode from your request: {task.strip()[:300]}", "", "# Key points"]
    lines += [f"- {b[:200]}" for b in bits[:5]] or ["- Add your key points here"]
    lines += ["", "# Next steps", "- Review and edit this draft.", "- Switch to a live model for original writing."]
    return name, "\n".join(lines)


def table(task):
    lines = [ln for ln in task.replace("/", "\n").split("\n")]
    csvish = [ln.strip() for ln in lines if ln.count(",") >= 1]
    if len(csvish) >= 2:
        return "\n".join(csvish)[:4000]
    return SAMPLE_CSV


def workspace_plan(task, names):
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
        queue.append({"name": "analyze_data", "args": {"table": table(task), "question": task[:500]}})
    if "create_slideshow" in names:
        queue.append({"name": "create_slideshow", "args": {"title": topic(task), "outline": outline(task)}})
    if "create_document" in names:
        title, body = document(task)
        queue.append({"name": "create_document", "args": {"title": title, "body": body}})
    return queue

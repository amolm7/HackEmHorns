"""Deterministic checks that a requested deliverable was really saved.

A model's sentence "I saved the slideshow" is not evidence. Only an executed
tool action is. These helpers decide which deliverables a task asks for, keep
tool-call budget in reserve to save them, and verify they exist before a chat
run may report success. Passing is a structural check, not a quality judgment.
"""
import re

ARTIFACT_TOOLS = {
    "create_slideshow": "slideshow",
    "create_document": "document",
    "draft_email": "email draft",
    "schedule_meeting": "meeting invite",
    "create_task_list": "task list",
}
NOUNS = {
    "create_slideshow": r"\b(slides?|slide ?deck|slideshow|deck|presentation)\b",
    "create_document": r"\b(document|doc|brief|report|memo|one[- ]pager|write[- ]?up)\b",
    "draft_email": r"\be-?mails?\b",
    "schedule_meeting": r"\b(meeting|invite|calendar event)\b",
    "create_task_list": r"\b(task list|tasks|to-?do|action items)\b",
}
VERBS = re.compile(
    r"\b(make|create|build|write|draft|prepare|produce|turn|put together|generate|save|schedule|set up|plan|compose|convert)\b",
    re.I,
)


def requested(task, held):
    """Artifact tools the task asks for that this agent actually holds."""
    if not VERBS.search(task or ""):
        return []
    return [
        tool for tool, pattern in NOUNS.items()
        if tool in held and re.search(pattern, task, re.I)
    ]


def reserve(task, held):
    """Tool calls that exploration must leave untouched so the deliverable can be saved."""
    wanted = requested(task, held)
    if wanted:
        return min(len(wanted), 3)
    return 1 if any(tool in held for tool in ARTIFACT_TOOLS) else 0


def saved(executed_tool_ids):
    return set(executed_tool_ids) & set(ARTIFACT_TOOLS)


def missing(task, held, executed_tool_ids):
    """Requested deliverables with no executed save action."""
    done = set(executed_tool_ids)
    return [tool for tool in requested(task, held) if tool not in done]


def labels(tools):
    return ", ".join(ARTIFACT_TOOLS[t] for t in tools)

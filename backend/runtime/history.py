"""Keep conversation history inside the model's input budget without breaking its protocol."""
import copy
import json

SHORT = 1200
LONG = 6000


def size(contents):
    return len(json.dumps(contents))


def _shrink(part, limit):
    resp = part["functionResponse"].get("response")
    text = json.dumps(resp)
    if len(text) > limit:
        part["functionResponse"]["response"] = {
            "compacted": True,
            "note": "This earlier tool result was shortened to save space. Its beginning is kept below.",
            "excerpt": text[:limit],
        }
        return True
    return False


def compact(contents, budget=90000, keep_recent=2):
    """Shorten old tool results, oldest first, until history fits.

    Messages, roles and function call/response IDs stay intact, so provider
    history remains valid. Returns the original list when it already fits."""
    if size(contents) <= budget:
        return contents
    out = copy.deepcopy(contents)
    holders = [i for i, m in enumerate(out) if any("functionResponse" in p for p in m.get("parts", []))]
    for group, limit in ((holders[:-keep_recent] if keep_recent else holders, SHORT), (holders, LONG)):
        for i in group:
            for part in out[i].get("parts", []):
                if "functionResponse" in part:
                    _shrink(part, limit)
            if size(out) <= budget:
                return out
    return out

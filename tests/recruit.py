"""Test helper: drive the internal recruiter service directly.

The public chat-style recruiter endpoints were removed (agents are created through
POST /agents/quick-create). These helpers keep the proposal tests focused on the
service rules that quick-create still relies on."""
from backend.db import get
from backend import recruiter


def propose(app, data, user="pavan", conversation_id=None):
    """Create or revise a proposal. Returns (conversation_id, result)."""
    with app.db.transaction(True) as c:
        actor = get(c, "users", user)
        conv_id = conversation_id or recruiter.conversation(c, actor)["id"]
        return conv_id, recruiter.message(c, app, actor, conv_id, data)

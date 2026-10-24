"""Durable task conversations, separate from recruiter setup conversations."""
from ..contracts import *
from ..db import *


def create(c, actor, agent, id=None):
    roles(actor, "admin", "manager", "builder", "member")
    visible_agent(actor, agent)
    require(agent["status"] == "active", "Agent is not active.", 409)
    conv = put(c, "agent_conversations", {
        "id": id or uid(), "org_id": actor["org_id"], "agent_id": agent["id"],
        "actor_id": actor["id"], "last_run_id": None, "created_at": now(),
    })
    audit(c, actor, "conversation.created", conv["id"], {"agent_id": agent["id"]})
    return conv


def list_for(c, actor, agent):
    visible_agent(actor, agent)
    return [x for x in all_rows(c, "agent_conversations") if x["org_id"] == actor["org_id"] and x["agent_id"] == agent["id"] and x["actor_id"] == actor["id"]]


def attach(c, actor, agent, data, run_id):
    earlier = get(c, "runs", data["follow_up_of"]) if data.get("follow_up_of") else None
    if earlier:
        in_org(actor, earlier)
        require(earlier["agent_id"] == agent["id"], "Follow-ups must stay with the same agent.")
        require(earlier["actor_id"] == actor["id"], "This conversation belongs to another user.", 403)
    conv_id = data.get("conversation_id") or (earlier.get("conversation_id", earlier.get("thread_id", earlier["id"])) if earlier else None)
    if conv_id:
        matches = [x for x in all_rows(c, "agent_conversations") if x["id"] == conv_id]
        if not matches and earlier and conv_id == earlier.get("thread_id", earlier["id"]):
            conv = create(c, actor, agent, conv_id)
            conv["last_run_id"] = earlier["id"]
        else:
            conv = get(c, "agent_conversations", conv_id)
        in_org(actor, conv)
        require(conv["agent_id"] == agent["id"], "Conversation belongs to another agent.", 409)
        require(conv["actor_id"] == actor["id"], "This conversation belongs to another user.", 403)
        if earlier:
            require(conv["last_run_id"] == earlier["id"], "Continue from the latest message, or start a new conversation.", 409, "stale_conversation")
        elif conv["last_run_id"]:
            earlier = get(c, "runs", conv["last_run_id"])
    else:
        conv = create(c, actor, agent, run_id)
    if earlier:
        require(earlier["status"] == "completed", "Wait for the previous task to finish, or start a new conversation.", 409)
        require(earlier["mode"] == data.get("mode", "demo"), "Use the same model, or start a new conversation.", 409, "conversation_model_conflict")
    conv["last_run_id"] = run_id
    put(c, "agent_conversations", conv)
    return conv, earlier

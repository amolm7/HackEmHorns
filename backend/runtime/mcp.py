"""Authenticated bundled MCP server, stateless Streamable HTTP JSON subset."""

import json
import re
import secrets
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ..contracts import *
from ..db import *
from ..registry import TOOLS, TICKETS, DOCS


def perform(db, name, args, execution_id):
    require(name in TOOLS, "Unknown sandbox tool.", 403)
    require(isinstance(args, dict), "Tool arguments must be an object.")
    with db.transaction(name == "create_draft") as c:
        if name == "create_draft":
            old = [r for r in all_rows(c, "tool_executions") if r["id"] == execution_id]
            if old:
                require(
                    old[0]["arguments_hash"] == digest(args),
                    "Execution ID payload conflict.",
                    409,
                )
                return old[0]["result"]
            ticket_id = string(args.get("ticket_id"), "ticket_id", 100)
            body = string(args.get("body"), "body", 4000)
            require(any(t["id"] == ticket_id for t in TICKETS), "Unknown ticket.")
            result = {
                "draft_id": uid(),
                "ticket_id": ticket_id,
                "body": body,
                "sent": False,
                "saved_at": now(),
            }
            put(
                c,
                "tool_executions",
                {
                    "id": execution_id,
                    "tool": name,
                    "arguments_hash": digest(args),
                    "result": result,
                    "created_at": now(),
                },
            )
            return result
        query = string(args.get("query"), "query", 1000).lower()
        terms = set(re.findall(r"[a-z0-9]+", query)) - {
            "the",
            "a",
            "an",
            "and",
            "to",
            "for",
            "our",
            "please",
            "ticket",
            "tickets",
            "docs",
            "help",
            "find",
            "show",
            "me",
            "what",
            "is",
        }
        source = TICKETS if name == "search_tickets" else DOCS
        ranked = sorted(
            [
                (len(terms & set(re.findall(r"[a-z0-9]+", json.dumps(x).lower()))), x)
                for x in source
            ],
            key=lambda p: p[0],
            reverse=True,
        )
        found = [item for score, item in ranked if score or not terms]
        return {
            ("tickets" if name == "search_tickets" else "documents"): found[:5],
            "sample_data": True,
        }


class MCP:
    def __init__(self, db):
        self.db = db
        self.token = secrets.token_urlsafe(32)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_error(405)

            def do_POST(self):
                if (
                    self.path != "/mcp"
                    or self.headers.get("Host")
                    != f"127.0.0.1:{self.server.server_port}"
                    or self.headers.get("Origin")
                    or self.headers.get("Authorization") != "Bearer " + owner.token
                ):
                    self.send_error(403)
                    return
                request = {}
                try:
                    n = int(self.headers.get("Content-Length", "0"))
                    require(0 < n <= 50000, "Invalid request size.")
                    request = json.loads(self.rfile.read(n))
                    require(isinstance(request, dict), "Expected JSON-RPC object.")
                    require(request.get("jsonrpc") == "2.0", "Expected JSON-RPC 2.0.")
                    method = request.get("method")
                    if method == "notifications/initialized":
                        self.send_response(202)
                        self.end_headers()
                        return
                    if method == "initialize":
                        result = {
                            "protocolVersion": "2025-03-26",
                            "capabilities": {"tools": {}},
                            "serverInfo": {
                                "name": "hire-agent-support-sandbox",
                                "version": "1.0.0",
                            },
                        }
                    elif method == "tools/list":
                        result = {
                            "tools": [
                                {k: v for k, v in t.items() if k != "risk"}
                                for t in TOOLS.values()
                            ]
                        }
                    elif method == "tools/call":
                        p = request.get("params", {})
                        try:
                            out = perform(
                                owner.db,
                                p.get("name"),
                                p.get("arguments", {}),
                                self.headers.get("X-Execution-ID", uid()),
                            )
                            result = {
                                "content": [{"type": "text", "text": json.dumps(out)}],
                                "isError": False,
                            }
                        except Error as e:
                            result = {
                                "content": [{"type": "text", "text": str(e)}],
                                "isError": True,
                            }
                    else:
                        raise Error("Unknown MCP method.")
                    response = {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": result,
                    }
                except (Error, ValueError, TypeError) as e:
                    response = {
                        "jsonrpc": "2.0",
                        "id": request.get("id") if isinstance(request, dict) else None,
                        "error": {"code": -32602, "message": str(e)},
                    }
                raw = json.dumps(response).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/mcp"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def rpc(self, method, params=None, execution_id="", notification=False):
        body = {"jsonrpc": "2.0", "method": method}
        if not notification:
            body["id"] = uid()
        if params is not None:
            body["params"] = params
        req = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Authorization": "Bearer " + self.token,
                "X-Execution-ID": execution_id,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                raw = r.read()
        except (urllib.error.URLError, TimeoutError):
            raise Error("Bundled MCP server is unavailable.", 502, "mcp_error")
        if notification:
            return None
        result = json.loads(raw)
        if "error" in result:
            raise Error(result["error"]["message"], 502, "mcp_error")
        return result["result"]

    def discover(self):
        self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "hire-agent-runtime", "version": "1"},
            },
        )
        self.rpc("notifications/initialized", notification=True)
        return self.rpc("tools/list")["tools"]

    def call(self, name, args, execution_id):
        result = self.rpc("tools/call", {"name": name, "arguments": args}, execution_id)
        require(
            not result.get("isError"), result["content"][0]["text"], 502, "tool_error"
        )
        return json.loads(result["content"][0]["text"])

    def close(self):
        self.server.shutdown()
        self.server.server_close()

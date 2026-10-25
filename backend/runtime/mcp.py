"""Authenticated bundled MCP server, stateless Streamable HTTP JSON subset."""

import csv
import html
import http.client
from html.parser import HTMLParser
import io
import ipaddress
import json
import math
import re
import secrets
import socket
import ssl
import threading
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import certifi
from ..contracts import *
from ..db import *
from ..registry import TOOLS, TICKETS, DOCS

# Tools that save something. They are idempotent per durable execution ID so crash recovery cannot save twice.
WRITE_TOOLS = {"create_draft", "create_slideshow", "create_document", "schedule_meeting", "draft_email", "create_task_list"}
MAX_PAGE_BYTES = 400_000


THEMES = ("aurora", "paper", "sunrise", "mono", "ocean", "dusk")
STAT = re.compile(r"^stat\s*:\s*(.+?)\s*\|\s*(.+)$", re.I)
QUOTE = re.compile(r"^quote\s*:\s*(.+?)(?:\s*\|\s*(.+))?$", re.I)
STEP = re.compile(r"^\d{1,2}[.)]\s+(\S.*)$")


def parse_outline(text):
    """Slides from a plain outline. '# ' starts a slide; '- ' adds a bullet; '> ' sets the lead
    statement; 'stat: 38% | label' adds a headline number; 'quote: words | who' adds a pull quote;
    '1. step' lines make a numbered sequence; 'notes: ' adds speaker notes. A title with nothing
    under it becomes a section divider."""
    slides, current = [], None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            current = {
                "title": line.lstrip("#").strip()[:120] or "Untitled",
                "bullets": [],
            }
            slides.append(current)
            continue
        if current is None:
            current = {"title": "Overview", "bullets": []}
            slides.append(current)
        if line.startswith(">"):
            current["lead"] = line.lstrip("> ").strip()[:200]
        elif line.lower().startswith("notes:"):
            note = line[6:].strip()[:400]
            current["notes"] = (current.get("notes", "") + " " + note).strip()[:600]
        elif STAT.match(line):
            value, label = STAT.match(line).groups()
            if len(current.setdefault("stats", [])) < 3:
                current["stats"].append({"value": value.strip()[:16], "label": label.strip()[:60]})
        elif QUOTE.match(line):
            text, by = QUOTE.match(line).groups()
            current["quote"] = {"text": text.strip()[:240], "by": (by or "").strip()[:80]}
        else:
            step = STEP.match(line)
            if step:
                current["ordered"] = True
            bullet = (step.group(1) if step else line.lstrip("-*\u2022 ")).strip()[:300]
            if bullet and len(current["bullets"]) < 8:
                current["bullets"].append(bullet)
    for index, slide in enumerate(slides):
        plain = not slide["bullets"] and not slide.get("stats") and not slide.get("quote")
        slide["layout"] = (
            "cover" if index == 0 and plain
            else "stats" if slide.get("stats")
            else "quote" if slide.get("quote") and not slide["bullets"]
            else "statement" if slide.get("lead") and not slide["bullets"]
            else "section" if plain and not slide.get("lead")
            else "steps" if slide.get("ordered") and slide["bullets"]
            else "split" if len(slide["bullets"]) >= 5
            else "list"
        )
    return slides[:30]


def clean_attendees(text):
    people = []
    for part in re.split(r"[,;\r\n]", text or ""):
        part = part.strip()
        if part and part.lower() not in [p.lower() for p in people]:
            people.append(part[:120])
    return people[:30]


def ics_escape(value):
    value = str(value).replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def meeting_result(args):
    try:
        start_text = string(args.get("start"), "start", 40).replace(" ", "T", 1)
        require("T" in start_text, "Start must include a date and time.", 422, "invalid_request")
        start = datetime.fromisoformat(start_text)
    except ValueError:
        raise Error("Start must be a date and time such as 2026-11-03T14:00.", 422, "invalid_request")
    raw = str(args.get("duration_minutes") or "30").strip()
    require(raw.isdigit() and 5 <= int(raw) <= 480, "Duration must be a number of minutes from 5 to 480.", 422, "invalid_request")
    minutes = int(raw)
    end = start + timedelta(minutes=minutes)
    title = string(args.get("title"), "title", 200)
    attendees = clean_attendees(args.get("attendees"))
    agenda = [x.strip().lstrip("-*\u2022 ").strip()[:200] for x in str(args.get("agenda") or "").splitlines() if x.strip()][:12]
    location = str(args.get("location") or "").strip()[:500]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid_value = uid()
    # Preserve explicit offsets in the artifact, and serialize them as UTC in the invite.
    def calendar_time(value):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return value.strftime("%Y%m%dT%H%M%S")

    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ORBIT//Meeting draft//EN", "METHOD:PUBLISH", "BEGIN:VEVENT",
        f"UID:{uid_value}@orbit.local", f"DTSTAMP:{stamp}",
        f"DTSTART:{calendar_time(start)}", f"DTEND:{calendar_time(end)}",
        f"SUMMARY:{ics_escape(title)}",
    ]
    if agenda:
        lines.append("DESCRIPTION:" + ics_escape("Agenda:\n" + "\n".join(f"- {x}" for x in agenda)))
    if location:
        lines.append(f"LOCATION:{ics_escape(location)}")
    for person in attendees:
        if re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+", person):
            lines.append(f"ATTENDEE;RSVP=TRUE:mailto:{person}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return {
        "kind": "meeting",
        "artifact_id": uid_value,
        "title": title,
        "start": start.isoformat(timespec="minutes"),
        "end": end.isoformat(timespec="minutes"),
        "duration_minutes": minutes,
        "attendees": attendees,
        "location": location,
        "agenda": agenda,
        "ics": "\r\n".join(lines) + "\r\n",
        "sent": False,
        "published": False,
        "saved_at": now(),
    }


def task_list_result(args):
    title = string(args.get("title"), "title", 200)
    tasks = []
    for line in str(args.get("tasks") or "").splitlines():
        line = line.strip().lstrip("-*\u2022 ").strip()
        line = re.sub(r"^\[[ xX]?\]\s*", "", line)
        if not line:
            continue
        parts = [x.strip() for x in line.split("|")]
        tasks.append({"text": parts[0][:200], "owner": (parts[1] if len(parts) > 1 else "")[:80], "due": (parts[2] if len(parts) > 2 else "")[:40]})
    require(bool(tasks), "The task list needs at least one task.")
    return {
        "kind": "tasks",
        "artifact_id": uid(),
        "title": title,
        "tasks": tasks[:40],
        "task_count": len(tasks[:40]),
        "published": False,
        "saved_at": now(),
    }


def number(value):
    cleaned = value.strip().replace(",", "").replace("$", "").replace("%", "")
    try:
        parsed = float(cleaned)
    except ValueError:
        return None
    require(
        math.isfinite(parsed),
        "Table numbers must be finite; NaN and infinity are not supported.",
    )
    return parsed


def analyze_table(text, question=""):
    text = text.strip()
    require(bool(text), "Provide a table with a header row.")
    first = text.splitlines()[0]
    delimiter = (
        "\t"
        if "\t" in first and "," not in first
        else ";"
        if ";" in first and "," not in first
        else ","
    )
    rows = [
        r
        for r in csv.reader(io.StringIO(text), delimiter=delimiter)
        if any(c.strip() for c in r)
    ]
    require(len(rows) >= 2, "The table needs a header row and at least one data row.")
    require(len(rows[0]) <= 30, "Tables support at most 30 columns.")
    require(len(rows) <= 501, "Tables support at most 500 data rows.")
    header = [h.strip() or f"column {i + 1}" for i, h in enumerate(rows[0])]
    require(len(set(header)) == len(header), "Table column names must be unique.")
    require(
        all(len(r) <= len(header) for r in rows[1:]),
        "A data row has more cells than the header.",
    )
    body = [r + [""] * (len(header) - len(r)) for r in rows[1:]]
    columns, numeric, categories = [], {}, {}
    for i, name in enumerate(header):
        values = [r[i].strip() for r in body if r[i].strip()]
        nums = [number(v) for v in values]
        if values and all(n is not None for n in nums):
            total = sum(nums)
            require(
                math.isfinite(total), "Table totals exceed the supported numeric range."
            )
            columns.append({"name": name, "type": "number"})
            numeric[name] = {
                "count": len(nums),
                "sum": round(total, 2),
                "mean": round(total / len(nums), 2),
                "min": min(nums),
                "max": max(nums),
            }
        else:
            columns.append({"name": name, "type": "text"})
            counts = {}
            for v in values:
                counts[v] = counts.get(v, 0) + 1
            categories[name] = sorted(counts.items(), key=lambda kv: -kv[1])[:5]
    chart, highlights = None, []
    label_col = next((c["name"] for c in columns if c["type"] == "text"), None)
    value_col = next((c["name"] for c in columns if c["type"] == "number"), None)
    if value_col:
        vi = header.index(value_col)
        li = header.index(label_col) if label_col else None
        totals = {}
        for n, r in enumerate(body):
            value = number(r[vi]) if r[vi].strip() else None
            if value is None:
                continue
            label = (
                r[li].strip() if li is not None and r[li].strip() else f"Row {n + 1}"
            )
            totals[label] = round(totals.get(label, 0) + value, 2)
            require(
                math.isfinite(totals[label]),
                "Table group totals exceed the supported numeric range.",
            )
        points = [{"label": k, "value": v} for k, v in list(totals.items())[:12]]
        chart = {
            "type": "bar",
            "x": label_col or "Row",
            "y": value_col,
            "points": points,
        }
        if points:
            top = max(totals, key=totals.get)
            low = min(totals, key=totals.get)
            highlights.append(f"Highest {value_col}: {top} ({totals[top]:g})")
            if low != top:
                highlights.append(f"Lowest {value_col}: {low} ({totals[low]:g})")
            if len(totals) > len(points):
                highlights.append(
                    f"Chart shows the first {len(points)} of {len(totals)} groups; statistics include all rows."
                )
        highlights.append(
            f"Total {value_col}: {numeric[value_col]['sum']:g} across {numeric[value_col]['count']} rows"
        )
    return {
        "kind": "analysis",
        "rows": len(body),
        "columns": columns,
        "numeric": numeric,
        "categories": categories,
        "chart": chart,
        "highlights": highlights,
        "question": question[:500],
        "sample_data": False,
    }


class _PageText(HTMLParser):
    """Prefer article content and omit navigation, scripts and other page chrome."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.body = []
        self.article = []

    def handle_starttag(self, tag, attrs):
        if tag in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            return
        attrs = dict(attrs)
        classes = set(attrs.get("class", "").split())
        skip = (
            tag
            in {"script", "style", "noscript", "svg", "head", "nav", "footer", "aside"}
            or attrs.get("role") == "navigation"
            or bool(
                classes
                & {
                    "mw-editsection",
                    "vector-header",
                    "vector-page-toolbar",
                    "mw-jump-link",
                    "toc",
                    "reflist",
                    "navbox",
                }
            )
        )
        article = tag in {"main", "article"} or "mw-parser-output" in classes
        self.stack.append((tag, skip, article))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if any(item[1] for item in self.stack):
            return
        self.body.append(data)
        if any(item[2] for item in self.stack):
            self.article.append(data)

    def text(self):
        return re.sub(r"\s+", " ", " ".join(self.article or self.body)).strip()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def public_address(url):
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise Error("Invalid link or port.")
    require(parts.scheme in {"http", "https"}, "Only http and https links can be read.")
    require(
        bool(parts.hostname) and not parts.username and not parts.password,
        "Invalid link.",
    )
    require(port in {None, 80, 443}, "Only standard web ports can be read.")
    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(
                parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)
            )
        }
    except OSError:
        raise Error("That address could not be found.", 502, "tool_error")
    require(
        bool(addresses) and all(ipaddress.ip_address(a).is_global for a in addresses),
        "Links to private or local addresses are blocked.",
        403,
        "tool_denied",
    )
    return sorted(addresses, key=lambda address: ipaddress.ip_address(address).version)


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, address):
        super().__init__()
        self.address = address

    def http_open(self, request):
        def connect(host, **kwargs):
            connection = http.client.HTTPConnection(host, **kwargs)
            connection._create_connection = (
                lambda target, timeout, source_address=None: socket.create_connection(
                    (self.address, target[1]), timeout, source_address
                )
            )
            return connection

        return self.do_open(connect, request)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, address, context):
        super().__init__(context=context)
        self.address = address

    def https_open(self, request):
        def connect(host, **kwargs):
            connection = http.client.HTTPSConnection(host, **kwargs)
            # Keep original host for SNI and certificate checks; only the socket address is pinned.
            connection._create_connection = (
                lambda target, timeout, source_address=None: socket.create_connection(
                    (self.address, target[1]), timeout, source_address
                )
            )
            return connection

        return self.do_open(connect, request, context=self._context)


def read_page(url):
    for _ in range(4):
        addresses = public_address(url)
        address = addresses[0]
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _PinnedHTTPHandler(address),
            _PinnedHTTPSHandler(
                address, ssl.create_default_context(cafile=certifi.where())
            ),
            _NoRedirect,
        )
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "HireAnAgent/1.0 (+local)",
                "Accept": "text/html,text/plain",
            },
        )
        try:
            response = opener.open(request, timeout=8)
        except urllib.error.HTTPError as e:
            if e.code in {301, 302, 303, 307, 308} and e.headers.get("Location"):
                url = urljoin(url, e.headers["Location"])
                e.close()
                continue
            e.close()
            return {
                "kind": "page_error",
                "url": url,
                "error": f"The page returned HTTP {e.code}.",
                "http_status": e.code,
            }
        except (urllib.error.URLError, TimeoutError, OSError):
            return {
                "kind": "page_error",
                "url": url,
                "error": "The page could not be reached.",
            }
        with response:
            kind = response.headers.get_content_type()
            require(
                kind in {"text/html", "text/plain", "application/xhtml+xml"},
                "Only text pages can be read.",
                502,
                "tool_error",
            )
            raw = response.read(MAX_PAGE_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
        try:
            text = raw.decode(charset, "replace")
        except LookupError:
            text = raw.decode("utf-8", "replace")
        title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        if kind != "text/plain":
            parser = _PageText()
            parser.feed(text)
            text = parser.text()
        else:
            text = re.sub(r"\s+", " ", text).strip()
        return {
            "kind": "page",
            "url": url,
            "title": html.unescape(re.sub(r"\s+", " ", title.group(1))).strip()[:200]
            if title
            else url,
            "text": text[:6000],
            "truncated": len(text) > 6000 or len(raw) == MAX_PAGE_BYTES,
        }
    raise Error("Too many redirects.", 502, "tool_error")


def perform(db, name, args, execution_id):
    require(name in TOOLS, "Unknown sandbox tool.", 403)
    require(isinstance(args, dict), "Tool arguments must be an object.")
    schema = TOOLS[name]["inputSchema"]
    require(all(field in args for field in schema["required"]), "Missing required tool arguments.")
    for field, value in args.items():
        require(field in schema["properties"], "Unknown tool argument.")
        spec = schema["properties"][field]
        require(isinstance(value, str) and spec.get("minLength", 0) <= len(value) <= spec["maxLength"], f"Invalid {field}: expected text up to {spec['maxLength']} characters.")
    if name == "analyze_data":
        return analyze_table(
            string(args.get("table"), "table", 4000), str(args.get("question") or "")
        )
    if name == "read_url":
        # Network access happens outside any database transaction.
        return {**read_page(string(args.get("url"), "url", 2000)), "fetched_at": now()}
    with db.transaction(name in WRITE_TOOLS) as c:
        if name in WRITE_TOOLS:
            old = [r for r in all_rows(c, "tool_executions") if r["id"] == execution_id]
            if old:
                require(
                    old[0]["arguments_hash"] == digest(args),
                    "Execution ID payload conflict.",
                    409,
                )
                return old[0]["result"]
            if name == "create_draft":
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
            elif name == "create_slideshow":
                title = string(args.get("title"), "title", 200)
                slides = parse_outline(string(args.get("outline"), "outline", 4000))
                require(bool(slides), "The outline needs at least one slide.")
                theme = str(args.get("theme") or "aurora").strip().lower()
                result = {
                    "kind": "slideshow",
                    "artifact_id": uid(),
                    "title": title,
                    "theme": theme if theme in THEMES else "aurora",
                    "slides": slides,
                    "slide_count": len(slides),
                    "published": False,
                    "saved_at": now(),
                }
            elif name == "schedule_meeting":
                result = meeting_result(args)
            elif name == "create_task_list":
                result = task_list_result(args)
            elif name == "draft_email":
                result = {
                    "kind": "email",
                    "artifact_id": uid(),
                    "to": [x for x in clean_attendees(args.get("to"))],
                    "subject": string(args.get("subject"), "subject", 200),
                    "body": string(args.get("body"), "body", 4000),
                    "sent": False,
                    "saved_at": now(),
                }
            else:
                title = string(args.get("title"), "title", 200)
                body = string(args.get("body"), "body", 40000)
                result = {
                    "kind": "document",
                    "artifact_id": uid(),
                    "title": title,
                    "body": body,
                    "word_count": len(body.split()),
                    "published": False,
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
        if name == "search_tickets" and any(t["id"].lower() == query for t in TICKETS):
            return {
                "tickets": [t for t in TICKETS if t["id"].lower() == query],
                "sample_data": True,
            }
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
                                for name, t in TOOLS.items() if not name.startswith("github_")
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
            with urllib.request.urlopen(req, timeout=32) as r:
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

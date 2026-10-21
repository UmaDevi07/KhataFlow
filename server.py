"""KhataFlow - a stateful Hinglish voice-ledger MCP server for Alexa+ (kirana udhaar book).

One process serves:
  /mcp          MCP server (Streamable HTTP) -> what Alexa+ connects to
  /             simulated Alexa+ web UI (mic + live ledger)
  /api/utter    simulator endpoint: Hinglish text -> tool call -> reply
  /api/ledger   current ledger for the UI

Storage: SQLite locally, Amazon DynamoDB when DDB_TABLE is set.
Optional: Amazon Bedrock understands commands the built-in parser misses.
"""
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

IST = ZoneInfo("Asia/Kolkata")
HERE = Path(__file__).parent

mcp = FastMCP(
    "KhataFlow",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8000)),
    stateless_http=True,
    json_response=True,
)

# ---------------------------------------------------------------- storage


class SqliteStore:
    def __init__(self, path):
        self.path = path
        with self._c() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS entries("
                "id TEXT PRIMARY KEY, customer TEXT, kind TEXT, amount REAL, note TEXT, ts TEXT)"
            )

    def _c(self):
        return sqlite3.connect(self.path)

    def add(self, e):
        with self._c() as c:
            c.execute(
                "INSERT INTO entries VALUES(?,?,?,?,?,?)",
                (e["id"], e["customer"], e["kind"], e["amount"], e["note"], e["ts"]),
            )

    def all(self):
        with self._c() as c:
            rows = c.execute("SELECT id,customer,kind,amount,note,ts FROM entries ORDER BY ts").fetchall()
        return [dict(zip(("id", "customer", "kind", "amount", "note", "ts"), r)) for r in rows]


class DynamoStore:
    """DynamoDB table with partition key `id` (String)."""

    def __init__(self, table):
        import boto3

        region = os.environ.get("AWS_REGION", "ap-south-1")
        self.t = boto3.resource("dynamodb", region_name=region).Table(table)

    def add(self, e):
        self.t.put_item(Item={**e, "amount": Decimal(str(e["amount"]))})

    def all(self):
        items, kw = [], {}
        while True:
            r = self.t.scan(**kw)
            items += r["Items"]
            if "LastEvaluatedKey" not in r:
                break
            kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]
        for i in items:
            i["amount"] = float(i["amount"])
        return sorted(items, key=lambda i: i["ts"])


STORE = (
    DynamoStore(os.environ["DDB_TABLE"])
    if os.environ.get("DDB_TABLE")
    else SqliteStore(os.environ.get("UDHAAR_DB", "udhaar.db"))
)


def entry(customer, kind, amount, note=""):
    return {
        "id": uuid.uuid4().hex,
        "customer": customer,
        "kind": kind,  # "credit" = udhaar given, "payment" = customer paid back
        "amount": float(amount),
        "note": note,
        "ts": datetime.now(IST).isoformat(timespec="seconds"),
    }


def balances():
    b = {}
    for e in STORE.all():
        b[e["customer"]] = b.get(e["customer"], 0) + (e["amount"] if e["kind"] == "credit" else -e["amount"])
    return b


def seed():
    """Demo opening balances (synthetic) so the first demo command has data."""
    if not STORE.all():
        for name, amt in [("Ravi", 500), ("Sita", 1200), ("Imran", 300), ("Meena", 800)]:
            STORE.add(entry(name, "credit", amt, "opening balance"))


seed()

# ---------------------------------------------------------------- context

SESSIONS = {}  # session_id -> last customer mentioned (the multi-turn memory)
NEED_NAME = {"ok": False, "speech": "Kiska naam? Customer ka naam bataiye."}


def resolve(customer, sid):
    """Use the named customer, or fall back to the last one in this conversation."""
    if customer and customer.strip():
        name = customer.strip().title()
        SESSIONS[sid] = name
        return name
    return SESSIONS.get(sid)


def money(x):
    return str(int(x)) if float(x).is_integer() else f"{x:.2f}"


# ---------------------------------------------------------------- MCP tools


@mcp.tool()
def add_udhaar(amount: float, customer: str = "", session_id: str = "default") -> dict:
    """Shopkeeper gave goods on credit: add amount to the customer's balance.
    If customer is empty, use the last customer from this conversation."""
    name = resolve(customer, session_id)
    if not name:
        return NEED_NAME
    if amount <= 0:
        return {"ok": False, "speech": "Amount sahi nahi hai."}
    STORE.add(entry(name, "credit", amount, "udhaar"))
    bal = balances().get(name, 0)
    return {
        "ok": True,
        "customer": name,
        "balance": bal,
        "speech": f"{name} ke khate mein {money(amount)} rupees jod diye. Ab {money(bal)} rupees baaki hai.",
    }


@mcp.tool()
def record_payment(amount: float, customer: str = "", mode: str = "cash", session_id: str = "default") -> dict:
    """Customer paid money back: reduce their balance. mode is cash or upi.
    If customer is empty, use the last customer from this conversation."""
    name = resolve(customer, session_id)
    if not name:
        return NEED_NAME
    bal = balances().get(name, 0)
    if amount <= 0 or amount > bal:
        return {
            "ok": False,
            "customer": name,
            "balance": bal,
            "speech": f"{name} ka sirf {money(bal)} rupees baaki hai. Itna payment record nahi ho sakta.",
        }
    STORE.add(entry(name, "payment", amount, mode))
    bal -= amount
    return {
        "ok": True,
        "customer": name,
        "balance": bal,
        "speech": f"{name} ka {money(amount)} rupees {mode} mein mil gaya. Ab {money(bal)} rupees baaki hai.",
    }


@mcp.tool()
def get_balance(customer: str = "", session_id: str = "default") -> dict:
    """How much a customer still owes. If customer is empty, use the last customer."""
    name = resolve(customer, session_id)
    if not name:
        return NEED_NAME
    b = balances()
    if name not in b:
        return {"ok": False, "speech": f"{name} ka koi record nahi mila."}
    return {"ok": True, "customer": name, "balance": b[name], "speech": f"{name} ka {money(b[name])} rupees baaki hai."}


@mcp.tool()
def customer_history(customer: str = "", n: int = 5, session_id: str = "default") -> dict:
    """Latest entries for a customer, newest first."""
    name = resolve(customer, session_id)
    if not name:
        return NEED_NAME
    rows = [e for e in STORE.all() if e["customer"] == name][-max(1, min(n, 10)):][::-1]
    if not rows:
        return {"ok": False, "speech": f"{name} ka koi record nahi mila."}
    parts = [
        f"{money(e['amount'])} {'udhaar' if e['kind'] == 'credit' else 'payment'}" for e in rows
    ]
    return {"ok": True, "customer": name, "entries": rows, "speech": f"{name} ke entries: " + ", ".join(parts) + "."}


@mcp.tool()
def summarize_book(session_id: str = "default") -> dict:
    """Total outstanding across all customers and how many customers owe money."""
    owing = {k: v for k, v in balances().items() if v > 0}
    total = sum(owing.values())
    return {
        "ok": True,
        "total": total,
        "customers_owing": len(owing),
        "speech": f"Total {money(total)} rupees baaki hai, {len(owing)} customers ka.",
    }


@mcp.tool()
def who_owes_most(n: int = 3, session_id: str = "default") -> dict:
    """The customers who owe the most, highest first."""
    top = sorted(((k, v) for k, v in balances().items() if v > 0), key=lambda kv: -kv[1])[: max(1, min(n, 10))]
    if not top:
        return {"ok": True, "top": [], "speech": "Kisi ka udhaar baaki nahi hai."}
    if top:
        SESSIONS[session_id] = top[0][0]
    return {
        "ok": True,
        "top": [{"customer": k, "balance": v} for k, v in top],
        "speech": "Sabse zyada baaki: " + ", ".join(f"{k} {money(v)} rupees" for k, v in top) + ".",
    }


TOOLS = {
    f.__name__: f
    for f in (add_udhaar, record_payment, get_balance, customer_history, summarize_book, who_owes_most)
}

# ---------------------------------------------------------------- simulator NLU

STOP = {"usme", "isme", "unka", "uska", "kitna", "aaj", "sabse", "mere", "ye", "wo", "sabka", "is", "us"}


def parse(text):
    """Rule-based Hinglish parser. Returns (tool, args) or None."""
    t = text.lower().strip()
    m_amt = re.search(r"(\d[\d,]*(?:\.\d+)?)", t)
    amount = float(m_amt.group(1).replace(",", "")) if m_amt else None
    m_name = re.search(r"\b([a-z]+) (?:ne|ko|ka|ki|ke)\b", t)
    name = m_name.group(1).title() if m_name and m_name.group(1) not in STOP else ""

    if re.search(r"sabse zyada|zyada udhaar|who owes|kis ka zyada|kiska zyada", t):
        return "who_owes_most", {}
    if re.search(r"summar|sabka|poori book|total", t):
        return "summarize_book", {}
    if re.search(r"history|entries|entry|saare|record bolo", t) and not amount:
        return "customer_history", {"customer": name}
    if not amount and re.search(r"kitna|baaki|balance|how much", t):
        return "get_balance", {"customer": name}
    if amount and re.search(r"udhaar|credit|liya|lia|le gaya|le gayi|khate mein", t):
        return "add_udhaar", {"amount": amount, "customer": name}
    if amount and re.search(r"kam kar|diye|diya|paid|payment|wapas|return|de gaya|de gayi|cut", t):
        mode = "upi" if re.search(r"upi|gpay|phonepe|paytm", t) else "cash"
        return "record_payment", {"amount": amount, "customer": name, "mode": mode}
    return None


def bedrock_parse(text):
    """Fallback understanding with Amazon Bedrock (only if BEDROCK_MODEL_ID is set)."""
    model = os.environ.get("BEDROCK_MODEL_ID")
    if not model:
        return None
    try:
        import boto3

        prompt = (
            "Map this Hinglish shopkeeper command to one tool. Tools: add_udhaar(amount, customer), "
            "record_payment(amount, customer, mode), get_balance(customer), customer_history(customer), "
            "summarize_book(), who_owes_most(). Reply ONLY with JSON like "
            '{"tool":"get_balance","args":{"customer":"Ravi"}}. Omit customer if no name is said. '
            "Command: " + text
        )
        client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        r = client.converse(
            modelId=model,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 200, "temperature": 0},
        )
        out = r["output"]["message"]["content"][0]["text"]
        j = json.loads(out[out.index("{"): out.rindex("}") + 1])
        if j.get("tool") in TOOLS:
            return j["tool"], j.get("args", {})
    except Exception:
        pass
    return None


# ---------------------------------------------------------------- web routes


def ledger_payload():
    by = {}
    for e in STORE.all():
        by.setdefault(e["customer"], []).append({k: e[k] for k in ("kind", "amount", "note", "ts")})
    customers = sorted(({"name": n, "balance": v} for n, v in balances().items()), key=lambda c: -c["balance"])
    return {"customers": customers, "entries": by}


@mcp.custom_route("/", methods=["GET"])
async def home(request: Request):
    return HTMLResponse((HERE / "ui.html").read_text(encoding="utf-8"))


@mcp.custom_route("/api/ledger", methods=["GET"])
async def api_ledger(request: Request):
    return JSONResponse(ledger_payload())


@mcp.custom_route("/api/utter", methods=["POST"])
async def api_utter(request: Request):
    body = await request.json()
    text = str(body.get("text", ""))[:300]
    sid = str(body.get("session", "default"))[:40]
    parsed = parse(text) or bedrock_parse(text)
    if not parsed:
        return JSONResponse({"reply": "Samajh nahi aaya, phir se boliye.", "tool": None, "ledger": ledger_payload()})
    tool, args = parsed
    args = {k: v for k, v in args.items() if v not in (None, "")}
    try:
        result = TOOLS[tool](session_id=sid, **args)
    except TypeError:
        return JSONResponse({"reply": "Samajh nahi aaya, phir se boliye.", "tool": None, "ledger": ledger_payload()})
    return JSONResponse(
        {
            "reply": result["speech"],
            "tool": tool,
            "args": args,
            "customer": result.get("customer"),
            "ledger": ledger_payload(),
        }
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")  # MCP endpoint: http://0.0.0.0:8000/mcp

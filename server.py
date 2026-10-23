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
PENDING = {}  # session_id -> (tool, args) waiting for a customer name
LANG = {}  # session_id -> language of the last message ("hi" = Hindi/Hinglish, "en" = English)


def both(hi, en):
    """Every tool answers in Hinglish (speech) and English (speech_en)."""
    return {"speech": hi, "speech_en": en}


NEED_NAME = {
    "ok": False,
    **both("Kiska naam? Customer ka naam bataiye.", "Whose account? Please tell me the customer's name."),
}


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
        return {"ok": False, **both("Amount sahi nahi hai.", "That amount isn't valid.")}
    STORE.add(entry(name, "credit", amount, "udhaar"))
    bal = balances().get(name, 0)
    return {
        "ok": True,
        "customer": name,
        "balance": bal,
        **both(
            f"{name} ke khate mein {money(amount)} rupees jod diye. Ab {money(bal)} rupees baaki hai.",
            f"Added {money(amount)} rupees to {name}'s account. Balance is now {money(bal)} rupees.",
        ),
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
            **both(
                f"{name} ka sirf {money(bal)} rupees baaki hai. Itna payment record nahi ho sakta.",
                f"{name} only owes {money(bal)} rupees. I can't record a larger payment.",
            ),
        }
    STORE.add(entry(name, "payment", amount, mode))
    bal -= amount
    return {
        "ok": True,
        "customer": name,
        "balance": bal,
        **both(
            f"{name} ka {money(amount)} rupees {mode} mein mil gaya. Ab {money(bal)} rupees baaki hai.",
            f"Recorded {money(amount)} rupees {mode} from {name}. Balance is now {money(bal)} rupees.",
        ),
    }


@mcp.tool()
def get_balance(customer: str = "", session_id: str = "default") -> dict:
    """How much a customer still owes. If customer is empty, use the last customer."""
    name = resolve(customer, session_id)
    if not name:
        return NEED_NAME
    b = balances()
    if name not in b:
        return {"ok": False, **both(f"{name} ka koi record nahi mila.", f"No record found for {name}.")}
    return {
        "ok": True,
        "customer": name,
        "balance": b[name],
        **both(f"{name} ka {money(b[name])} rupees baaki hai.", f"{name} owes {money(b[name])} rupees."),
    }


@mcp.tool()
def customer_history(customer: str = "", n: int = 5, session_id: str = "default") -> dict:
    """Latest entries for a customer, newest first."""
    name = resolve(customer, session_id)
    if not name:
        return NEED_NAME
    rows = [e for e in STORE.all() if e["customer"] == name][-max(1, min(n, 10)):][::-1]
    if not rows:
        return {"ok": False, **both(f"{name} ka koi record nahi mila.", f"No record found for {name}.")}
    hi = [f"{money(e['amount'])} {'udhaar' if e['kind'] == 'credit' else 'payment'}" for e in rows]
    en = [f"{money(e['amount'])} {'credit' if e['kind'] == 'credit' else 'payment'}" for e in rows]
    return {
        "ok": True,
        "customer": name,
        "entries": rows,
        **both(f"{name} ke entries: " + ", ".join(hi) + ".", f"{name}'s latest entries: " + ", ".join(en) + "."),
    }


@mcp.tool()
def summarize_book(session_id: str = "default") -> dict:
    """Total outstanding across all customers and how many customers owe money."""
    owing = {k: v for k, v in balances().items() if v > 0}
    total = sum(owing.values())
    return {
        "ok": True,
        "total": total,
        "customers_owing": len(owing),
        **both(
            f"Total {money(total)} rupees baaki hai, {len(owing)} customers ka.",
            f"Total outstanding is {money(total)} rupees across {len(owing)} customers.",
        ),
    }


@mcp.tool()
def who_owes_most(n: int = 3, session_id: str = "default") -> dict:
    """The customers who owe the most, highest first."""
    top = sorted(((k, v) for k, v in balances().items() if v > 0), key=lambda kv: -kv[1])[: max(1, min(n, 10))]
    if not top:
        return {"ok": True, "top": [], **both("Kisi ka udhaar baaki nahi hai.", "Nobody owes anything right now.")}
    SESSIONS[session_id] = top[0][0]
    return {
        "ok": True,
        "top": [{"customer": k, "balance": v} for k, v in top],
        **both(
            "Sabse zyada baaki: " + ", ".join(f"{k} {money(v)} rupees" for k, v in top) + ".",
            "Highest balances: " + ", ".join(f"{k} {money(v)} rupees" for k, v in top) + ".",
        ),
    }


@mcp.tool()
def who_paid_most(n: int = 3, session_id: str = "default") -> dict:
    """The customers who have paid back the most in total, highest first."""
    paid = {}
    for e in STORE.all():
        if e["kind"] == "payment":
            paid[e["customer"]] = paid.get(e["customer"], 0) + e["amount"]
    top = sorted(paid.items(), key=lambda kv: -kv[1])[: max(1, min(n, 10))]
    if not top:
        return {"ok": True, "top": [], **both("Abhi tak kisi ne payment nahi diya.", "No payments have been recorded yet.")}
    SESSIONS[session_id] = top[0][0]
    return {
        "ok": True,
        "top": [{"customer": k, "paid": v} for k, v in top],
        **both(
            "Sabse zyada payment: " + ", ".join(f"{k} {money(v)} rupees" for k, v in top) + ".",
            "Top payers: " + ", ".join(f"{k} {money(v)} rupees" for k, v in top) + ".",
        ),
    }


TOOLS = {
    f.__name__: f
    for f in (
        add_udhaar,
        record_payment,
        get_balance,
        customer_history,
        summarize_book,
        who_owes_most,
        who_paid_most,
    )
}

# ---------------------------------------------------------------- simulator NLU

STOP = {"usme", "isme", "unka", "uska", "kitna", "aaj", "sabse", "mere", "ye", "wo", "sabka", "is", "us"}

# words that are never a customer name (includes Chrome's spelling variants)
FILLER = set(
    """
ne neh nay nai ko koh ka kah kaa ki kee ke kay se me mein main
udhaar udhar uddhar credit debit liya lia liye diya diye dia dena lena de le gaya gayi
rupees rupee rupaye rupaya rs inr payment paid pay cash upi gpay phonepe paytm wapas return kam kar karo cut
add give gave given took taken new customer khata khate account ledger of to for from the a an and
hai hain ab abhi aur bhi aaj
kitna kitni baaki balance how much does owe owes history entries entry record bolo batao bata dikhao show what whats is
usme isme usne isne usko isko uska iska unka unko uske iske wo woh ye yeh mera meri mere mujhe
kiska kiski kiske kisko kya kab kaun
create naya nayi open opening
usmein ismein usmain ismain usmai ismai usmey ismey usse isse unmein unme
""".split()
) | STOP

# Chrome often spells Hinglish differently; normalise common variants before parsing
SPELLINGS = (
    ("jyada", "zyada"),
    ("zyaada", "zyada"),
    ("sabseh", "sabse"),
    ("sabsay", "sabse"),
    ("udhar", "udhaar"),
    ("kiskah", "kiska"),
    ("kiskaa", "kiska"),
)


# Hindi-origin words: if any appear (or the text is in Devanagari) we reply in Hindi/Hinglish
HI_WORDS = set(
    """
ne neh nay nai ko koh ka kah kaa ki kee ke kay hai hain kitna kitni baaki udhaar udhar diya diye dia liya lia liye
kam karo kar sabse sabseh sabsay zyada jyada zyaada kiska kiski kiske kisne kaun naam bataiye boliye batao bata
dikhao usme isme usne isne uska iska unka wo woh ye yeh mera meri mere mujhe aur mein se rupaye rupaya khata khate
naya nayi wapas poori sabka
""".split()
)


def detect_lang(text, sid):
    """'hi' for Hindi/Hinglish, 'en' for English. Bare one-word answers keep the previous language."""
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    words = re.findall(r"[a-z]+", text.lower())
    if any(w in HI_WORDS for w in words):
        return "hi"
    if len(words) >= 2:
        return "en"
    return LANG.get(sid, "en")


def find_name(t):
    """Customer name from a lowercase command, or ''."""
    m = re.search(r"\b([a-z]+) (?:ne|neh|nay|ko|koh|ka|kah|kaa|ki|kee|ke|kay)\b", t)
    if m and m.group(1) not in FILLER:
        return m.group(1).title()
    for w in re.findall(r"[a-z]+", t):  # fallback: first non-command word
        if w not in FILLER:
            return w.title()
    return ""


def bare_name(text):
    """User answered 'Kiska naam?' with just a name, e.g. 'gita'."""
    words = [w for w in re.findall(r"[a-z]+", text.lower()) if w not in FILLER]
    return " ".join(words[:2]).title() if 0 < len(words) <= 2 else ""


def parse(text):
    """Rule-based Hinglish parser. Returns (tool, args) or None."""
    t = text.lower().strip()
    for a, b in SPELLINGS:
        t = t.replace(a, b)
    m_amt = re.search(r"(\d[\d,]*(?:\.\d+)?)", t)
    amount = float(m_amt.group(1).replace(",", "")) if m_amt else None
    name = find_name(t)

    # must come before who_owes_most ("sabse zyada payment" is not "sabse zyada udhaar")
    if re.search(
        r"(highest|most|biggest|top|sabse zyada|zyada).*(payment|paid)"
        r"|(payment|paid).*(highest|most|biggest|zyada)",
        t,
    ):
        return "who_paid_most", {}
    if re.search(
        r"sabse zyada|zyada udhaar|who owes|kis ka zyada|kiska zyada"
        r"|(highest|most|biggest|top).*(owe|udhaar|baaki|due|balance)"
        r"|(owe|udhaar|baaki|due).*(highest|most|biggest)",
        t,
    ):
        return "who_owes_most", {}
    if re.search(r"summar|sabka|poori book|total", t):
        return "summarize_book", {}
    if re.search(r"history|entries|entry|saare|record bolo", t) and not amount:
        return "customer_history", {"customer": name}
    if not amount and re.search(r"kitna|baaki|balance|how much", t):
        return "get_balance", {"customer": name}
    # "create a ledger for gita of rupees 200" -> new customer with an opening udhaar
    if amount and re.search(r"create|naya|nayi|new|open", t) and re.search(r"ledger|khata|customer|account", t):
        return "add_udhaar", {"amount": amount, "customer": name}
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
            "summarize_book(), who_owes_most(), who_paid_most(). Reply ONLY with JSON like "
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
    lang = detect_lang(text, sid)
    LANG[sid] = lang
    not_understood = (
        "Sorry, I didn't catch that. Please try again." if lang == "en" else "Samajh nahi aaya, phir se boliye."
    )

    pend = PENDING.pop(sid, None)
    parsed = parse(text)
    if not parsed and pend:  # answer to "Kiska naam?"
        nm = bare_name(text)
        if nm:
            parsed = (pend[0], {**pend[1], "customer": nm})
    parsed = parsed or bedrock_parse(text)

    if not parsed:
        return JSONResponse({"reply": not_understood, "lang": lang, "tool": None, "ledger": ledger_payload()})
    tool, args = parsed
    args = {k: v for k, v in args.items() if v not in (None, "")}
    try:
        result = TOOLS[tool](session_id=sid, **args)
    except TypeError:
        return JSONResponse({"reply": not_understood, "lang": lang, "tool": None, "ledger": ledger_payload()})
    if result is NEED_NAME:
        PENDING[sid] = (tool, args)
    return JSONResponse(
        {
            "reply": result["speech_en"] if lang == "en" else result["speech"],
            "lang": lang,
            "tool": tool,
            "args": args,
            "customer": result.get("customer"),
            "ledger": ledger_payload(),
        }
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")  # MCP endpoint: http://0.0.0.0:8000/mcp

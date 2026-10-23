# KhataFlow
**A stateful Hinglish voice-ledger MCP server for Alexa+.**

**Live demo:** https://khataflow-2lc8.onrender.com/

"Khata" is the traditional Indian ledger book. "Flow" is the live update you see the moment a command is processed.
Kirana shopkeepers keep customer credit (**udhaar**) in paper notebooks. With KhataFlow, they just say it:

- "Ravi ne 200 rupees payment diya"
- "Ravi ka kitna baaki hai?" then "Usme se 200 kam karo, usne cash diya" (it remembers Ravi)
- "Sabse zyada udhaar kiska hai?"
- "Who has the highest payment?" (English works too)

Built for the **Build, Ship, Shape: Amazon Developer Hackathon** (Alexa+ track, Open Source mini challenge). The Alexa+ interface in this repo is **simulated**. All balances are synthetic.

## Features

- **Voice or text:** speak in Chrome (Web Speech API) or type
- **Hinglish and English:** replies match the language you used
- **Memory:** remembers the last customer in a conversation, so follow-ups need no name
- **New customers from one sentence:** "Rahul ko 500 ka udhaar diya", "add Priya 150 credit"
- **Asks when unsure:** if no name is given, it asks "Kiska naam?" and uses your next answer
- **Tolerates messy speech recognition:** handles spelling variants such as "neh", "kah", "usmein", "jyada"

## How it works
```
Voice -> Alexa+ (or the simulated Alexa+ page) -> MCP server (/mcp) -> tool -> ledger
```
- **MCP tools:** `add_udhaar`, `record_payment`, `get_balance`, `customer_history`, `summarize_book`, `who_owes_most`, `who_paid_most`
- **Endpoints:**
  - `/mcp`: the MCP server (Streamable HTTP) that Alexa+ connects to
  - `/`: simulated Alexa+ web UI with mic and live ledger
  - `/api/utter`: simulator endpoint (text in, tool call, reply out)
  - `/api/ledger`: current ledger for the UI
- **Context:** the server keeps the last customer per conversation.
- **Language:** every tool returns a Hinglish reply and an English reply, and the simulator picks one based on the language of your message.
- **Storage:** SQLite (`udhaar.db`, created at startup and seeded with synthetic balances). Balance = credits minus payments.
- **Parser:** a rule-based Hinglish parser with spelling normalisation.
- **Hosting:** Render (free tier).

## Try it
Open the live demo in Chrome (the first load after idle can take 30-60 seconds), then click **Speak** or type:
1. `Ravi ka kitna baaki hai?`
2. `Usme se 200 kam karo, usne cash diya`
3. `Rahul ko 500 ka udhaar diya`
4. `Who owes the most?`
5. `Who has the highest payment?` (after a payment has been recorded)
6. `Poori book ka summary do`

## Run locally
```
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -U -r requirements.txt
python server.py
```
- UI: http://localhost:8000/ (use Chrome for the mic; typing works anywhere)
- MCP endpoint: http://localhost:8000/mcp
- Test the MCP tools: `python client.py` (or `python client.py https://<your-url>/mcp`)

## Deploy on Render
1. Push this repo to GitHub.
2. In Render: **New > Web Service**, connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `python server.py` (the server reads Render's `PORT` variable)
5. Open the service URL, and use `https://<service-url>/mcp` as the MCP endpoint.

## Connect to Alexa+
Register your HTTPS `/mcp` URL using the official Alexa+ MCP guide linked on the hackathon Devpost page. The UI at `/` is the simulated Alexa+ experience and is labelled as simulated.

## Optional AWS support (not enabled in the live demo)

The code can use AWS services if you set environment variables:
- `DDB_TABLE`: store the ledger in DynamoDB instead of SQLite (partition key `id`, type String). Also set `AWS_REGION` and AWS credentials.
- `BEDROCK_MODEL_ID`: use Amazon Bedrock as a fallback parser for commands the built-in parser misses.

## Limitations

- Data lives in a SQLite file on Render's free tier, whose disk is ephemeral. It resets when the server

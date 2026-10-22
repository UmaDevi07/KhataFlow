# KhataFlow
A Stateful Hinglish Voice-Ledger MCP Server for Alexa+.
-------------------------------------------------------------------------------------------------------------------------------------------------------------------
"Khata" is the traditional Indian ledger book; "Flow" is the live update you see the moment a command is processed.
Kirana shopkeepers keep credit (udhaar) in notebooks. With KhataFlow, they just say it:

- "Ravi ne 200 rupees payment diya"
- "Ravi ka kitna baaki hai?" -> "Usme se 200 kam karo, usne cash diya" (remembers Ravi)
- "Sabse zyada udhaar kiska hai?"

**Live demo:** https://khataflow-2lc8.onrender.com/

Built for the Build, Ship, Shape: Amazon Developer Hackathon (Alexa+ track, Open Source mini challenge). Demo balances are synthetic.

## How it works
```
Voice -> Alexa+ (or the simulated Alexa+ page) -> MCP server (/mcp) -> tool -> ledger
```
- **MCP tools:** add_udhaar, record_payment, get_balance, customer_history, summarize_book, who_owes_most
- **Context:** the server remembers the last customer per conversation, so follow-ups need no name.
- **Storage:** in-memory ledger seeded with synthetic balances on start. Balance = credits - payments.
- **Hosting:** Render (free tier).
- **Simulated Alexa+ UI:** `ui.html` is served at `/`, with a mic (Chrome, Web Speech API). Balances flash green for payments and orange-red for credit, with a before/after rupee delta.

## Run locally
```
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -U -r requirements.txt
python server.py
```
- UI: http://localhost:8000/ (use Chrome for the mic; typing also works)
- MCP endpoint: http://localhost:8000/mcp (test with `python client.py`)

## Connect to Alexa+
Register your HTTPS `/mcp` URL using the official Alexa+ MCP guide linked on the hackathon Devpost page. The UI at `/` is the simulated Alexa+ experience and is labelled as simulated.

## Limits
- Data is in memory only. It resets when the server restarts or when Render's free tier sleeps.
- All visitors share the same demo ledger.
- The first load after idle can take 30-60 seconds.
- The parser handles digits ("200"), not spoken numbers ("do sau").
- No authentication. Demo only, do not store real customer data.

## License

MIT

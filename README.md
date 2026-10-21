# KhataFlow

A Stateful Hinglish Voice-Ledger MCP Server for Alexa+.
"Khata" is the traditional Indian ledger book; "Flow" is the live update you see the moment a command is processed.
Kirana shopkeepers keep credit (udhaar) in notebooks. Here they just say it:

- "Ravi ne 200 rupees payment diya"
- "Ravi ka kitna baaki hai?"  ->  "Usme se 200 kam karo, usne cash diya"  (remembers Ravi)
- "Sabse zyada udhaar kiska hai?"

Built for: Build, Ship, Shape: Amazon Developer Hackathon (Alexa+ track, AWS Builder + Open Source mini challenges).
Demo opening balances are synthetic.

## How it works
```
Voice -> Alexa+ (or the simulated Alexa+ page) -> MCP server (/mcp) -> tool -> ledger store
```
- MCP tools: add_udhaar, record_payment, get_balance, customer_history, summarize_book, who_owes_most
- Context: the server remembers the last customer per conversation, so follow-ups need no name.
- Storage: one `entries` table/collection (customer, kind credit|payment, amount, note, ts). Balance = credits - payments.
- AWS: DynamoDB for storage, App Runner for hosting, Bedrock as fallback understanding for commands the parser misses.
- Simulated Alexa+: `ui.html` served at `/`, glassmorphic dashboard with mic (Chrome, Web Speech API); balances flash mint green for payments and orange-red for credit, with a before/after rupee delta.

## Run locally
```
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -U -r requirements.txt
python server.py
```
- UI: http://localhost:8000/   (use Chrome for the mic; typing also works)
- MCP: http://localhost:8000/mcp  ->  `python client.py` to test it

## Deploy on AWS
1. DynamoDB: create table `udhaar-entries`, partition key `id` (String), on-demand capacity.
2. App Runner: source = this GitHub repo. Build: `pip install -r requirements.txt`. Start: `python server.py`. Port 8000.
3. Env vars: `DDB_TABLE=udhaar-entries`, `AWS_REGION=<your region>`, optional `BEDROCK_MODEL_ID=<id from Bedrock console>`.
4. Instance role permissions: `dynamodb:PutItem`, `dynamodb:Scan` on the table; `bedrock:InvokeModel` if using Bedrock.
5. Test: `python client.py https://<service-url>/mcp` and open `https://<service-url>/`.

## Connect to Alexa+
Register your HTTPS `/mcp` URL using the official Alexa+ MCP guide linked on the hackathon Devpost page.
The UI at `/` is the simulated Alexa+ experience; it is clearly labelled as simulated.

## Limits
- The built-in parser handles digits ("200"), not spoken numbers ("do sau"); Bedrock fallback may.
- No authentication: demo only, do not store real customer data.

## License
MIT

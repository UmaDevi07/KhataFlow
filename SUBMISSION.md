# KhataFlow submission guide

Official deadline: Fri 23 Oct 2026, 12:00 PM PDT = Sat 24 Oct, 12:30 AM IST.
Plan to submit by Fri 23 Oct afternoon IST. Do not leave it to midnight.
Page: https://amazonappdev2026.devpost.com/   Rules: https://amazonappdev2026.devpost.com/rules

## 3-day plan (from Wed 21 Oct)
- Wed 21: register on Devpost. Run locally (server.py, UI, client.py). Push to a public GitHub repo. Start the friction log.
- Thu 22: DynamoDB + App Runner deploy. Connect to Alexa+ using the official guide (if blocked, the simulator is your fallback). Rehearse the demo 3 times.
- Fri 23: record video (morning), upload, fill Devpost, submit by afternoon IST. Leave the rest as buffer.

## Demo video (aim for 90 seconds to 2 minutes; the rules only cap it at 3 minutes)
- 0:00 Start straight on the screen. Say: "Ravi ne 200 rupees payment diya." Ravi's card flashes mint green and the banner shows the balance drop (₹500 → ₹300). A credit command flashes orange-red and shows the rise. Judges need no Hindi to see it.
- 0:15 Multi-turn: "Ravi ka kitna baaki hai?" (reply 300). Then: "Usme se 100 kam karo, usne cash diya." (no name repeated, balance updates).
- 0:40 "Sabse zyada udhaar kiska hai?" and "Poori book ka summary do."
- 0:55 Architecture slide (15s): voice > Alexa+ > MCP server > DynamoDB, hosted on AWS App Runner. One entries table, balance = credits - payments. The server remembers the last customer per conversation.
- 1:10 Say once: "This is a simulated Alexa+ interface; the MCP server is the real backend."
- 1:20 Why Hinglish: shopkeepers say "baaki", "udhaar", "kam karo" mixed with English. Say that your parser and tools are built around those phrasings. Do NOT claim other software fails Indian accents unless you tested it.

## Devpost fields
1. Track: Alexa+. Mini challenges: AWS Builder, Open Source (check each challenge's criteria in the rules).
2. Description: problem, solution, how it's built, what's next.
3. Public GitHub repo with MIT LICENSE at root. No keys committed.
4. Public English demo video link, under 3 minutes.
5. Judge access: your public URL (UI at /, MCP at /mcp), free through judging.
6. Product feedback: honest notes about Alexa+/MCP docs and tools.
7. Disclose anything that existed before the hackathon.

## Friction log (up to 10% score bonus per Amazon's announcement)
Write each real problem as it happens. Do not invent entries; reviewers read these.
| Date | What I tried | What went wrong | What fixed it / what docs should say |
|------|--------------|-----------------|--------------------------------------|

## Final check
- Public URL works from your phone on mobile data.
- Repo is public, video plays logged out.
- Devpost shows "Submitted", not "Draft".

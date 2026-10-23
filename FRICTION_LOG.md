# Friction log

## 1. AWS account activation blocked my AWS deployment
- **Task:** Create an AWS account to host the backend (App Runner, DynamoDB).
- **Steps:** Signed up, then landed on the "Complete your account setup" page.
- **Expected:** A usable account, or a clear statement of what was still missing.
- **Actual:** The page listed several checklist items, a possible $1 verification hold for 3-5 days, and up to 24 hours for activation. It was unclear which step was pending.
- **Severity:** High (blocked the AWS deployment).
- **Workaround:** Deployed on Render instead.
- **Suggestion:** Show which checklist item is pending, with an estimated time, and say what works on the free plan meanwhile.

## 2. Hinglish speech recognition is inconsistent
- **Task:** Voice commands like "Gita ne 200 ka udhaar liya".
- **Actual:** Chrome's speech recognition wrote variants such as "neh", "kah", "usmein", so strict parsing failed.
- **Severity:** Medium.
- **Workaround:** Spelling normalisation and a looser parser.
- **Suggestion:** Better Hinglish support or custom vocabulary in speech recognition.

## 3. Free hosting resets local storage
- **Task:** Keep the ledger between sessions on Render's free tier.
- **Actual:** SQLite data resets when the server restarts or sleeps.
- **Severity:** Medium.
- **Workaround:** Seeded synthetic demo data and documented the limit.
- **Suggestion:** Move to DynamoDB (already supported in the code).

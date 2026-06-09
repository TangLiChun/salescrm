---
name: salescrm
description: Use when importing network-operator leads into Sales CRM, or when the user mentions Sales CRM, ASN contacts, peering outreach, or lead discovery on this VPS.
---

# Sales CRM (via the `salescrm` CLI)

Sales CRM runs on the same VPS at `$SALESCRM_URL` (default `http://127.0.0.1:8000`).
Talk to it through the **`salescrm` CLI** using the `bash` tool — it wraps the CRM Agent
API and reads `SALESCRM_URL` / `SALESCRM_TOKEN` from the environment. Do NOT use browser
login.

## Setup

1. CRM Web UI → **设置 → 自动化 → 外部 Agent API** → **重新生成** → copy the Token.
2. Export env vars (deploy.sh writes `${APP_DIR}/.reasonix-env` and sources it from
   `~/.bashrc`; otherwise set them yourself):

   ```bash
   export SALESCRM_URL=http://127.0.0.1:8000
   export SALESCRM_TOKEN=<paste-token>
   ```

3. The `salescrm` CLI is on `PATH` (deploy.sh symlinks it to `/usr/local/bin/salescrm`).

## Commands

| Command | When to use |
|---------|-------------|
| `salescrm health` | Verify the CRM + DB are up before a long scrape/import job. |
| `salescrm contacts [--status all\|sent\|unsent] [--q TEXT] [--limit N]` | Inspect existing contacts (dedupe checks, follow-up). |
| `salescrm import-leads <file.json\|-> [--source TAG]` | Import scraped leads. Input is a JSON array of contact rows, or `{"rows": [...]}`. Use `-` to read from stdin. |
| `salescrm discover "<query>" [--min-score N] [--auto-import]` | Run AI lead discovery for a natural-language query. |

## Lead row shape

Only `email` is required. All other fields are optional.

| Field | Accepted aliases | Notes |
|-------|-----------------|-------|
| `email` | — | Required; dedupe key |
| `org` | `organization`, `company`, `network_name` | Organization name |
| `name` | `contact_name`, `contact`, `fn` | Contact full name |
| `asn` | — | Integer or AS-string (`64500` or `"AS64500"`) |
| `roles` | — | Free text or comma-separated (e.g. `"NOC, Peering"`) |
| `linkedin` | `linkedin_url`, `linkedin_profile` | LinkedIn profile URL |
| `x` | `x_url`, `twitter`, `twitter_url` | X (Twitter) profile URL |
| `facebook` | `facebook_url` | Facebook profile URL |

`--source` defaults to `reasonix-agent`; override with `--source <tag>` to track the scrape origin.

Example:

```bash
cat > leads.json <<'JSON'
[
  {"email": "noc@example.net", "org": "Example Networks", "name": "Sam Lee", "asn": 64500, "roles": "NOC, Peering", "linkedin": "https://www.linkedin.com/in/samlee", "x": "https://x.com/samlee"}
]
JSON
salescrm import-leads leads.json --source my-scrape
```

`import-leads` returns `{"imported": N, "skipped": N, "duplicates": N, "filtered": N, "total": N}` (`total` is the contact count after import). Report the counts to the user.

## Typical workflow

1. `salescrm health` — confirm connectivity.
2. Scrape / produce lead rows as JSON using the fields above.
3. `echo "$ROWS_JSON" | salescrm import-leads -` (or pass a file path).
4. Report the returned counts (imported / skipped / duplicates / filtered / total) to the user.

Errors print to stderr with the HTTP status + server detail and a non-zero exit code.

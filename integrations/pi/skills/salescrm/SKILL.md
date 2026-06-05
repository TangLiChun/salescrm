---
name: salescrm-pi
description: Use when importing network-operator leads into Sales CRM from Pi, or when the user mentions Sales CRM, pi-agent, ASN contacts, or peering outreach pipelines.
---

# Sales CRM + Pi Agent

Sales CRM runs on the same VPS at `http://127.0.0.1:8000`. Pi talks to it via **Agent API** (Bearer token), not browser login.

## Setup

1. CRM Web UI → **系统设置 → 自动化 → Pi Agent API** → **重新生成** → copy Token
2. Export env vars (add to `~/.bashrc` or a `.env` file Pi loads):

```bash
export SALESCRM_URL=http://127.0.0.1:8000
export SALESCRM_TOKEN=<paste-token>
```

3. Install this package (from repo root on VPS):

```bash
pi install /opt/salescrm/integrations/pi
```

## Tools (extension)

| Tool | When to use |
|------|-------------|
| `salescrm_health` | Verify CRM is up before a long scrape job |
| `salescrm_list_contacts` | Check duplicates before import (`q=email@domain`) |
| `salescrm_import_leads` | Push structured rows after Playwright/bash scraping |
| `salescrm_discover_leads` | Use CRM's built-in AI discovery instead of custom scrape |

## Import row shape

Minimum: `{ "email": "abuse@example.net" }`

Recommended fields: `org`, `name`, `asn`, `roles`, `notes`, `source` (default `pi-agent`).

## Typical workflow

1. `salescrm_health`
2. Write/run a scraper (Playwright, curl, etc.) for target sites
3. `salescrm_list_contacts` with email domain to skip duplicates
4. `salescrm_import_leads` with cleaned JSON rows
5. Report counts: imported / skipped / duplicates / filtered

## Notes

- Import respects CRM blocklist/allowlist settings.
- Token binds to the default admin user (`default_admin_user` setting).
- Regenerating Token in CRM invalidates the old one immediately.

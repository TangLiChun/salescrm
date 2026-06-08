# Sales CRM × DeepSeek-Reasonix

Let [DeepSeek-Reasonix](https://github.com/esengine/DeepSeek-Reasonix) import scraped
leads into Sales CRM from the same VPS, via the `salescrm` helper CLI.

The CRM side is unchanged: Reasonix calls the Agent API (`/api/agent/*`, Bearer token)
through the `salescrm` CLI using its built-in `bash` tool. No MCP server.

## Automated (deploy.sh)

`sudo ./scripts/deploy.sh` will (unless `SKIP_REASONIX=1`):

- read the Agent Token and write `${APP_DIR}/.reasonix-env` (sourced from `~/.bashrc`);
- install Reasonix (`npm i -g reasonix`);
- symlink the CLI to `/usr/local/bin/salescrm`;
- ensure `${APP_DIR}/reasonix.toml` registers the skills path;
- verify with the Agent API health check.

## Manual

1. CRM Web UI → **设置 → 自动化 → 外部 Agent API** → **重新生成** → copy Token.
2. ```bash
   export SALESCRM_URL=http://127.0.0.1:8000
   export SALESCRM_TOKEN=<token>
   ```
3. Install Reasonix: `npm i -g reasonix` (or a prebuilt binary from GitHub releases).
4. Put the CLI on PATH: `ln -sf "$PWD/integrations/reasonix/bin/salescrm" /usr/local/bin/salescrm`.
5. Register the skill: add `[skills] paths = [".../integrations/reasonix/skills"]` to your
   `reasonix.toml` (see `reasonix.toml.example`).
6. Configure your DeepSeek model/credentials: `reasonix setup`.

## Verify

```bash
source ${APP_DIR}/.reasonix-env
salescrm health
```
Expected: `{"ok": true, "db": true, "schema": true, ...}`.

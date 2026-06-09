# 生产部署清单（商用就绪）

按本清单部署后，系统达到小团队商用基线：强制密钥、登录防暴破、安全响应头、HTTPS、每日备份、CI 全覆盖。

## 1. 必做：密钥与口令

```bash
cp .env.example .env
# 编辑 .env：
#   PI_INTERNAL_SECRET=$(openssl rand -hex 24)   # 必须 ≥16 字符强随机
#   POSTGRES_PASSWORD=$(openssl rand -hex 16)
docker compose up -d --build
```

- **PI_INTERNAL_SECRET**：内部 API（`/api/internal/pi/*`）与公网共用 8000 端口。留空或弱值（占位符、<16 字符）时内部 API 自动禁用、Pi 回退内置 Python loop——绝不会以可猜测的密钥运行。
- **管理员密码**：首次启动创建 `admin / admin123`。**登录后立即在「设置 → 修改密码」改掉**。使用默认密码登录时，`/api/login` 响应会带 `must_change_password: true`，启动日志也会告警。
- `session_secret` 首次启动自动生成强随机值（存于数据库），无需手工配置。

## 2. 必做：HTTPS 反向代理

应用本身只讲 HTTP。对外必须经 TLS 反代（Caddy 最省事）：

```caddyfile
crm.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

然后：

1. 系统设置中开启 **session_https_only=1**（会话 Cookie 加 Secure 标记，并自动启用 HSTS 响应头），重启 salescrm 容器。
2. 容器已带 `--proxy-headers`。让限速器拿到真实客户端 IP，需告知 uvicorn 信任的代理地址，在 `.env` 或 compose 中加：
   `FORWARDED_ALLOW_IPS=<反代的容器网段或 IP>`（同机 docker 部署通常是网桥网段，如 `172.16.0.0/12`）。不配置时按代理 IP 限速，仍然安全（按用户名维度生效）。
3. 防火墙只放行 80/443；8000 端口不直接对公网暴露。

## 3. 必做：备份

```bash
# 每日 03:00 备份，保留 14 天（KEEP_DAYS 可调）
crontab -e
0 3 * * * cd /path/to/salescrm && ./scripts/backup_db.sh >> backups/backup.log 2>&1
```

- 备份目录建议再同步到异地（rclone/对象存储）。
- 恢复演练：`./scripts/restore_db.sh backups/salescrm_<时间戳>.dump`，**上线前至少演练一次**。
- 页面上的「导出备份」只导出联系人 JSON，不能替代数据库备份。

## 4. 监控与日志

- 健康检查：`GET /health` 返回 `{"ok": true, "db": true, "schema": true}`。接入 Uptime Kuma / healthchecks.io 轮询。
- 容器自带 healthcheck，`docker compose ps` 可见状态；`restart: unless-stopped` 已配置。
- 日志：`docker compose logs -f salescrm pi-agent`。启动时会输出安全告警（默认密码、未开 HTTPS-only 等），上线前确认日志无 WARNING。

## 5. 升级流程

```bash
git pull
./scripts/backup_db.sh                 # 升级前先备份
docker compose up -d --build           # 重建镜像（含 pi-agent）
docker compose ps                      # 确认 healthy
```

数据库 schema 迁移在应用启动时自动执行（`init_db()`），无需手工步骤。

## 6. 安全基线（已内置）

| 防护 | 说明 |
|------|------|
| 登录限速 | 同 IP+用户名 5 分钟内 5 次失败 → 429 + Retry-After |
| 会话固定防护 | 登录成功时清空旧 session 再写入 |
| 内部 API 密钥强校验 | 弱/短密钥视为未配置（503），双端（Python+TS）一致 |
| 安全响应头 | nosniff / DENY frame / Referrer-Policy；HTTPS 模式自动加 HSTS |
| CSRF 缓解 | 会话 Cookie SameSite=Lax（Starlette 默认），写操作均为 JSON API |
| 密码存储 | PBKDF2-HMAC-SHA256，120k 迭代，随机盐 |
| 容器 | 双镜像均非 root 运行；postgres 不对外发布端口 |

## 7. 已知限制（商用前需知）

- **单实例架构**：登录限速与 Pi 线程锁均为进程内状态，scheduler/email sender 假定单副本。水平扩容前需把这些状态移到 Postgres/Redis。
- **会话无服务端吊销**：改密码后旧 Cookie 在过期前仍有效（Starlette 签名 Cookie 方案的固有特性）。如需立即吊销，须改造为服务端会话存储。
- **无按用户角色权限**：所有登录用户权限相同（数据按 user_id 隔离）。
- **邮件发送合规**：商用群发请确认 SMTP 服务商政策、退订机制与当地法规（如 CAN-SPAM/GDPR）由使用方自行保障。

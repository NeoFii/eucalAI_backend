# Eucal AI 部署文档

## 部署架构

三台服务器，服务间通过内网 IP 通信。

```
┌──────────────────────────────────────────────┐
│          前端节点 (2H2G) — Server A           │
│                                              │
│  ┌──────────────────┐  ┌──────────────────┐  │
│  │  eucal-admin     │  │ Frontend-zh      │  │
│  │  (管理后台)       │  │ (用户前端)        │  │
│  │  :3001           │  │ :3000            │  │
│  └──────────────────┘  └──────────────────┘  │
│  ┌──────────────────────────────────────────┐│
│  │  Nginx (:80/:443)                        ││
│  │  admin.domain → :3001                    ││
│  │  www.domain   → :3000                    ││
│  └──────────────────────────────────────────┘│
└──────────────────────────────────────────────┘
          │ 内网                    │ 内网
          ▼                        ▼
┌──────────────────────────────────────────────┐
│          后端节点 (2H4G) — Server B           │
│                                              │
│  ┌─────────┐  ┌─────────────┐               │
│  │  MySQL  │  │admin-service│               │
│  │  :3306  │  │    :8001    │               │
│  └─────────┘  ├─────────────┤               │
│  ┌─────────┐  │admin-worker │               │
│  │  Redis  │  └─────────────┘               │
│  │  :6379  │  ┌─────────────┐               │
│  └─────────┘  │user-service │               │
│               │    :8000    │               │
│               ├─────────────┤               │
│               │ user-worker │               │
│               └─────────────┘               │
└──────────────────────────────────────────────┘
          │ 内网
          ▼
┌──────────────────────────────────────────────┐
│          GPU 节点 — Server C                  │
│                                              │
│  ┌────────────────┐  ┌────────────────────┐  │
│  │ router-service │  │ inference-service  │  │
│  │     :8003      │  │      :8004         │  │
│  └────────────────┘  └────────────────────┘  │
└──────────────────────────────────────────────┘
```

### 内网 IP 约定

本文档使用以下占位符，部署时替换为实际内网 IP：

| 占位符 | 说明 |
|--------|------|
| `<FRONTEND_IP>` | 前端节点内网 IP |
| `<BACKEND_IP>` | 后端节点内网 IP |
| `<GPU_IP>` | GPU 节点内网 IP |

### 端口与防火墙规划

| 节点 | 监听端口 | 来源限制 |
|------|---------|---------|
| Server A | 80, 443 | 公网 |
| Server A | 3000, 3001 | 仅本机（Nginx 反代） |
| Server B | 8000 | 仅 `<FRONTEND_IP>` 和 `<GPU_IP>` |
| Server B | 8001 | 仅 `<FRONTEND_IP>` 和 `<GPU_IP>` |
| Server B | 3306 | 仅本机（不暴露） |
| Server B | 6379 | 仅本机（不暴露） |
| Server C | 8003 | 仅 `<FRONTEND_IP>` 和 `<BACKEND_IP>` |
| Server C | 8004 | 仅 `<BACKEND_IP>` 和 `<GPU_IP>` 自身 |

> 内网通信原则：MySQL/Redis 不暴露任何端口，admin/user 服务只对授信节点开放，所有跨节点通信走内网。

---

## 环境要求

| 节点 | CPU/内存 | Docker | 其他 |
|------|---------|--------|------|
| Server A (前端) | 2H2G | 20.10+ | - |
| Server B (后端) | 2H4G | 20.10+ | - |
| Server C (GPU) | 视模型而定 | 20.10+ | nvidia-container-toolkit, NVIDIA 驱动 |

通用：Docker Compose v2.0+、20GB+ 磁盘空间。

---

## 一、密钥准备（一次性）

在任意一台机器生成后，分发到三台服务器使用。所有服务必须使用相同的密钥才能互通。

```bash
echo "JWT_SECRET_KEY=$(openssl rand -hex 32)"
echo "INTERNAL_SECRET=$(openssl rand -hex 32)"
echo "PROVIDER_SECRET_MASTER_KEY=$(openssl rand -hex 32)"
echo "INFERENCE_SERVICE_SECRET=$(openssl rand -hex 16)"
echo "MYSQL_ROOT_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)"
```

把输出保存到密码管理器，后续每台服务器配置都会用到。

| 变量 | admin-service | user-service | router-service | inference-service |
|------|:---:|:---:|:---:|:---:|
| `JWT_SECRET_KEY` | * | * | | |
| `INTERNAL_SECRET` | * | * | * | * |
| `PROVIDER_SECRET_MASTER_KEY` | * | | | |
| `INFERENCE_SERVICE_SECRET` | | | * | * |

---

## 二、后端节点部署 (Server B, 2H4G)

### 2.1 准备目录

```bash
mkdir -p /srv/eucal && cd /srv/eucal
git clone git@github.com:NeoFii/eucalAI_backend.git backend
```

部署后目录：

```
/srv/eucal/backend/
├── infra/                    # MySQL + Redis
└── services/
    ├── admin-service/
    └── user-service/
```

### 2.2 启动 MySQL + Redis

```bash
cd /srv/eucal/backend/infra
cat > .env << EOF
MYSQL_ROOT_PASSWORD=<刚才生成的 MYSQL_ROOT_PASSWORD>
EOF

# 创建共享 Docker 网络（admin/user/MySQL/Redis 都用这个）
docker network create eucal_backend_network

docker compose up -d
docker compose logs -f mysql  # 等待 "ready for connections"，然后 Ctrl+C
```

> **MySQL 和 Redis 不暴露端口到宿主机**。后端服务通过 Docker 网络访问，外部节点（前端/GPU）也不需要直接连 MySQL/Redis。

### 2.3 配置 admin-service

```bash
cd /srv/eucal/backend/services/admin-service
cp .env.example .env
```

编辑 `.env`：

```bash
# 数据库 — 容器间用服务名
ADMIN_DATABASE_URL=mysql+aiomysql://root:<MYSQL_ROOT_PASSWORD>@mysql:3306/eucal_ai_admin

# 共享密钥
JWT_SECRET_KEY=<JWT_SECRET_KEY>
INTERNAL_SECRET=<INTERNAL_SECRET>
PROVIDER_SECRET_MASTER_KEY=<PROVIDER_SECRET_MASTER_KEY>

# Redis — 容器间用服务名
REDIS_URL=redis://redis:6379/0
ADMIN_QUEUE_REDIS_URL=redis://redis:6379/3

# 服务发现
USER_SERVICE_URL=http://user-service:8000          # 同节点用 Docker 服务名
ROUTER_SERVICE_URL=http://<GPU_IP>:8003            # 跨节点用内网 IP
INFERENCE_SERVICE_URL=http://<GPU_IP>:8004

# 安全
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
ALLOWED_HOSTS=https://admin.yourdomain.com
DEBUG=false
LOG_LEVEL=INFO
LOG_TO_FILE=true

# 首次部署时创建超级管理员
BOOTSTRAP_SUPERADMIN_ENABLED=true
BOOTSTRAP_SUPERADMIN_EMAIL=admin@yourdomain.com
BOOTSTRAP_SUPERADMIN_PASSWORD=<强密码>
BOOTSTRAP_SUPERADMIN_NAME=System Admin
```

修改 `docker-compose.yml`，把 `8001` 端口绑定到内网网卡 IP，避免暴露到公网：

```yaml
# services/admin-service/docker-compose.yml
ports:
  - "<BACKEND_IP>:8001:8001"   # 而不是默认的 "8001:8001"
```

> 替换 `<BACKEND_IP>` 为后端节点的内网 IP。这样只有同内网的节点能访问，公网无法访问。

### 2.4 配置 user-service

```bash
cd /srv/eucal/backend/services/user-service
cp .env.example .env
```

编辑 `.env`：

```bash
USER_DATABASE_URL=mysql+aiomysql://root:<MYSQL_ROOT_PASSWORD>@mysql:3306/eucal_ai_user

JWT_SECRET_KEY=<JWT_SECRET_KEY>
INTERNAL_SECRET=<INTERNAL_SECRET>

REDIS_URL=redis://redis:6379/0
USER_QUEUE_REDIS_URL=redis://redis:6379/1
CACHE_REDIS_URL=redis://redis:6379/2

ADMIN_SERVICE_URL=http://admin-service:8001        # 同节点用服务名

COOKIE_SECURE=true
COOKIE_SAMESITE=lax
ALLOWED_HOSTS=https://yourdomain.com
DEBUG=false
LOG_LEVEL=INFO
LOG_TO_FILE=true
```

同样修改端口绑定：

```yaml
# services/user-service/docker-compose.yml
ports:
  - "<BACKEND_IP>:8000:8000"
```

### 2.5 启动后端服务

```bash
# 数据库迁移
cd /srv/eucal/backend/services/admin-service
docker compose run --rm admin-service \
  alembic -c migrations/alembic.ini upgrade head

cd ../user-service
docker compose run --rm user-service \
  alembic -c migrations/alembic.ini upgrade head

# 启动
cd ../admin-service && docker compose up -d
cd ../user-service && docker compose up -d

# 验证
curl -s http://<BACKEND_IP>:8001/api/v1/health
curl -s http://<BACKEND_IP>:8000/api/v1/health
```

---

## 三、GPU 节点部署 (Server C)

### 3.1 准备 GPU 环境

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi  # 验证 Docker GPU 可用
```

### 3.2 部署 inference-service

```bash
mkdir -p /srv/eucal && cd /srv/eucal
git clone git@github.com:NeoFii/eucalAI_backend.git backend

cd backend/services/inference-service
cp .env.example .env
```

编辑 `.env`：

```bash
INFERENCE_SERVICE_SECRET=<INFERENCE_SERVICE_SECRET>
INTERNAL_SECRET=<INTERNAL_SECRET>
ADMIN_SERVICE_URL=http://<BACKEND_IP>:8001          # 内网 IP

CUDA_VISIBLE_DEVICES=0
GPU_CONCURRENCY_LIMIT=2

LOG_LEVEL=INFO
LOG_TO_FILE=true
ENV=production
```

修改端口绑定到内网：

```yaml
# services/inference-service/docker-compose.yml
ports:
  - "<GPU_IP>:8004:8004"
```

准备模型权重并启动：

```bash
mkdir -p /srv/eucal/models
# 把模型权重放进 /srv/eucal/models（路径可在 docker-compose.yml 中通过 MODEL_WEIGHTS_HOST_PATH 调整）

docker compose up -d
curl -s http://<GPU_IP>:8004/health
```

### 3.3 部署 router-service

```bash
cd /srv/eucal/backend/services/router-service
cp .env.example .env
```

编辑 `.env`：

```bash
# 服务发现 — 全部走内网 IP
USER_SERVICE_URL=http://<BACKEND_IP>:8000
ADMIN_SERVICE_URL=http://<BACKEND_IP>:8001
INFERENCE_SERVICE_URL=http://127.0.0.1:8004        # 同节点可用 localhost

INTERNAL_SECRET=<INTERNAL_SECRET>
INFERENCE_SERVICE_SECRET=<INFERENCE_SERVICE_SECRET>

# Redis（可选）— router 默认不连 Redis，需要的话指向后端节点
# 如果要用，需要在 Server B 暴露 Redis 端口（见末尾"附录"）
# ROUTER_REDIS_URL=redis://<BACKEND_IP>:6379/4
# CHANNEL_HEALTH_REDIS_URL=redis://<BACKEND_IP>:6379/5

# 上游 LLM API Key
AUTODL_API_KEY=<your-key>
AIPING_API_KEY=<your-key>
OPENROUTER_API_KEY=<your-key>

LOG_LEVEL=INFO
LOG_TO_FILE=true
ENV=production
DEBUG=false
```

修改端口：

```yaml
# services/router-service/docker-compose.yml
ports:
  - "<GPU_IP>:8003:8003"
```

启动：

```bash
docker compose up -d
curl -s http://<GPU_IP>:8003/health
```

---

## 四、前端节点部署 (Server A, 2H2G)

前端节点同时跑两个前端容器，加一层 Nginx 做 HTTPS 终止和域名分发。

### 4.1 克隆仓库

```bash
mkdir -p /srv/eucal && cd /srv/eucal
git clone git@github.com:NeoFii/eucal-admin.git admin-frontend
git clone git@github.com:NeoFii/Frontend-zh.git user-frontend
```

### 4.2 创建本地 Docker 网络

前端节点上没有后端服务，但两个前端共用一个网络方便管理：

```bash
docker network create eucal_frontend_network
```

> **注意**：前端节点不需要 `eucal_backend_network`（那是后端节点的网络）。前端容器通过内网 IP 访问后端。

### 4.3 部署 admin-frontend

```bash
cd /srv/eucal/admin-frontend
cp .env.example .env
```

编辑 `.env`：

```bash
# 后端 API — 跨节点用内网 IP
API_URL=http://<BACKEND_IP>:8001
PORT=3001
```

修改 `docker-compose.yml`，把网络改成 `eucal_frontend_network`，端口绑定到 localhost：

```yaml
services:
  admin:
    build:
      context: .
      args:
        API_URL: ${API_URL:-http://<BACKEND_IP>:8001}
    ports:
      - "127.0.0.1:${PORT:-3001}:3001"     # 只监听本机，让 Nginx 反代
    restart: unless-stopped
    networks:
      - frontend
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:3001/login"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

networks:
  frontend:
    external: true
    name: eucal_frontend_network
```

构建并启动：

```bash
docker compose up -d --build
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3001/login
```

### 4.4 部署 user-frontend (Frontend-zh)

```bash
cd /srv/eucal/user-frontend/deploy
cp .env.example .env
```

编辑 `.env`：

```bash
# 构建时变量（保持默认即可）
NEXT_PUBLIC_API_BASE_URL=/api/v1
NEXT_PUBLIC_COMPANY_NAME=Eucal AI
NEXT_PUBLIC_IMAGE_HOSTS=eucal.ai,www.eucal.ai,yourdomain.com
NEXT_PUBLIC_ROUTER_API_BASE_URL=/router-api/api/v1
NEXT_PUBLIC_ROUTER_OPENAI_BASE_URL=/router-api/v1

# 运行时变量 — 跨节点用内网 IP
API_URL=http://<BACKEND_IP>:8000          # user-service
ROUTER_API_URL=http://<GPU_IP>:8003       # router-service

FRONTEND_PORT=3000
```

修改 `docker-compose.yml`：

```yaml
services:
  frontend:
    # ... 原有配置保持 ...
    ports:
      - "127.0.0.1:${FRONTEND_PORT:-3000}:3000"   # 只监听本机
    networks:
      - frontend

networks:
  frontend:
    external: true
    name: eucal_frontend_network
```

构建并启动：

```bash
chmod +x deploy.sh
./deploy.sh up
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000/
```

### 4.5 配置 Nginx + HTTPS

```bash
apt update && apt install -y nginx certbot python3-certbot-nginx
```

创建配置 `/etc/nginx/sites-available/eucal`：

```nginx
# 管理后台
server {
    listen 80;
    server_name admin.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name admin.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/admin.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/admin.yourdomain.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# 用户前端
server {
    listen 80;
    server_name www.yourdomain.com yourdomain.com;
    return 301 https://www.yourdomain.com$request_uri;
}

server {
    listen 443 ssl http2;
    server_name www.yourdomain.com yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/www.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/www.yourdomain.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    client_max_body_size 10m;

    # 大模型流式响应需要更长的超时
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;       # 流式响应必需
    }
}
```

启用并申请证书：

```bash
ln -s /etc/nginx/sites-available/eucal /etc/nginx/sites-enabled/
nginx -t

certbot --nginx -d admin.yourdomain.com -d www.yourdomain.com -d yourdomain.com
systemctl reload nginx
```

---

## 五、防火墙配置

### Server A (前端节点)

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp           # SSH
ufw allow 80/tcp           # HTTP
ufw allow 443/tcp          # HTTPS
ufw enable
```

### Server B (后端节点)

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
# 只允许前端和 GPU 节点访问后端服务端口
ufw allow from <FRONTEND_IP> to any port 8000   # user-service
ufw allow from <FRONTEND_IP> to any port 8001   # admin-service
ufw allow from <GPU_IP> to any port 8000
ufw allow from <GPU_IP> to any port 8001
ufw enable
```

### Server C (GPU 节点)

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow from <FRONTEND_IP> to any port 8003   # router 给前端用
ufw allow from <BACKEND_IP> to any port 8003    # router 给后端用（admin 拉配置）
ufw allow from <BACKEND_IP> to any port 8004    # inference 给后端用
ufw enable
```

> 如果云服务商有安全组（阿里云/腾讯云/AWS），优先在安全组层面做限制，比 ufw 更可靠。

---

## 六、内网通信速查表

| 调用方 → 被调方 | 地址 | 端口 |
|---|---|---|
| admin-service → user-service | `http://user-service:8000` | 同 Docker 网络 |
| admin-service → router-service | `http://<GPU_IP>:8003` | 内网 |
| admin-service → inference-service | `http://<GPU_IP>:8004` | 内网 |
| user-service → admin-service | `http://admin-service:8001` | 同 Docker 网络 |
| router-service → user-service | `http://<BACKEND_IP>:8000` | 内网 |
| router-service → admin-service | `http://<BACKEND_IP>:8001` | 内网 |
| router-service → inference-service | `http://127.0.0.1:8004` | 同节点 localhost |
| inference-service → admin-service | `http://<BACKEND_IP>:8001` | 内网 |
| admin-frontend → admin-service | `http://<BACKEND_IP>:8001` | 内网 |
| user-frontend → user-service | `http://<BACKEND_IP>:8000` | 内网 |
| user-frontend → router-service | `http://<GPU_IP>:8003` | 内网 |

---

## 七、运维命令

### 查看日志

```bash
# 查看某个服务的日志
cd /srv/eucal/backend/services/admin-service
docker compose logs -f --tail 100 admin-service

# 查看所有容器的状态
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

### 更新部署

后端节点：

```bash
cd /srv/eucal/backend && git pull origin main

# 数据库迁移（如有）
cd services/admin-service
docker compose run --rm admin-service alembic -c migrations/alembic.ini upgrade head
docker compose up -d --build

cd ../user-service
docker compose run --rm user-service alembic -c migrations/alembic.ini upgrade head
docker compose up -d --build
```

GPU 节点：

```bash
cd /srv/eucal/backend && git pull origin main
cd services/inference-service && docker compose up -d --build
cd ../router-service && docker compose up -d --build
```

前端节点：

```bash
cd /srv/eucal/admin-frontend && git pull && docker compose up -d --build
cd /srv/eucal/user-frontend && git pull && cd deploy && ./deploy.sh up
```

### 数据库备份

```bash
# 在后端节点执行
docker exec $(docker ps -qf name=mysql) mysqldump -uroot -p'<MYSQL_ROOT_PASSWORD>' \
  --databases eucal_ai_admin eucal_ai_user \
  --single-transaction --routines --triggers \
  | gzip > /srv/eucal/backup/db_$(date +%Y%m%d_%H%M%S).sql.gz

# 恢复
gunzip -c /srv/eucal/backup/db_20260502_120000.sql.gz | \
  docker exec -i $(docker ps -qf name=mysql) mysql -uroot -p'<MYSQL_ROOT_PASSWORD>'
```

加入 crontab 每日备份：

```bash
echo "0 3 * * * /srv/eucal/scripts/backup.sh" | crontab -
```

### 重启服务

```bash
# 后端节点
cd /srv/eucal/backend/services/admin-service && docker compose restart
cd /srv/eucal/backend/services/user-service && docker compose restart

# GPU 节点
cd /srv/eucal/backend/services/router-service && docker compose restart
cd /srv/eucal/backend/services/inference-service && docker compose restart

# 前端节点
cd /srv/eucal/admin-frontend && docker compose restart
cd /srv/eucal/user-frontend/deploy && ./deploy.sh restart
```

---

## 八、资源占用估算

| 服务 | 内存（典型） | CPU |
|------|------------|-----|
| MySQL 8 | 400-600MB | 低 |
| Redis 7 | 50-100MB | 极低 |
| admin-service (2 workers) | 300-500MB | 低 |
| admin-worker | 100-200MB | 极低 |
| user-service (2 workers) | 300-500MB | 中 |
| user-worker | 100-200MB | 极低 |
| router-service (4 workers) | 400-800MB | 中-高 |
| inference-service | 视模型而定（GPU 显存） | 高 |
| eucal-admin (Next.js) | 100-150MB | 低 |
| Frontend-zh (Next.js) | 100-150MB | 中 |
| Nginx | 20-50MB | 极低 |

**预估**：
- Server A (2H2G): 两个前端 + Nginx ≈ 350MB，剩余资源充足
- Server B (2H4G): MySQL + Redis + admin + user + workers ≈ 1.5-2.5GB，建议留 1GB+ 给系统和 buffer
- Server C: 取决于推理模型规模

---

## 九、常见问题

### Q: 跨节点调用超时？

1. 检查内网连通性：`ping <BACKEND_IP>` / `telnet <BACKEND_IP> 8001`
2. 检查防火墙是否放行：`ufw status`
3. 从容器内测试连通性：

```bash
# 从 GPU 节点的 router 容器内测试到后端
docker exec $(docker ps -qf name=router-service) \
  wget -qO- http://<BACKEND_IP>:8001/api/v1/health
```

### Q: MySQL 首次启动后服务连接失败？

MySQL 首次启动需要 30-60 秒初始化。等 `docker compose -f /srv/eucal/backend/infra/docker-compose.yml ps` 显示 MySQL `healthy` 后再启动后端服务。

### Q: 前端构建时如何指向后端 IP？

`API_URL` 是构建时参数，每次修改后端 IP 都要重新 `docker compose up -d --build`。生产环境建议固定内网 IP（云服务器一般支持设置固定私网 IP）。

### Q: 跨节点 Docker 容器能直接互联吗？

不能。Docker 默认网络仅在单台主机内有效。跨节点通信必须通过宿主机网卡（即内网 IP）。本文档的设计就是这样：同节点内的服务通过 Docker 网络（服务名）互通，跨节点通过内网 IP。

### Q: 我能不能让 router-service 用上 Server B 的 Redis？

可以。需要修改 Server B 的 `infra/docker-compose.yml`，把 Redis 端口绑定到内网 IP：

```yaml
redis:
  ports:
    - "<BACKEND_IP>:6379:6379"
  command: ["redis-server", "--save", "", "--appendonly", "no", "--requirepass", "<redis-password>"]
```

防火墙开 Server B 的 6379 给 `<GPU_IP>`：

```bash
ufw allow from <GPU_IP> to any port 6379
```

GPU 节点的 router `.env`：

```bash
ROUTER_REDIS_URL=redis://:<redis-password>@<BACKEND_IP>:6379/4
CHANNEL_HEALTH_REDIS_URL=redis://:<redis-password>@<BACKEND_IP>:6379/5
```

### Q: 模型权重很大，怎么放？

在 GPU 节点的 `services/inference-service/docker-compose.yml` 中：

```yaml
volumes:
  - ${MODEL_WEIGHTS_HOST_PATH:-/srv/eucal/models}:/app/models:ro
```

把权重放到 `/srv/eucal/models` 目录即可（或修改 `MODEL_WEIGHTS_HOST_PATH` 指向其他磁盘）。

### Q: 想让 Server A 也跑后端服务（比如 admin-service）该怎么改？

不推荐。2H2G 跑两个 Next.js 已经接近上限，再加 admin-service + worker 会内存吃紧。如果一定要合并，建议升级 Server A 配置或裁剪掉 worker。


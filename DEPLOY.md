# LuckyNiuMaNote 部署与迁移指南

本文说明本仓库在 Linux 服务器上的组成、首次部署、日常更新与迁移到新机器时的注意事项。默认示例用户为 `ubuntu`、项目路径为 `/home/ubuntu/LuckyNiuMaNote`；换机时请统一替换为你的 **系统用户** 与 **项目绝对路径**。

## 1. 架构概览

| 组件 | 作用 | 典型进程/服务 |
|------|------|----------------|
| **Express (`server.js`)** | 静态站点（React 构建产物）、REST API（仓位、机器人状态、K 线等） | `systemd: luckyniuma-backend` |
| **Nginx** | 对外 80/443，反代到本机 `127.0.0.1:3000`；TLS 由 Certbot 管理 | `nginx` |
| **React 前端** | Vite 构建输出在 `frontend/dist/`，由 `server.js` 挂载 | 构建时使用 `npm run build` |
| **内容构建 (`build.js`)** | 把 `content/` 编译为 `frontend/public/generated-data.json` 与 `src/generated-data.js` | 构建时执行 |
| **交易脚本** | Python 策略、实时 JSON、CLI | `PM2: ecosystem.army.json` |
| **日志** | 策略运行日志、PM2 合并日志 | 目录 `logs/`（仓库根下，与 `.gitignore` 中规则一致时可能不提交） |

**不要把 `server.js` 同时交给 systemd 与另一套 PM2（例如旧脚本里的 `lucky-backend`）各起一个实例**，否则会争用端口 `3000`。当前推荐：**网站仅由 `luckyniuma-backend` 托管**；量化进程仅由 PM2 托管。

## 2. 系统依赖与环境

- **操作系统**：Ubuntu 22.04 LTS 等（文档在 Jammy 上验证过）。
- **Node.js**：≥ 18（一键 HTTPS 脚本会按需装 Node 20.x）。
- **Python**：3.10+；交易侧需要 **`python3-venv`**：`sudo apt install -y python3-venv`。
- **Nginx + Certbot**：由 `scripts/setup-https.sh` 安装（见下文）。
- **PM2**：`sudo npm install -g pm2`（交易与实时数据进程使用）。

云厂商安全组需放行 **80、443**（申请 Let’s Encrypt 与对外网站）；**无需**对公网开放 `3000`（仅本机回环）。

## 3. 获取代码与首次构建（网站部分）

```bash
cd /home/ubuntu
git clone <你的仓库 URL> LuckyNiuMaNote
cd LuckyNiuMaNote

npm ci || npm install
(cd frontend && npm ci || npm install)
npm run build
```

`npm run build` = `build.js`（内容） + `frontend` 的 `vite build`。生成物包括：

- `frontend/dist/`（生产前端）
- `frontend/public/generated-data.json`（站点静态数据）

本地快速验证（**不**经过 Nginx，仅调试）：

```bash
node server.js
# 默认监听环境变量 PORT（缺省 3000）与 LISTEN_HOST（缺省 0.0.0.0）
```

生产环境应设 **`LISTEN_HOST=127.0.0.1`**，由 Nginx 反代（见 `infra/luckyniuma-backend.service`）。

## 4. systemd：Express 后端（`luckyniuma-backend`）

模板文件：`infra/luckyniuma-backend.service`。

关键环境变量含义：

| 变量 | 说明 |
|------|------|
| `PORT` |  Node 监听端口，默认 `3000`，需与 Nginx `upstream` 一致。 |
| `LISTEN_HOST` | 生产建议 `127.0.0.1`，仅本机访问。 |
| `TRUST_PROXY` | 设为 `1` 时开启 `trust proxy`，便于 Express 识别 HTTPS 与客户端地址。 |
| `SITE_PUBLIC_URL` | 日志中展示的站点根 URL（可选）。 |

**换机或改路径**时，请编辑该 service 文件内的 `User`/`Group`/`WorkingDirectory`/`ExecStart` 路径，再安装：

```bash
sudo cp infra/luckyniuma-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now luckyniuma-backend
sudo systemctl status luckyniuma-backend
```

## 5. Nginx、HTTPS 与 Let’s Encrypt（SSL）

Nginx 站点模板：`infra/nginx-luckyniuma.conf`。默认 `server_name` 为 `luckyniuma.com` 与 `www.luckyniuma.com`，迁移到其它域名时请修改该文件中的 `server_name`，再安装到 `/etc/nginx/sites-available/` 并重载 Nginx。Certbot 使用 **nginx 插件** 时可能会自动改写该站点配置中的 `listen 443 ssl` 与证书路径。

### 5.1 首次申请证书的前置条件

- **DNS**：域名 **A / AAAA** 记录指向本机公网 IP（验证方式为 **HTTP-01**，Let’s Encrypt 需经 80 端口访问到你的 Nginx）。
- **入站端口**：云安全组或本机防火墙放行 **80**（校验与跳转）、**443**（HTTPS）。
- **Nginx 与站点**：`setup-https.sh` 会复制模板、启用站点、启动后端，使 80 上能反代到 `127.0.0.1:3000`，供 Certbot 完成验证。

### 5.2 一键脚本与环境变量

脚本路径：**`scripts/setup-https.sh`**（需 **root** 执行）。除安装/配置 Nginx 与 systemd 外，会在 Nginx 可用后调用 **Certbot** 申请证书。

| 变量 | 含义 |
|------|------|
| **`CERTBOT_EMAIL`** | **必填**。用于 Let’s Encrypt 账户与到期通知（建议用你可收件的邮箱）。 |
| **`DOMAINS`** | 可选。空格分隔的域名列表，会展开为多个 `certbot -d`。默认 **`luckyniuma.com`**（仅 apex）。若 `www` 已解析到本机，可设为 `luckyniuma.com www.luckyniuma.com`。 |

示例：

```bash
sudo apt install -y python3-venv   # 若尚未安装，供后续交易 venv 使用

# 仅主域名（与脚本默认一致）
sudo CERTBOT_EMAIL=你的邮箱@example.com /path/to/LuckyNiuMaNote/scripts/setup-https.sh

# 同时包含 www（二者 DNS 均需正确）
sudo CERTBOT_EMAIL=你的邮箱@example.com DOMAINS="luckyniuma.com www.luckyniuma.com" /path/to/LuckyNiuMaNote/scripts/setup-https.sh
```

脚本内 Certbot 采用非交互参数：`certbot --nginx`、`--agree-tos`、`--no-eff-email`、`--redirect`、`--non-interactive`。成功后会部署证书并在 Nginx 中打开 **HTTPS** 与 **HTTP→HTTPS** 跳转（由 Certbot 写入的配置为准）。

若申请失败（常见：DNS 未生效、80 不可达），脚本会打印可手动执行的 `certbot` 示例；修好 DNS/防火墙后重跑脚本或按提示执行即可。请确保 `CERTBOT_EMAIL` 可收件，以免错失续期提醒。

### 5.3 证书文件位置与核实

- 默认证书目录：**`/etc/letsencrypt/live/<首要域名>/`**（`fullchain.pem`、`privkey.pem` 等）。
- 核实服务与到期时间（示例）：

```bash
sudo certbot certificates
echo | openssl s_client -connect 你的域名:443 -servername 你的域名 2>/dev/null | openssl x509 -noout -dates -subject
```

### 5.4 自动续期（无需自建 cron）

安装 **`python3-certbot-nginx`** 后，Ubuntu/Debian 通常已启用 **`certbot.timer`**：

- **作用**：systemd 定时触发 **`certbot.service`**，执行 **`certbot renew`**（默认仅对临近到期的证书尝试续签）。
- **Nginx 插件**：续期成功后 Certbot 会按插件行为处理证书更新，多数情况下已配置 `reload` / `deploy hook` 避免中断；若你改过 Nginx 手工配置，升级大版本后建议再跑一次 `sudo nginx -t && sudo systemctl reload nginx`。

常用检查命令：

```bash
systemctl status certbot.timer
systemctl list-timers | grep certbot
sudo certbot renew --dry-run   # 干跑验证续期链路是否正常
```

一般不须再添加 root 的 cron 任务；若 `certbot.timer` 被禁用，可执行：

```bash
sudo systemctl enable --now certbot.timer
```

### 5.5 事后追加域名（证书扩展）

若首次只申请了 `example.com`，后来要为 `www.example.com` 使用同一张证书：

```bash
sudo certbot --nginx -d example.com -d www.example.com --expand
```

并保证 Nginx `server_name` 与 DNS 一致。

### 5.6 与 systemd 后端的关系

`setup-https.sh` 末尾会 **`systemctl restart luckyniuma-backend`**，以便 Node 在 TLS 就绪后正常提供站点。日常仅续证时通常不需要重启 Node；仅当证书路径或反代结构变更时才考虑重载 Nginx 或按需重启后端。

## 6. 交易侧：Python 虚拟环境与配置

### 6.1 配置文件（不要提交 Git）

路径：**`trading-scripts/config/.hl_config`**（`KEY=value` 行格式，参见 `config/.hl_config.sample`）。

- 策略脚本、`hl_trade.py`、`transfer.py` 均从该路径读取（或配合环境变量 `HL_API_KEY`）。
- 权限建议：`chmod 600 trading-scripts/config/.hl_config`。

### 6.2 虚拟环境与依赖

```bash
cd trading-scripts
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`run_*.sh` 会 `source .venv/bin/activate` 后执行对应 `scripts/*.py`。

### 6.3 日志目录

策略与 NFI 会向仓库根目录 **`logs/`** 写入 `trader_nfi.log`、`trader_01_boll_macd.log` 等；PM2 另有合并日志路径（见 `ecosystem.army.json`）。若目录不存在，可由进程创建或手动 `mkdir -p logs`。

## 7. PM2：量化「军团」与实时数据

配置文件：**`trading-scripts/ecosystem.army.json`**。

当前包含：

- `auto-trader`（NFI 主策略）
- `trader-boll-macd`、`trader-supertrend`、`trader-adx`
- `realtime-data`（循环执行 `generate_realtime_data.py`，写入 `frontend/dist/realtime-data.json`）

**注意**：JSON 内 `cwd`、`log_file` 等使用了绝对路径 **`/home/ubuntu/LuckyNiuMaNote`**。迁移到新路径时，请全文替换为你的项目根目录。

启动（以运行用户执行，例如 `ubuntu`）：

```bash
cd /path/to/LuckyNiuMaNote/trading-scripts
sudo -u ubuntu bash -c 'export PATH=/usr/bin:$PATH; pm2 start ecosystem.army.json && pm2 save'
sudo -u ubuntu pm2 startup systemd -u ubuntu --hp /home/ubuntu   # 按命令输出再执行一条 sudo env ...
```

开机自启依赖 **`pm2-ubuntu.service`**（或对应的 `pm2-<user>.service`）。

常用运维：

```bash
sudo -u ubuntu pm2 list
sudo -u ubuntu pm2 restart all
sudo -u ubuntu pm2 logs auto-trader --lines 50
```

根目录另有一份 **`trading-scripts/ecosystem.config.json`**（含更多策略应用），若需单独启动可与 `ecosystem.army.json` 二选一或合并，避免重复进程名。

## 8. 根目录 `deploy.sh` 说明（与当前推荐的差异）

`deploy.sh` 仍假设用 **PM2 名称 `lucky-backend`** 跑 `server.js`。若生产已改用 **`luckyniuma-backend`（systemd）**，请勿直接运行该脚本而不改逻辑，否则可能重复起后端或路径仍为旧环境。

推荐日常发布网站流程：

```bash
cd /path/to/LuckyNiuMaNote
npm run build
sudo systemctl restart luckyniuma-backend
```

交易侧更新代码后：

```bash
sudo -u ubuntu pm2 restart all && sudo -u ubuntu pm2 save
```

## 9. 迁移检查清单（换服务器）

1. **克隆仓库**到新路径；安装 Node / `npm run build`。
2. 修改 **`infra/luckyniuma-backend.service`** 中用户、路径、`SITE_PUBLIC_URL`，安装并启动 systemd。
3. 修改 **`infra/nginx-luckyniuma.conf`** 中 `server_name`；必要时重新跑 Certbot 或拷贝 `/etc/letsencrypt`（不推荐手动拷私钥，优先在新机重新申请）。
4. 修改 **`trading-scripts/ecosystem.army.json`**（及若使用的 **`ecosystem.config.json`**）中所有绝对路径。
5. 从旧机**安全拷贝** `trading-scripts/config/.hl_config`（勿入 Git）；`chmod 600`。
6. 安装 **`python3-venv`**，重建 `trading-scripts/.venv`，`pip install -r requirements.txt`。
7. 创建或确认 **`logs/`** 权限属主与运行用户一致。
8. 安装 PM2、`pm2 start ecosystem.army.json`、`pm2 save`、`pm2 startup`。
9. 安全组放行 **80/443**；验证 `https://你的域名/` 与 `https://你的域名/api/position`。
10. 确认 **仅一个** Node 进程监听 `3000`（`ss -tlnp | grep 3000`）。

## 10. 主要 URL 与 API（便于验收）

| URL | 说明 |
|-----|------|
| `/` | 首页（React SPA） |
| `/strategy`、`/learn`、`/chart` | 其他前端路由 |
| `/api/position` | 聚合账户与持仓（读 Hyperliquid） |
| `/api/traders-status` | 各策略进程存活与日志摘要 |
| `/api/indicators`、`/api/chart/:symbol` | 指标与图表数据 |

## 11. 相关文件索引

| 路径 | 说明 |
|------|------|
| `server.js` | Express 入口，环境变量见上文 |
| `build.js` | 内容构建 |
| `frontend/vite.config.js` | 前端构建配置 |
| `scripts/setup-https.sh` | Node/Nginx/Certbot/systemd 一键初始化 |
| `infra/nginx-luckyniuma.conf` | Nginx 反代模板 |
| `infra/luckyniuma-backend.service` | systemd 单元模板 |
| `trading-scripts/ecosystem.army.json` | PM2：首页展示的 4 个机器人 + 实时数据 |
| `trading-scripts/requirements.txt` | Python 依赖 |
| `trading-scripts/config/.hl_config.sample` | 交易配置模板 |

---

**免责声明**：本文档仅描述技术部署步骤。链上与交易所操作有风险，请自行做好密钥与资金安全。

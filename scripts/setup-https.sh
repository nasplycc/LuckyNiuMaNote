#!/usr/bin/env bash
# 在 Ubuntu 服务器上一键：安装 Node/Nginx/Certbot、构建站点、systemd 后端、申请 Let's Encrypt、启用自动续期。
# 用法：
#   sudo CERTBOT_EMAIL=你的邮箱@example.com ./scripts/setup-https.sh
# 若 www 未做 DNS，可仅申请主域名：
#   sudo CERTBOT_EMAIL=... DOMAINS="luckyniuma.com" ./scripts/setup-https.sh
#
# 前置：luckyniuma.com（及可选 www）A/AAAA 记录指向本机公网 IP，且 80/443 对本机放行。

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
EMAIL="${CERTBOT_EMAIL:-}"
# 默认仅主域名；www 需 DNS 指向本机后再设为 "luckyniuma.com www.luckyniuma.com" 或运行 certbot --expand
DOMAINS="${DOMAINS:-luckyniuma.com}"

if [[ "${EUID:-0}" -ne 0 ]]; then
  echo "请使用 root 运行：sudo CERTBOT_EMAIL=你的邮箱 $0"
  exit 1
fi

if [[ -z "$EMAIL" ]]; then
  echo "请设置 CERTBOT_EMAIL（Let's Encrypt 到期提醒用）。"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y curl ca-certificates nginx python3-certbot-nginx

if ! command -v node >/dev/null 2>&1 || ! node -e "process.exit(parseInt(process.versions.node,10)>=18?0:1)" 2>/dev/null; then
  echo "安装 Node.js 20.x …"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

echo "构建站点 …"
cd "$PROJECT_DIR"
sudo -u ubuntu bash -c "set -e; cd '$PROJECT_DIR'; if [ ! -d node_modules ]; then npm ci || npm install; fi; if [ ! -d frontend/node_modules ]; then (cd frontend && (npm ci || npm install)); fi; npm run build"

install -o root -g root -m 644 "$PROJECT_DIR/infra/nginx-luckyniuma.conf" /etc/nginx/sites-available/luckyniuma.com
ln -sf /etc/nginx/sites-available/luckyniuma.com /etc/nginx/sites-enabled/luckyniuma.com
if [[ -f /etc/nginx/sites-enabled/default ]]; then
  rm -f /etc/nginx/sites-enabled/default
fi

install -o root -g root -m 644 "$PROJECT_DIR/infra/luckyniuma-backend.service" /etc/systemd/system/luckyniuma-backend.service
systemctl daemon-reload
systemctl enable luckyniuma-backend.service
systemctl restart luckyniuma-backend.service

nginx -t
systemctl reload nginx

# 组装 certbot -d 参数
CERTBOT_D=()
for d in $DOMAINS; do
  CERTBOT_D+=(-d "$d")
done

echo "申请 TLS 证书（HTTP-01，需域名已解析到本机）…"
if certbot --nginx "${CERTBOT_D[@]}" \
  --email "$EMAIL" \
  --agree-tos \
  --no-eff-email \
  --redirect \
  --non-interactive; then
  systemctl reload nginx
else
  echo "⚠ 证书申请未成功（多为 DNS 未到本机或 80 端口不可达）。HTTP 仍可访问；DNS 就绪后执行："
  echo "  sudo certbot --nginx ${CERTBOT_D[*]} --email $EMAIL --agree-tos --no-eff-email --redirect"
fi
systemctl restart luckyniuma-backend.service

echo ""
echo "续期：系统已安装 certbot.timer，由 systemd 定时执行 certbot renew（一般每天两次）。"
systemctl enable certbot.timer 2>/dev/null || true
systemctl start certbot.timer 2>/dev/null || true
systemctl status certbot.timer --no-pager || true

FIRST_DOMAIN="$(echo "$DOMAINS" | awk '{print $1}')"
echo ""
echo "站点：https://${FIRST_DOMAIN}"
echo "后端：systemctl status luckyniuma-backend"

# EC2 first boot (Amazon Linux 2023, arm64). CDK prepends /etc/warszawa/instance.env above this.
# Installs tooling and the pull agent; the agent then clones release/<env> and runs deploy/deploy.sh.
set -euxo pipefail

# 1 GB RAM box: swap so uv sync / npm builds don't OOM
if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile swap swap defaults 0 0' >> /etc/fstab
fi

dnf install -y git jq

# uv (pinned) for Python deps; Python itself is downloaded by uv into a world-readable dir
UV_VERSION=0.13.0
curl -fsSL "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-aarch64-unknown-linux-gnu.tar.gz" \
  | tar -xz --strip-components=1 -C /usr/local/bin uv-aarch64-unknown-linux-gnu/uv uv-aarch64-unknown-linux-gnu/uvx
mkdir -p /opt/uv/python /opt/uv/cache && chmod -R 755 /opt/uv

id warszawa >/dev/null 2>&1 || useradd --system --home-dir /opt/warszawa --shell /sbin/nologin warszawa
mkdir -p /opt/warszawa && chmod 755 /opt/warszawa

# GitHub host key (from https://api.github.com/meta), so git over SSH never trusts on first use
mkdir -p /etc/warszawa
echo 'github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl' \
  > /etc/warszawa/known_hosts

install -m 755 /dev/stdin /usr/local/bin/warszawa-agent <<'AGENT'
__AGENT__
AGENT

cat > /etc/systemd/system/warszawa-agent.service <<'UNIT'
[Unit]
Description=Warszawa Live deploy agent (pulls release branch, deploys)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/warszawa-agent
TimeoutStartSec=1800
UNIT

cat > /etc/systemd/system/warszawa-agent.timer <<'UNIT'
[Unit]
Description=Check for a new release every minute

[Timer]
OnBootSec=30s
OnUnitInactiveSec=60s

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now warszawa-agent.timer

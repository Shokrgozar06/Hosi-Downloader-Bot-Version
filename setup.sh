#!/bin/bash
set -e

echo "=========================================================="
echo "      Hosi Downloader Bot - One-Click Server Setup        "
echo "=========================================================="

echo "=== 1. Updating packages and installing dependencies ==="
sudo apt update
sudo apt install -y python3-pip python3-venv git curl docker.io ffmpeg nodejs npm

echo "=== 2. Setting up 4GB Swap (to prevent Out-Of-Memory) ==="
if [ ! -f /swapfile ]; then
    echo "Creating 4GB swapfile..."
    sudo fallocate -l 4G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    if ! grep -q '/swapfile' /etc/fstab; then
        echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    fi
    echo "Swap created and activated."
else
    echo "Swapfile already exists."
fi

echo "=== 3. Installing Deno via npm ==="
if ! command -v deno &> /dev/null; then
    echo "Installing Deno using npm (global)..."
    sudo npm install -g deno
    # If not found in standard PATH, create symlink or fallback
    if ! command -v deno &> /dev/null; then
        NPM_DENO_PATH=$(npm root -g)/deno/bin/deno
        if [ -f "$NPM_DENO_PATH" ]; then
            sudo ln -sf "$NPM_DENO_PATH" /usr/local/bin/deno
        else
            echo "Fallback: Installing Deno via official script..."
            curl -fsSL https://deno.land/install.sh | sh
            sudo cp ~/.deno/bin/deno /usr/local/bin/deno
        fi
    fi
    echo "Deno installed: $(deno --version | head -n 1)"
else
    echo "Deno is already installed: $(deno --version | head -n 1)"
fi

echo "=== 4. Starting Telegram Bot API local server (Docker) ==="
sudo systemctl enable --now docker
docker rm -f telegram-bot-api 2>/dev/null || true
docker run -d \
  --name=telegram-bot-api \
  --restart=always \
  -p 8081:8081 \
  -v /var/lib/telegram-bot-api:/var/lib/telegram-bot-api \
  -e TELEGRAM_API_ID=32477543 \
  -e TELEGRAM_API_HASH=38a5e1a8693d16bbb22a33bc1cda0a26 \
  -e TELEGRAM_LOCAL=true \
  aiogram/telegram-bot-api:latest

echo "=== 5. Setting up Python venv and requirements ==="
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

echo "=== 6. Setting up Systemd Service for 24/7 background running ==="
SERVICE_FILE="/etc/systemd/system/hosi-bot.service"
CURRENT_DIR=$(pwd)
CURRENT_USER=$(whoami)

sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=Hosi Downloader Telegram Bot
After=network.target docker.service

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$CURRENT_DIR
ExecStart=$CURRENT_DIR/venv/bin/python $CURRENT_DIR/downloader.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable hosi-bot
sudo systemctl restart hosi-bot

echo "=========================================================="
echo " Setup complete! The bot is running in background (24/7). "
echo " - View real-time logs: sudo journalctl -u hosi-bot -f    "
echo " - Restart bot:         sudo systemctl restart hosi-bot   "
echo " - Stop bot:            sudo systemctl stop hosi-bot      "
echo "=========================================================="

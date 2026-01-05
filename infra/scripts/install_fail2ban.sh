#!/bin/bash
# ============================================================
# Subro Web Fail2Ban Installation Script
# ============================================================
#
# This script:
# 1. Installs fail2ban if not present
# 2. Creates log directory with correct permissions
# 3. Copies filter and jail configurations
# 4. Validates configuration
# 5. Restarts fail2ban
#
# Usage: sudo ./install_fail2ban.sh
#
# ============================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL2BAN_DIR="$SCRIPT_DIR/fail2ban"
LOG_DIR="/opt/subro_web/logs"

echo -e "${GREEN}=== Subro Web Fail2Ban Installation ===${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
    exit 1
fi

# 1. Install fail2ban if not present
echo -e "${YELLOW}Step 1: Checking fail2ban installation...${NC}"
if ! command -v fail2ban-client &> /dev/null; then
    echo "Installing fail2ban..."
    apt-get update
    apt-get install -y fail2ban
    echo -e "${GREEN}✓ fail2ban installed${NC}"
else
    echo -e "${GREEN}✓ fail2ban already installed$(NC)"
fi

# 2. Ensure log directory exists with correct permissions
echo ""
echo -e "${YELLOW}Step 2: Setting up log directory...${NC}"
mkdir -p "$LOG_DIR"
touch "$LOG_DIR/security.log"
chmod 640 "$LOG_DIR/security.log"
chown root:adm "$LOG_DIR/security.log"
echo -e "${GREEN}✓ Log directory ready: $LOG_DIR${NC}"

# 3. Copy filter configurations
echo ""
echo -e "${YELLOW}Step 3: Installing fail2ban filters...${NC}"
if [ -d "$FAIL2BAN_DIR/filter.d" ]; then
    cp "$FAIL2BAN_DIR/filter.d/"*.conf /etc/fail2ban/filter.d/
    echo -e "${GREEN}✓ Filters installed:${NC}"
    ls -la /etc/fail2ban/filter.d/subro-*.conf
else
    echo -e "${RED}Error: Filter directory not found: $FAIL2BAN_DIR/filter.d${NC}"
    exit 1
fi

# 4. Copy jail configuration
echo ""
echo -e "${YELLOW}Step 4: Installing fail2ban jails...${NC}"
if [ -d "$FAIL2BAN_DIR/jail.d" ]; then
    cp "$FAIL2BAN_DIR/jail.d/"*.local /etc/fail2ban/jail.d/
    echo -e "${GREEN}✓ Jails installed:${NC}"
    ls -la /etc/fail2ban/jail.d/subro*.local
else
    echo -e "${RED}Error: Jail directory not found: $FAIL2BAN_DIR/jail.d${NC}"
    exit 1
fi

# 5. Test configuration
echo ""
echo -e "${YELLOW}Step 5: Validating fail2ban configuration...${NC}"
if fail2ban-client -t; then
    echo -e "${GREEN}✓ Configuration is valid${NC}"
else
    echo -e "${RED}Error: Configuration validation failed!${NC}"
    echo "Please check the configuration files and try again."
    exit 1
fi

# 6. Restart fail2ban
echo ""
echo -e "${YELLOW}Step 6: Restarting fail2ban service...${NC}"
systemctl restart fail2ban
systemctl enable fail2ban
echo -e "${GREEN}✓ fail2ban restarted and enabled${NC}"

# 7. Verify jails are active
echo ""
echo -e "${YELLOW}Step 7: Verifying active jails...${NC}"
sleep 2  # Give fail2ban a moment to start
echo ""
echo -e "${GREEN}=== Active Jails ===${NC}"
fail2ban-client status

echo ""
echo -e "${GREEN}=== Installation Complete ===${NC}"
echo ""
echo "Useful commands:"
echo "  - Check all jails:        sudo fail2ban-client status"
echo "  - Check specific jail:    sudo fail2ban-client status subro-login"
echo "  - Unban an IP:            sudo fail2ban-client unban <IP>"
echo "  - Test filter regex:      fail2ban-regex $LOG_DIR/security.log /etc/fail2ban/filter.d/subro-login.conf"
echo ""
echo -e "${YELLOW}IMPORTANT: Review and update ignoreip in /etc/fail2ban/jail.d/subro.local${NC}"
echo "Add your office VPN ranges to prevent accidental lockouts!"

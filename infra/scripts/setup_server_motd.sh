#!/bin/bash
# setup_server_motd.sh
# Optimizes MOTD scripts to skip for non-interactive SSH sessions (CI/CD)
# Run this after server setup: sudo ./setup_server_motd.sh

set -e

SCRIPTS=(
    "/etc/update-motd.d/51-my-sysinfo"
    "/etc/update-motd.d/92-health"
    "/etc/update-motd.d/60-fail2ban-status"
)

SKIP_CHECK='[[ -z "$SSH_TTY" && -z "$TERM" ]] && exit 0'

for script in "${SCRIPTS[@]}"; do
    if [ -f "$script" ]; then
        if grep -q 'SSH_TTY' "$script"; then
            echo "✓ $script already has CI/CD skip check"
        else
            echo "Adding CI/CD skip check to $script..."
            sed -i "5i\\# Skip for non-interactive SSH sessions (CI/CD)\\n$SKIP_CHECK\\n" "$script"
            echo "✓ Updated $script"
        fi
    else
        echo "⚠ $script not found, skipping"
    fi
done

echo ""
echo "Done! MOTD scripts will now skip for non-interactive SSH sessions."

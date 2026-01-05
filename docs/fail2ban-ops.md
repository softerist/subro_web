# Fail2Ban Operations Runbook for Subro Web

# ==========================================

## Quick Reference Commands

### Check Status

```bash
# All jails overview
sudo fail2ban-client status

# Specific jail status (shows banned IPs)
sudo fail2ban-client status subro-login
sudo fail2ban-client status subro-token
sudo fail2ban-client status subro-ratelimit
sudo fail2ban-client status subro-scan
sudo fail2ban-client status recidive

# List all currently banned IPs across all jails
sudo fail2ban-client banned
```

### Unban an IP

```bash
# Unban from specific jail
sudo fail2ban-client set subro-login unbanip 192.168.1.100

# Unban from ALL jails at once
sudo fail2ban-client unban 192.168.1.100

# Unban all IPs (emergency reset)
sudo fail2ban-client unban --all
```

### Temporarily Whitelist an IP

Edit `/etc/fail2ban/jail.d/subro.local`:

```ini
[DEFAULT]
ignoreip = 127.0.0.1/8 ::1 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 YOUR_IP_HERE
```

Then reload: `sudo fail2ban-client reload`

### Test Filter Regex

```bash
# Test against actual security log
fail2ban-regex /opt/subro_web/logs/security.log /etc/fail2ban/filter.d/subro-login.conf

# Test with verbose output (shows matches)
fail2ban-regex /opt/subro_web/logs/security.log /etc/fail2ban/filter.d/subro-login.conf --print-all-matched
```

### View Recent Bans

```bash
# Last 20 ban events
grep "Ban" /var/log/fail2ban.log | tail -20

# Bans for specific IP
grep "192.168.1.100" /var/log/fail2ban.log

# Watch bans in real-time
tail -f /var/log/fail2ban.log | grep --line-buffered "Ban\|Unban"
```

---

## Troubleshooting

### "fail2ban banned my reverse proxy / Caddy / internal IP"

**Root Cause:** The application isn't extracting the real client IP correctly.

**Solution:**

1. Check `ignoreip` includes your proxy IPs:

   ```bash
   grep ignoreip /etc/fail2ban/jail.d/subro.local
   ```

2. Verify the application logs show real client IPs:

   ```bash
   tail -f /opt/subro_web/logs/security.log
   ```

   You should see external IPs, not `172.x.x.x` or `10.x.x.x`.

3. Check Docker networking:

   ```bash
   docker exec blue-api-1 cat /app/logs/security.log | tail -20
   ```

4. Verify X-Forwarded-For is being set by your proxy (Nginx/Caddy).

### "Legitimate user got banned"

**Immediate Action:**

```bash
# Unban immediately
sudo fail2ban-client unban 203.0.113.50
```

**Investigation:**

```bash
# See what triggered the ban
grep "203.0.113.50" /opt/subro_web/logs/security.log
grep "203.0.113.50" /var/log/fail2ban.log
```

**Possible Causes:**

- Corporate network / shared IP (multiple users behind NAT)
- Forgotten password + multiple attempts
- Automated client with stale credentials
- Frontend bug causing repeated failed requests

**If recurring for specific IP/network:**
Add to permanent whitelist in `/etc/fail2ban/jail.d/subro.local`.

### "No bans are happening even with attacks"

**Check jail is enabled:**

```bash
sudo fail2ban-client status subro-login
# Should show "Currently failed:" and "Currently banned:"
```

**Check log path exists and is readable:**

```bash
ls -la /opt/subro_web/logs/security.log
# Should show recent modification time
```

**Test filter manually:**

```bash
fail2ban-regex /opt/subro_web/logs/security.log /etc/fail2ban/filter.d/subro-login.conf
# Should show "Lines: X lines, ... matched, ..."
```

**Check fail2ban logs for errors:**

```bash
journalctl -u fail2ban -n 50
```

### "Ban times aren't escalating"

Progressive bans only work if fail2ban is tracking ban history. Check that:

1. `bantime.increment = true` is in the jail config
2. The fail2ban database isn't being cleared: `/var/lib/fail2ban/fail2ban.sqlite3`

---

## Log File Locations

| Log             | Location                              | Purpose                                  |
| --------------- | ------------------------------------- | ---------------------------------------- |
| Security events | `/opt/subro_web/logs/security.log`    | Application security events for fail2ban |
| Fail2ban log    | `/var/log/fail2ban.log`               | Ban/unban actions                        |
| Jail config     | `/etc/fail2ban/jail.d/subro.local`    | Jail definitions                         |
| Filter configs  | `/etc/fail2ban/filter.d/subro-*.conf` | Regex patterns                           |

---

## Progressive Ban Escalation

Ban times escalate automatically for repeat offenders:

| Offense           | Approximate Ban Time |
| ----------------- | -------------------- |
| 1st               | 15 minutes           |
| 2nd               | 6 hours              |
| 3rd               | 6 days               |
| 4+ (via recidive) | 1 year               |

The recidive jail watches fail2ban's own log. If an IP gets banned 4+ times within a week, they're banned for 1 year on ALL ports.

---

## Maintenance

### Log Rotation

Logs are rotated via logrotate. Config location: `/etc/logrotate.d/subro-logs`

### Database Cleanup

Fail2ban maintains a SQLite database of ban history. To reset:

```bash
sudo systemctl stop fail2ban
sudo rm /var/lib/fail2ban/fail2ban.sqlite3
sudo systemctl start fail2ban
```

⚠️ This resets all ban history and progressive escalation!

### Updating Filters

After modifying filter files:

```bash
sudo fail2ban-client reload
```

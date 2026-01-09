# qBittorrent Integration Guide

This guide explains how to integrate qBittorrent with the Subro Web application. There are two levels of integration:

1. **Dashboard Monitoring**: Displays qBittorrent status and links in the app dashboard.
2. **Automated Subtitle Support**: Automatically triggers a subtitle download job when qBittorrent completes a download.

---

## 1. Dashboard Monitoring Configuration

To see qBittorrent status and quick links in your dashboard, you need to configure the credentials in the application settings.

### Via Web Interface (Recommended)

1. Log in as an **Admin** or **Superuser**.
2. Navigate to **Settings** (⚙️).
3. Under the **qBittorrent** section, enter:
   - **Host**: The IP or hostname of your qBittorrent server (e.g., `192.168.1.100` or `localhost`).
   - **Port**: The Web UI port (default is `8080`).
   - **Username**: Your qBittorrent Web UI username.
   - **Password**: Your qBittorrent Web UI password.
4. Click **Save Settings**.

### Via Environment Variables

Alternatively, you can set these in your `.env.prod` file:

```bash
QBITTORRENT_HOST=192.168.1.100
QBITTORRENT_PORT=8080
QBITTORRENT_USERNAME=admin
QBITTORRENT_PASSWORD=your_password
```

---

## 2. Automated Subtitle Support (Webhook)

You can configure qBittorrent to automatically notify Subro Web when a download is finished. This is done using the provided [qbittorrent-nox-webhook.sh](file:///home/user/subro_web/backend/scripts/qbittorrent-nox-webhook.sh) script.

### Prerequisites

- **API Key**: Generate an API key in the web interface (**Settings** -> **API Key** -> **Generate**).

### Step-by-Step Setup

1. **Locate the Script**:
   The script is located at `backend/scripts/qbittorrent-nox-webhook.sh`. If you are running in Docker, you may want to copy this script to a location accessible by your local qBittorrent installation.

2. **Configure the Script Environment**:
   The script reads its configuration from the repository root's `.env` file by default. Ensure the following variables are set:

   ```bash
   SUBRO_API_BASE_URL=https://your-domain.com/api/v1
   SUBRO_API_KEY=your_generated_api_key
   ```

   _Note: If qBittorrent is running on the same server, you can use `http://localhost:8000/api/v1`._

3. **Configure qBittorrent**:
   - Open your qBittorrent Web UI or Desktop Client.
   - Go to **Options** -> **Downloads**.
   - Find the section **"Run external program on torrent completion"**.
   - Check the box and enter the following command:
     ```bash
     /path/to/qbittorrent-nox-webhook.sh "%F"
     ```
     _Replace `/path/to/` with the actual absolute path to the script on your server._
     _`%F` is a qBittorrent parameter that passes the content path (folder or file)._

4. **Verify Permissions**:
   Ensure the script is executable by the user running qBittorrent:
   ```bash
   chmod +x /path/to/qbittorrent-nox-webhook.sh
   ```

### How it Works

When a torrent finishes:

1. qBittorrent calls the script with the download path.
2. The script sends a POST request to the Subro Web API to create a new subtitle download job.
3. Subro Web validates the path and enqueues a Celery task to download subtitles.
4. (Optional) If configured, the script can also trigger a Plex library refresh.

---

## 3. Plex Integration (Optional)

The webhook script also supports triggering a Plex library refresh. To enable this, add the following to your environment:

```bash
PLEX_BASE_URL=http://your-plex-ip:32400
PLEX_TOKEN=your_plex_token
PLEX_SECTION_IDS=1,2  # Comma-separated IDs of sections to refresh
```

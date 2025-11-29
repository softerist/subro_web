````markdown
# WebSocket API Documentation

## Log Streaming Endpoint

This endpoint provides real-time streaming of job logs, status updates, and execution metadata.

- **URL:** `/api/v1/ws/jobs/{job_id}/logs`
- **Method:** `GET` (Upgrade to WebSocket)
- **Authentication:** Required via Query Parameter

### Connection & Authentication

Since WebSockets do not support custom headers during the initial handshake in standard browser APIs, authentication is handled via a query parameter.

**URL Format:**
`ws://<host>/api/v1/ws/jobs/{job_id}/logs?token=<ACCESS_TOKEN>`

- **job_id**: The UUID of the job to monitor.
- **token**: A valid JWT Access Token.

**Connection Flow:**

1.  **Handshake:** Client initiates connection with the token.
2.  **Validation:** Server validates the token and checks if the user has permission (Owner or Admin) to view the job.
3.  **Accept/Reject:**
    - If valid, server accepts the connection and sends a `system` message.
    - If invalid/unauthorized, server closes connection with code `1008` (Policy Violation).

### Server-to-Client Message Structure

All messages sent by the server are JSON objects with a standard structure:

```json
{
  "type": "string",    // Message category: 'log', 'status', 'info', 'system', 'error'
  "payload": {         // specific data for this message type
    ...
  }
}
```
````

#### 1. Log Message (`type: "log"`)

Represents a line of output from the running script.

```json
{
  "type": "log",
  "payload": {
    "ts": "2023-10-27T10:30:01.123Z", // ISO 8601 Timestamp
    "stream": "stdout", // "stdout" or "stderr"
    "message": "Processing video file 1 of 5..."
  }
}
```

#### 2. Status Update (`type: "status"`)

Indicates a transition in the job's lifecycle.

**Running:**

```json
{
  "type": "status",
  "payload": {
    "status": "RUNNING",
    "ts": "2023-10-27T10:30:00.000Z",
    "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "started_at": "2023-10-27T10:30:00.000Z"
  }
}
```

**Succeeded:**

```json
{
  "type": "status",
  "payload": {
    "status": "SUCCEEDED",
    "ts": "2023-10-27T10:35:00.000Z",
    "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "completed_at": "2023-10-27T10:35:00.000Z",
    "exit_code": 0,
    "result_message": "Download complete."
  }
}
```

**Failed:**

```json
{
  "type": "status",
  "payload": {
    "status": "FAILED",
    "ts": "2023-10-27T10:35:00.000Z",
    "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "completed_at": "2023-10-27T10:35:00.000Z",
    "exit_code": 1,
    "error_message": "Network timeout connecting to provider.",
    "log_snippet": "Error: Connection refused..."
  }
}
```

**Cancelled:**

```json
{
  "type": "status",
  "payload": {
    "status": "CANCELLED",
    "ts": "2023-10-27T10:32:00.000Z",
    "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "completed_at": "2023-10-27T10:32:00.000Z",
    "exit_code": -100,
    "result_message": "Job cancelled by user request."
  }
}
```

#### 3. Info Message (`type: "info"`)

General information about the execution environment (e.g., process PID).

```json
{
  "type": "info",
  "payload": {
    "message": "Subtitle downloader process (PID: 1234) started execution.",
    "ts": "2023-10-27T10:30:00.500Z",
    "pid": 1234,
    "command": "python script.py ..."
  }
}
```

#### 4. System Message (`type: "system"`)

Sent immediately upon successful connection.

```json
{
  "type": "system",
  "payload": {
    "message": "Log streaming started.",
    "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "ts": "2023-10-27T10:29:59.000Z"
  }
}
```

#### 5. Error Message (`type: "error"`)

Sent if a protocol-level error occurs before the connection closes.

```json
{
  "type": "error",
  "payload": {
    "message": "Job not found or access denied.",
    "ts": "2023-10-27T10:29:59.000Z"
  }
}
```

### Client Implementation Guidelines

1.  **Reconnection:** Clients should implement automatic reconnection with exponential backoff if the connection drops unexpectedly.
2.  **State Sync:** When connecting, clients should first fetch the job details via HTTP GET `/api/v1/jobs/{id}` to get the current state, then connect WebSocket for _updates_.
3.  **Terminal States:** Once a `SUCCEEDED`, `FAILED`, or `CANCELLED` status message is received, the client should expect the connection to close shortly after (or can close it manually).

```

```

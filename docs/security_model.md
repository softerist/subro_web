# Security Model

This document outlines the security architecture, access controls, and policies enforced by the application to protect user data and system integrity.

## 1. Authentication

- **Method:** JSON Web Tokens (JWT).
- **Access Tokens:** Short-lived (default 30 mins), signed with `HS256`.
- **Refresh Tokens:** Long-lived (default 7 days), securely stored in `HttpOnly`, `Secure`, `SameSite=Strict` cookies.
- **MFA:** Time-based One-Time Password (TOTP) is supported and enforced for Superusers.

## 2. Role-Based Access Control (RBAC)

The system defines three distinct user roles with hierarchical permissions:

### 👑 Superuser

- **Scope:** Full System Access.
- **Capabilities:**
  - Create/Delete Admins and other Superusers.
  - Reset passwords for _any_ user.
  - Add _root_ storage paths (e.g., `/mnt/data`).
  - View all system logs and statistics.
- **Risk:** High. MFA is strongly recommended (and warned if missing).

### 🛡️ Admin

- **Scope:** User & Service Management.
- **Capabilities:**
  - Create/Edit/Delete **Standard** users.
  - Reset passwords for **Standard** users (but NOT Superusers).
  - Manage application settings (API keys, download defaults).
  - Add storage paths _only_ as subdirectories of existing roots (e.g., `/mnt/data/movies` if `/mnt/data` exists).
- **Restrictions:** Cannot modify Superuser accounts or add new root paths.

### 👤 Standard User

- **Scope:** Job Submission & Personal History.
- **Capabilities:**
  - Submit subtitle download jobs.
  - View own job history.
  - View global statistics.
  - Add storage paths _only_ as subdirectories of existing roots.
- **Restrictions:** Cannot access Settings, User Management, or System Logs.

## 3. Account Recovery & Password Policy

### Password Hashing

Passwords are hashed using **Argon2id**, a memory-hard function resistant to GPU-based cracking attacks.

### Force Password Change

Admins can flag a user to require a password change on their next login.

- **Mechanism:** A `force_password_change` flag is set on the user record.
- **Enforcement:** Upon login, the user is redirected to a restricted `/change-password` route. All other routes (Dashboard, Jobs, etc.) are blocked until the password is updated.
- **Resolution:** The flag is automatically cleared by the backend upon a successful password update.

### MFA Reset

Admins can disable MFA for a user via the "Reset Password" dialog.

- **Use Case:** A user has lost their Authenticator device.
- **Security:** This action deletes the server-side MFA secret, requiring the user to re-register MFA if they wish to use it again.

## 4. Data Encryption & Key Rotation

### Encrypted Settings + MFA Secrets

Sensitive settings (e.g., external API keys) and MFA secrets are encrypted at rest using
Fernet with a keyring defined by `DATA_ENCRYPTION_KEYS`.

- **Key order matters:** the first key is used for new encryption; all keys are tried for decryption.
- **Rotation flow:** prepend a new key, deploy (auto re-encrypt), verify, then remove the old key and deploy again.
- **Re-encryption:** handled by the deployment pipeline; can be controlled with
  `REENCRYPT_ON_DEPLOY` and `REENCRYPT_FORCE`.

### Token Secrets

Password reset and verification tokens can use dedicated secrets:

- `RESET_PASSWORD_TOKEN_SECRET`
- `VERIFICATION_TOKEN_SECRET`

If unset, they fall back to `SECRET_KEY`.

### API Keys

API keys are stored as HMAC-SHA256 hashes with a server-side `API_KEY_PEPPER`.
Only non-sensitive metadata (e.g., prefix/last4) is stored for display, and the raw
key is shown only once at creation. Rotating `API_KEY_PEPPER` requires reissuing keys.

## 5. Path Security (FileSystem Isolation)

To prevent unauthorized file system traversal or exposure of sensitive host directories, strict path management rules are enforced:

1. **Whitelist Approach:** Jobs can only write to explicit paths stored in the database.
2. **Root Path Authority:** Only **Superusers** can define new "Root" paths (e.g., `/`, `/mnt`, `/etc`).
3. **Subdirectory Delegation:** **Admins** and **Standard Users** can only add paths that are strictly _inside_ a pre-approved Root path.
   - _Example:_ If `/mnt/storage` is a Root Path:
     - ✅ User can add `/mnt/storage/movies`.
     - ❌ User CANNOT add `/mnt/secrets`.

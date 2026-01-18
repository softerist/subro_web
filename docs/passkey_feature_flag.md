# Feature Flag: Passkey UI

## Frontend Feature Flag

### Environment Variable

Add to `.env.local` (development) and production environment:

```bash
# Enable/disable Passkey UI
NEXT_PUBLIC_ENABLE_PASSKEYS=true
```

### Usage in SettingsPage.tsx

The `PasskeySettings` component is already integrated. To add feature flag support:

```tsx
// In SettingsPage.tsx
const isPasskeyEnabled = process.env.NEXT_PUBLIC_ENABLE_PASSKEYS === 'true';

{/* Security Tab Content */}
{currentTab === "security" && (
  <div className="space-y-6" ref={cardRef}>
    <PasswordSettings />
    <MfaSettings />
    {isPasskeyEnabled && <PasskeySettings />}  {/* ← Conditional render */}
  </div>
)}
```

## Backend Behavior (Current Implementation)

**Passkey API endpoints are ALWAYS enabled** regardless of frontend flag:

- ✅ `/passkey/login/*` endpoints — Always available (users with existing passkeys can login)
- ✅ `/passkey/register/*` endpoints — Always available (but UI is hidden if flag is off)
- ✅ `/passkey/list` endpoint — Always available
- ✅ `/passkey/{id}` endpoints (rename/delete) — Always available

### Rationale

- **No server-side flag** by default — Keeps backend simple
- **UI-only rollout** — Frontend controls who sees the feature
- **Existing users protected** — Users who registered passkeys before rollback can still manage them

### Optional: Backend Feature Flag

If strict server-side control is needed, add to `backend/app/core/config.py`:

```python
class Settings(BaseSettings):
    # ...
    PASSKEY_MANAGEMENT_ENABLED: bool = Field(
        default=True,
        description="Enable passkey management endpoints (register/delete)",
        validation_alias="PASSKEY_MANAGEMENT_ENABLED"
    )
```

Then in `backend/app/api/routers/passkey.py`:

```python
@router.post("/register/options")
async def get_registration_options(...):
    if not settings.PASSKEY_MANAGEMENT_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Passkey registration is temporarily disabled"
        )
    # ... existing logic
```

## Gradual Rollout Strategy

### Phase 1: Internal Testing (Flag OFF)
```bash
NEXT_PUBLIC_ENABLE_PASSKEYS=false  # Default OFF
```

- Deploy to production with flag OFF
- Enable for internal team only (via admin override or separate env)
- Test full flow in production environment

### Phase 2: Canary Release (5%)
```bash
# Use feature flag service (LaunchDarkly, Split.io, etc.)
# OR implement simple percentage rollout:

const isPasskeyEnabled =
  process.env.NEXT_PUBLIC_ENABLE_PASSKEYS === 'true' ||
  (user?.id && parseInt(user.id.slice(-2), 16) < 13);  // ~5% of users
```

### Phase 3: Progressive Rollout
- 25% → 50% → 100%
- Monitor success rates at each stage
- Halt and investigate if metrics drop

### Phase 4: Full Release
```bash
NEXT_PUBLIC_ENABLE_PASSKEYS=true  # All users
```

## Rollback Plan

If issues arise:

1. **Immediate**: Set `NEXT_PUBLIC_ENABLE_PASSKEYS=false`
2. **Redeploy frontend** (environment variable change)
3. **Verify** Settings page no longer shows Passkeys section
4. **Investigate** issue before re-enabling

**Note**: Existing passkeys remain functional — users can still login with them

## Testing Flag States

### Flag ON
- [ ] Navigate to Settings → Security
- [ ] Verify Passkeys section visible
- [ ] Test full registration flow
- [ ] Test rename/delete

### Flag OFF
- [ ] Navigate to Settings → Security
- [ ] Verify NO Passkeys section
- [ ] Verify existing passkey login still works (if user has passkeys)
- [ ] Verify direct API access still works (for existing users)

## Future: Multi-Environment Flags

For larger deployments, use a feature flag service:

```tsx
import { useFeatureFlag } from '@/hooks/useFeatureFlags';

export function SettingsPage() {
  const isPasskeyEnabled = useFeatureFlag('passkeys-ui', false);

  return (
    // ...
    {isPasskeyEnabled && <PasskeySettings />}
  );
}
```

This allows:
- **Per-user rollout** (A/B testing)
- **Real-time toggles** (no redeploy needed)
- **Analytics integration**
- **Kill switch** for emergencies

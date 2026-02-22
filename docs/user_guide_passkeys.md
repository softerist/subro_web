# User Guide: Passkeys

## What are Passkeys?

Passkeys are a safer and easier way to sign in without remembering passwords. They use your fingerprint, face, or security key to verify it's really you.

### Benefits

- **More secure**: Can't be phished or stolen like passwords
- **Faster**: Sign in with just your fingerprint or face
- **Easier**: No passwords to remember
- **Cross-device**: Sync across your devices (iPhone, Mac, etc.)

## Setting Up a Passkey

### On Desktop (Windows/Mac/Linux)

1. Sign in to your account with your password
2. Go to **Settings** → **Security**
3. Click **"Add Passkey"**
4. Give your passkey a name (optional) – e.g., "MacBook Pro"
5. Your browser will prompt you to:
   - **Windows**: Use Windows Hello (fingerprint, face, or PIN)
   - **Mac**: Use Touch ID or password
   - **Linux**: Use your authenticator

6. Done! You can now sign in with your passkey

### On Mobile (iPhone/Android)

1. Sign in to your account with your password
2. Go to **Settings** → **Security**
3. Tap **"Add Passkey"**
4. Your device will prompt you to:
   - **iPhone**: Use Face ID or Touch ID
   - **Android**: Use fingerprint or screen lock

5. Done! Your passkey is saved

## Using Your Passkey to Sign In

1. Go to the sign-in page
2. Click **"Sign in with Passkey"**
3. Your browser will show a prompt
4. Verify with your fingerprint, face, or security key
5. You're signed in!

## Managing Your Passkeys

### Rename a Passkey

1. Go to **Settings** → **Security**
2. Find the passkey in your list
3. Click the **edit icon** (pencil)
4. Enter a new name
5. Click the **check mark** to save

### Delete a Passkey

1. Go to **Settings** → **Security**
2. Find the passkey in your list
3. Click the **delete icon** (trash)
4. Confirm deletion

**Note**: You can still sign in with your password if you delete all your passkeys.

## Troubleshooting

### "Browser doesn't support passkeys"

**Solution**: Use a modern browser:

- Chrome 109+
- Safari 16+
- Firefox 119+
- Edge 109+

### "Passkey not working after device reset"

**Cause**: Factory resets can erase passkeys stored on your device.

**Solution**:

- Check if passkeys synced via iCloud Keychain (iPhone/Mac) or Google Password Manager (Android/Chrome)
- If not synced, you'll need to create a new passkey

### "Can't find passkey on new device"

**Synced passkeys** (iPhone/Mac with iCloud, Android/Chrome with Google account):

- Wait a few minutes for sync
- Make sure you're signed into the same account

**Device-specific passkeys** (security keys, Windows Hello):

- These don't sync – use them on the original device only

### "Registration always fails"

**Possible causes**:

- Not using HTTPS in production
- Browser extension conflicts
- Privacy mode/incognito (some browsers don't support passkeys in private mode)

**Solutions**:

- Try a different browser
- Disable extensions temporarily
- Use normal browsing mode (not private/incognito)

### "Works on one site but not another"

Passkeys are specific to each website. You need to create a new passkey for each site you use.

## Security Tips

✅ **Enable device lock**: Passkeys are protected by your device's security (PIN, fingerprint, etc.)

✅ **Keep backups**: Use synced passkeys (iCloud Keychain, Google Password Manager) so you don't lose access

✅ **Don't share devices**: Anyone with access to your unlocked device can use your passkeys

✅ **Keep password as backup**: Don't disable password login until you're comfortable with passkeys

## FAQ

**Q: Can I use the same passkey on multiple devices?**

A: If you use synced passkeys (iCloud, Google), yes! Otherwise, you'll need to create a passkey on each device.

**Q: What happens if I lose my device?**

A:

- **Synced passkeys**: They'll sync to your new device automatically
- **Device-specific**: You'll need to sign in with your password and create a new passkey

**Q: Are passkeys stored on the website's server?**

A: No! Passkeys are stored on your device or in your cloud account (iCloud, Google). The website only stores a public key that can't be used to sign in.

**Q: Can I still use my password?**

A: Yes! Passkeys are an additional option. You can always sign in with your password.

**Q: Do I need internet to use a passkey?**

A: Yes, you need internet to sign in to websites. But the passkey verification happens locally on your device.

## Need Help?

If you're still having trouble, contact support with:

- Device type (iPhone 15, Windows 11, etc.)
- Browser and version
- Error message (if any)
- What you were trying to do

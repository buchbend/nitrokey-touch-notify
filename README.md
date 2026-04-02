# nitrokey-touch-notify

Desktop notification when a hardware security key (Nitrokey, YubiKey, etc.) is waiting for physical touch during SSH authentication.

## How it works

Runs as a transparent SSH agent proxy. Intercepts `SSH2_AGENTC_SIGN_REQUEST` messages and shows a GNOME desktop notification if the signing operation takes longer than 300ms (indicating the key is waiting for touch, not a fast software key).

- No dependencies beyond Python 3.10+ and `gdbus` (part of GLib, present on all GNOME systems)
- Notifications auto-dismiss after 5 seconds
- Works on GNOME/Wayland (uses D-Bus `CloseNotification` to dismiss critical banners)

## Install

```bash
make install
make enable
```

Add to `~/.bashrc`:
```bash
source ~/.config/nitrokey-touch-notify/shell-integration.sh
```

## Usage

```
make help       # show all targets
make status     # check service
make log        # follow logs
make restart    # restart after editing
make uninstall  # remove everything
```

## Manual run (for testing)

```bash
./nitrokey_touch_notify.py
# In another terminal:
export SSH_AUTH_SOCK="$XDG_RUNTIME_DIR/nitrokey-touch-proxy.sock"
ssh somehost   # notification should appear when key blinks
```

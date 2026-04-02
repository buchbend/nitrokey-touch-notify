# Source this from .bashrc / .zshrc
# Redirects SSH_AUTH_SOCK to the touch-notify proxy if it's running

_NITROKEY_PROXY_SOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/nitrokey-touch-proxy.sock"

if [ -S "$_NITROKEY_PROXY_SOCK" ]; then
    export SSH_AUTH_SOCK="$_NITROKEY_PROXY_SOCK"
fi

unset _NITROKEY_PROXY_SOCK

#!/usr/bin/env python3
"""nitrokey-touch-notify — Desktop notification when a hardware key awaits touch.

Sits as a transparent proxy between SSH clients and the real ssh-agent.
When a signing request takes longer than 300ms (indicating the key is
waiting for physical touch), a desktop notification is shown.

Usage:
    # Start the proxy (reads SSH_AUTH_SOCK, creates proxy socket)
    nitrokey-touch-notify

    # Then in your shell:
    export SSH_AUTH_SOCK="$XDG_RUNTIME_DIR/nitrokey-touch-proxy.sock"
"""

from __future__ import annotations

import asyncio
import os
import re
import signal
import struct
import sys
from pathlib import Path

# SSH agent protocol message types
SSH2_AGENTC_SIGN_REQUEST = 13
SSH2_AGENT_SIGN_RESPONSE = 14

# Only show notification if signing takes longer than this (filters software keys)
TOUCH_DELAY_S = 0.3
TOUCH_TIMEOUT_S = 5.0

_last_notification_id: int = 0


async def _notify(urgency: str, timeout_ms: int, body: str) -> None:
    """Send notification via D-Bus (async) and track the notification ID."""
    global _last_notification_id
    urgency_byte = 2 if urgency == "critical" else 1
    try:
        proc = await asyncio.create_subprocess_exec(
            "gdbus", "call", "--session",
            "--dest=org.freedesktop.Notifications",
            "--object-path=/org/freedesktop/Notifications",
            "--method=org.freedesktop.Notifications.Notify",
            "nitrokey-touch-notify",
            str(_last_notification_id),
            "dialog-password",
            "Nitrokey",
            body,
            "[]",
            f"{{'urgency': <byte {urgency_byte}>}}",
            str(timeout_ms),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2)
        # gdbus returns "(uint32 <id>,)\n"
        if stdout:
            match = re.search(rb"\d+,\)", stdout)
            if match:
                _last_notification_id = int(match.group()[:-2])
    except (asyncio.TimeoutError, ValueError, OSError):
        pass


async def _close_notification() -> None:
    """Close the notification by ID via D-Bus."""
    if _last_notification_id:
        try:
            proc = await asyncio.create_subprocess_exec(
                "gdbus", "call", "--session",
                "--dest=org.freedesktop.Notifications",
                "--object-path=/org/freedesktop/Notifications",
                "--method=org.freedesktop.Notifications.CloseNotification",
                str(_last_notification_id),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=2)
        except (asyncio.TimeoutError, OSError):
            pass


class ConnectionState:
    """Track sign request/response state per connection."""

    def __init__(self) -> None:
        self._notification_shown = False
        self._pending_task: asyncio.Task | None = None
        self._dismiss_task: asyncio.Task | None = None

    def on_sign_request(self) -> None:
        if self._pending_task and not self._pending_task.done():
            self._pending_task.cancel()
        if self._dismiss_task and not self._dismiss_task.done():
            self._dismiss_task.cancel()
        self._pending_task = asyncio.create_task(self._delayed_notify())

    async def _delayed_notify(self) -> None:
        await asyncio.sleep(TOUCH_DELAY_S)
        await _notify("critical", 0, "Touch required for authentication")
        self._notification_shown = True
        self._dismiss_task = asyncio.create_task(self._auto_dismiss())

    async def _auto_dismiss(self) -> None:
        await asyncio.sleep(TOUCH_TIMEOUT_S)
        if self._notification_shown:
            await _close_notification()
            self._notification_shown = False

    def on_sign_response(self) -> None:
        if self._pending_task and not self._pending_task.done():
            self._pending_task.cancel()
        if self._dismiss_task and not self._dismiss_task.done():
            self._dismiss_task.cancel()
        if self._notification_shown:
            asyncio.create_task(self._do_touch_done())
            self._notification_shown = False

    async def _do_touch_done(self) -> None:
        await _close_notification()
        await _notify("normal", 3000, "Touch confirmed")


async def forward(
    reader: asyncio.StreamReader,
    peer_writer: asyncio.StreamWriter,
    state: ConnectionState,
    direction: str,
) -> None:
    """Forward data, parsing SSH agent protocol to detect sign operations."""
    buf = b""
    try:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            buf += data

            # Parse SSH agent protocol: 4-byte big-endian length + type byte + payload
            while len(buf) >= 5:
                msg_len = struct.unpack(">I", buf[:4])[0]
                if len(buf) < 4 + msg_len:
                    break
                msg_type = buf[4]

                if direction == "client" and msg_type == SSH2_AGENTC_SIGN_REQUEST:
                    state.on_sign_request()
                elif direction == "agent" and msg_type == SSH2_AGENT_SIGN_RESPONSE:
                    state.on_sign_response()

                buf = buf[4 + msg_len:]

            peer_writer.write(data)
            await peer_writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        peer_writer.close()


async def handle_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    real_agent_sock: str,
) -> None:
    try:
        agent_reader, agent_writer = await asyncio.open_unix_connection(
            real_agent_sock
        )
    except (ConnectionRefusedError, FileNotFoundError) as exc:
        print(f"Cannot connect to agent: {exc}", file=sys.stderr)
        client_writer.close()
        return

    state = ConnectionState()
    await asyncio.gather(
        forward(client_reader, agent_writer, state, "client"),
        forward(agent_reader, client_writer, state, "agent"),
    )


async def serve(real_agent_sock: str, proxy_sock: str) -> None:
    proxy_path = Path(proxy_sock)
    proxy_path.unlink(missing_ok=True)

    server = await asyncio.start_unix_server(
        lambda r, w: handle_client(r, w, real_agent_sock),
        path=str(proxy_path),
    )
    proxy_path.chmod(0o600)

    print(f"Proxying {proxy_sock} -> {real_agent_sock}")
    print(f"Set in your shell:  export SSH_AUTH_SOCK={proxy_sock}")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    async with server:
        await stop.wait()

    proxy_path.unlink(missing_ok=True)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Desktop notification when Nitrokey awaits touch"
    )
    parser.add_argument(
        "--agent-sock",
        default=os.environ.get("SSH_AUTH_SOCK"),
        help="Real SSH agent socket (default: $SSH_AUTH_SOCK)",
    )
    parser.add_argument(
        "--proxy-sock",
        default=os.path.join(
            os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"),
            "nitrokey-touch-proxy.sock",
        ),
        help="Proxy socket path",
    )
    args = parser.parse_args()

    if not args.agent_sock:
        print(
            "Error: SSH_AUTH_SOCK not set and --agent-sock not provided",
            file=sys.stderr,
        )
        sys.exit(1)

    if not Path(args.agent_sock).exists():
        print(f"Error: Agent socket not found: {args.agent_sock}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(serve(args.agent_sock, args.proxy_sock))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import secrets
import socket

from jarvis_mrb.server_config import ServerConfig, load_server_config, save_server_config


def _local_ipv4_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET):
            address = item[4][0]
            if address and not address.startswith("127."):
                addresses.add(address)
    except OSError:
        pass
    return sorted(addresses)


def configure_remote_access(*, rotate: bool = False) -> tuple[ServerConfig, bool]:
    """Idempotent setup: do not break paired clients on a second run."""
    existing = load_server_config()
    was_rotated = rotate or not existing.api_token
    token = secrets.token_urlsafe(32) if was_rotated else existing.api_token
    config = ServerConfig(bind_host="0.0.0.0", port=existing.port, api_token=token)
    save_server_config(config)
    return config, was_rotated


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure the Horus private-network backend.")
    parser.add_argument("--rotate", action="store_true", help="Replace the saved API token; reconnect every client.")
    args = parser.parse_args()
    config, changed = configure_remote_access(rotate=args.rotate)

    print("Horus remote access is configured for private-network use.")
    print("API token " + ("created/rotated" if changed else "reused") + ":")
    print(config.api_token)
    print()
    addresses = _local_ipv4_addresses()
    if addresses:
        print("Possible iPhone server URLs while on the same Wi-Fi:")
        for address in addresses:
            print(f"  http://{address}:{config.port}")
    else:
        print(f"Use this PC's private LAN or Tailscale IP as http://<ip>:{config.port}")
    print()
    print("Restart the Horus service after changing configuration.")
    print("Do not forward the service port to the public Internet.")
    print("LAN HTTP is not end-to-end encrypted: use only networks you trust.")


if __name__ == "__main__":
    main()

from __future__ import annotations

import secrets
import socket

from jarvis_mrb.server_config import ServerConfig, save_server_config


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


def main() -> None:
    token = secrets.token_urlsafe(32)
    path = save_server_config(ServerConfig(bind_host="0.0.0.0", port=8765, api_token=token))

    print("Jarvis remote access is configured for private-network use.")
    print(f"Saved server configuration to: {path}")
    print()
    print("API token (copy this into the Jarvis iPhone app):")
    print(token)
    print()
    addresses = _local_ipv4_addresses()
    if addresses:
        print("Possible iPhone server URLs while on the same Wi-Fi:")
        for address in addresses:
            print(f"  http://{address}:8765")
    else:
        print("Use this PC's private LAN or Tailscale IP as http://<ip>:8765")
    print()
    print("Restart the Jarvis service after running this command.")
    print("Do not forward port 8765 from your router to the public Internet.")


if __name__ == "__main__":
    main()

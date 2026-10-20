"""Horus Windows desktop launcher packaged as Horus.exe (no Python required)."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

PORT = 8765


def service_running() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1.5) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def start_service() -> bool:
    if service_running():
        return True
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    executable = sys.executable
    subprocess.Popen(
        [executable, "--service"],
        cwd=os.path.dirname(executable),
        creationflags=flags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    for _ in range(60):
        if service_running():
            return True
        time.sleep(0.5)
    return False


def _local_ipv4() -> str:
    try:
        for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = result[4][0]
            if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
    except OSError:
        pass
    return "PC_LAN_IP"


def ui() -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk
    from jarvis_mrb.inference import DEFAULT_MODELS, configure_inference, inference_status
    from jarvis_mrb.remote_setup import configure_remote_access
    from jarvis_mrb.server_config import load_server_config

    root = tk.Tk()
    root.title("Horus · Setup")
    root.geometry("600x440")
    root.minsize(550, 400)
    root.option_add("*Font", "Segoe UI 10")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    frame = ttk.Frame(root, padding=22)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.columnconfigure(0, weight=1)
    ttk.Label(frame, text="Horus", font=("Segoe UI", 22, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(frame, text="Local-first assistant · one-time configuration").grid(row=1, column=0, sticky="w", pady=(0, 15))
    tabs = ttk.Notebook(frame)
    tabs.grid(row=2, column=0, sticky="nsew")
    frame.rowconfigure(2, weight=1)

    ai = ttk.Frame(tabs, padding=15)
    ai.columnconfigure(1, weight=1)
    tabs.add(ai, text="AI provider")
    state = inference_status()
    provider = tk.StringVar(value=state["provider"])
    model = tk.StringVar(value=state["model"])
    key = tk.StringVar()
    notice = tk.StringVar(value="Local Ollama needs no API key. BYOK keys stay in Windows Credential Manager.")

    ttk.Label(ai, text="Provider").grid(row=0, column=0, sticky="w", pady=9)
    providers = ttk.Combobox(ai, textvariable=provider, values=("ollama", "openai", "anthropic", "openrouter"), state="readonly")
    providers.grid(row=0, column=1, sticky="ew", pady=9)
    ttk.Label(ai, text="Model").grid(row=1, column=0, sticky="w", pady=9)
    ttk.Entry(ai, textvariable=model).grid(row=1, column=1, sticky="ew", pady=9)
    ttk.Label(ai, text="API key").grid(row=2, column=0, sticky="w", pady=9)
    ttk.Entry(ai, textvariable=key, show="•").grid(row=2, column=1, sticky="ew", pady=9)
    ttk.Label(ai, textvariable=notice, wraplength=450).grid(row=4, column=0, columnspan=2, sticky="w", pady=(16, 0))

    def changed_provider(_=None):
        name = provider.get()
        model.set(DEFAULT_MODELS.get(name, "qwen3:8b"))
        key.set("")
    providers.bind("<<ComboboxSelected>>", changed_provider)

    def save():
        try:
            value = key.get().strip()
            saved = configure_inference(provider.get(), model.get(), value if value else None)
            key.set("")
            notice.set(f"Saved: {saved['provider']} / {saved['model']}. "
                       + ("API key ready." if saved["key_configured"] else "API key missing."))
        except Exception as exc:
            messagebox.showerror("Horus setup", str(exc), parent=root)
    ttk.Button(ai, text="Save AI settings", command=save).grid(row=3, column=1, sticky="e", pady=13)

    network = ttk.Frame(tabs, padding=15)
    network.columnconfigure(0, weight=1)
    tabs.add(network, text="Phone connection")
    ttk.Label(network, text="Optional. For a phone on the same trusted private network.", wraplength=450).grid(row=0, column=0, sticky="w", pady=(0, 12))
    network_notice = tk.StringVar(value="LAN access is off until you enable it. HTTP is not encrypted.")
    ttk.Label(network, textvariable=network_notice, wraplength=450).grid(row=1, column=0, sticky="w")
    token_text = tk.StringVar(value="")
    url_text = tk.StringVar(value="")

    def enable_lan():
        if not messagebox.askyesno("Private network only", "Enable Horus on all PC network interfaces? Never port-forward port 8765. Use a trusted LAN or an encrypted reverse proxy.", parent=root):
            return
        config, rotated = configure_remote_access()
        url_text.set(f"http://{_local_ipv4()}:{config.port}")
        token_text.set(config.api_token)
        network_notice.set("LAN configured. Restart Horus for new bind settings to take effect." if rotated else "LAN configured; token reused.")

    def copy_value(value):
        root.clipboard_clear()
        root.clipboard_append(value)
        root.update()

    ttk.Button(network, text="Enable private LAN connection", command=enable_lan).grid(row=2, column=0, sticky="w", pady=(15, 6))
    ttk.Button(network, text="Copy LAN URL", command=lambda: copy_value(url_text.get())).grid(row=3, column=0, sticky="w", pady=4)
    ttk.Button(network, text="Copy API token", command=lambda: copy_value(token_text.get())).grid(row=4, column=0, sticky="w", pady=4)
    ttk.Label(network, text="Never share the token. Configure Horus iPhone Settings with the LAN URL and token.", wraplength=450).grid(row=5, column=0, sticky="w", pady=(15, 0))

    call = ttk.Frame(tabs, padding=15)
    tabs.add(call, text="Callless")
    ttk.Label(call, text="Callless uses a shared Horus hub for contacts, presence and encrypted peer-to-peer browser audio. A public deployment needs HTTPS and typically a TURN relay.", wraplength=465).pack(anchor="w", pady=8)
    def open_callless():
        if start_service():
            webbrowser.open(f"http://127.0.0.1:{PORT}/callless/")
        else:
            messagebox.showerror("Service unavailable", "Horus service failed to start; review local configuration.", parent=root)
    ttk.Button(call, text="Open Callless", command=open_callless).pack(anchor="w", pady=12)

    def start_and_open():
        if start_service():
            webbrowser.open(f"http://127.0.0.1:{PORT}/callless/")
        else:
            messagebox.showerror("Service unavailable", "Horus could not start its service.", parent=root)
    ttk.Button(frame, text="Start Horus", command=start_and_open).grid(row=3, column=0, sticky="e", pady=(16, 0))
    root.mainloop()


def main() -> None:
    if "--service" in sys.argv:
        from jarvis_mrb.service import main as run_service
        run_service()
    elif "--self-test" in sys.argv:
        from jarvis_mrb.inference import inference_status
        from jarvis_mrb.service import app
        assert app and inference_status()["provider"]
    else:
        ui()


if __name__ == "__main__":
    main()

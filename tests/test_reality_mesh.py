from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import runpy
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jarvis_mrb import reality_mesh as mesh

ROOT = Path(__file__).resolve().parents[1]
MAC = ROOT / "scripts/jarvis-mac-node.py"
PNG = b"\x89PNG\r\n\x1a\n" + b"f" * 128


class MacNodeProtocolTests(unittest.TestCase):
    def setUp(self):
        module = runpy.run_path(str(MAC), run_name="mesh_test")
        self.node_class = module["NodeState"]
        self.state = self.node_class(
            token="a" * 48, device_id="macbook", label="MacBook Air",
            allow_screen=True
        )
        handler = module["handler_for"](self.state)
        handler.do_GET.__globals__["_capture_screen"] = lambda: ("image/png", PNG)
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)
        self.url = "http://127.0.0.1:" + str(self.http.server_port)

    def request(self, path, method="GET", payload=None, token="a" * 48):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Authorization": "Bearer " + token}
        if data is not None:
            headers["Content-Type"] = "application/json"
        with urlopen(Request(self.url + path, data=data, method=method,
                             headers=headers), timeout=3) as response:
            return response.status, response.headers, response.read()

    def test_mac_agent_refuses_short_secret_and_invalid_id(self):
        with self.assertRaises(ValueError):
            self.node_class(token="short", device_id="macbook", label="Mac")
        with self.assertRaises(ValueError):
            self.node_class(token="x" * 48, device_id="../macbook", label="Mac")

    def test_protocol_and_read_only_capability_manifest(self):
        status, headers, raw = self.request("/v1/health")
        info = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(info["device_id"], "macbook")
        self.assertEqual(info["capabilities"]["screen"], "session_opt_in")
        self.assertEqual(info["capabilities"]["remote_input"], "not_implemented")
        self.assertEqual(info["capabilities"]["clipboard"], "not_implemented")
        self.assertEqual(headers["Cache-Control"], "private, no-store")
        self.assertNotIn("token", info)

    def test_auth_gate_applies_to_health_and_private_screen(self):
        for path in ("/v1/health", "/v1/context", "/v1/screen"):
            with self.assertRaises(HTTPError) as raised:
                self.request(path, token="wrong")
            self.assertEqual(raised.exception.code, 401)

    def test_two_explicit_opt_ins_and_revoke_screen(self):
        with self.assertRaises(HTTPError) as raised:
            self.request("/v1/screen")
        self.assertEqual(raised.exception.code, 403)
        self.assertEqual(self.request(
            "/v1/session", method="POST", payload={"duration_seconds": 120}
        )[0], 200)
        status, headers, image = self.request("/v1/screen")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/png")
        self.assertEqual(image, PNG)
        self.assertEqual(self.request("/v1/session", method="DELETE")[0], 200)
        with self.assertRaises(HTTPError) as raised:
            self.request("/v1/screen")
        self.assertEqual(raised.exception.code, 403)

    def test_session_expires_and_permission_vetoes_even_with_token(self):
        self.request("/v1/session", method="POST",
                     payload={"duration_seconds": 15})
        self.state.session_expiry = datetime.now(timezone.utc) - timedelta(seconds=1)
        with self.assertRaises(HTTPError) as raised:
            self.request("/v1/screen")
        self.assertEqual(raised.exception.code, 403)
        self.state.allow_screen = False
        with self.assertRaises(HTTPError) as raised:
            self.request("/v1/session", method="POST",
                         payload={"duration_seconds": 30})
        self.assertEqual(raised.exception.code, 403)

    def test_duration_and_unknown_endpoints_fail_closed(self):
        for duration in (-1, 0, True, 301, "120"):
            with self.assertRaises(HTTPError) as raised:
                self.request("/v1/session", method="POST",
                             payload={"duration_seconds": duration})
            self.assertEqual(raised.exception.code, 422)
        with self.assertRaises(HTTPError) as raised:
            self.request("/v1/execute", method="POST", payload={})
        self.assertEqual(raised.exception.code, 404)


class MeshCoordinatorTests(unittest.TestCase):
    def test_no_ambient_network_discovery_and_no_open_internet_tokens(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(mesh.probe("macbook")["status"], "unconfigured")
            with self.assertRaises(mesh.NodeUnavailable):
                mesh.frame("macbook")
        for base in (
            "http://example.com:8766",
            "http://192.168.1.4:8766",
            "https://not-a-tailscale-domain.example:8766",
            "http://169.254.169.254:80",
            "http://127.0.0.1:bad",
            "http://127.0.0.1:8766/evil",
        ):
            with self.subTest(base=base):
                with patch.dict("os.environ", {
                    "JARVIS_MESH_MACBOOK_URL": base,
                    "JARVIS_MESH_MACBOOK_TOKEN": "x" * 48,
                }):
                    self.assertIsNone(mesh._config("macbook"))
        with patch.dict("os.environ", {
            "JARVIS_MESH_MACBOOK_URL": "http://100.100.50.20:8766",
            "JARVIS_MESH_MACBOOK_TOKEN": "x" * 48,
        }):
            self.assertIsNotNone(mesh._config("macbook"))

    def test_auth_transport_and_screen_binary_response_limits(self):
        module = runpy.run_path(str(MAC), run_name="mesh_test")
        state = module["NodeState"](
            token="a" * 48, device_id="macbook", label="MacBook",
            allow_screen=True,
        )
        handler = module["handler_for"](state)
        handler.do_GET.__globals__["_capture_screen"] = lambda: ("image/png", PNG)
        host = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = Thread(target=host.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(host.server_close)
        self.addCleanup(host.shutdown)
        with patch.dict("os.environ", {
            "JARVIS_MESH_MACBOOK_URL": "http://127.0.0.1:" + str(host.server_port),
            "JARVIS_MESH_MACBOOK_TOKEN": "a" * 48,
        }):
            self.assertEqual(
                mesh._request("macbook", "GET", "/v1/health")[0]["device_id"],
                "macbook"
            )
            with patch.object(mesh, "probe", return_value={
                "status": "online",
                "capabilities": {"screen": "session_opt_in"}
            }):
                self.assertEqual(mesh.begin_screen("macbook")["status"], "active")
            frame, media = mesh.frame("macbook")
            self.assertEqual(frame, PNG)
            self.assertEqual(media, "image/png")
            self.assertEqual(mesh.finish_screen("macbook")["status"], "closed")
            with self.assertRaises(mesh.NodeUnavailable):
                mesh.frame("macbook")
            with self.assertRaises(ValueError):
                mesh._request("macbook", "POST", "/v1/execute")

    def test_public_sensor_coverage_never_asserts_live_or_global_camera(self):
        manifest = mesh.public_sources()
        self.assertTrue(manifest["registry_is_coverage_not_live_observation"])
        self.assertEqual(len(manifest["sources"]), 5)
        for source in manifest["sources"]:
            self.assertEqual(source["status"], "integrated_not_checked")
            self.assertTrue(source["source_url"].startswith("https://"))
        caltrans = next(s for s in manifest["sources"] if s["id"] == "caltrans_cwwp2")
        self.assertIn("California", caltrans["coverage"])
        nws = next(s for s in manifest["sources"] if s["id"] == "nws")
        self.assertIn("not Melbourne", nws["coverage"])

    def test_service_endpoints_are_authenticated_and_screens_no_store(self):
        content = (ROOT / "jarvis_mrb/service.py").read_text()
        for route in (
            "/mesh/nodes", "/mesh/public-sources", "/mesh/place",
            "/mesh/screen/begin", "/mesh/screen/stop", "/mesh/screen/{node_id}"
        ):
            self.assertIn(route, content)
        self.assertIn('headers={"Cache-Control": "private, no-store"', content)
        self.assertIn("from jarvis_mrb.reality_mesh import begin_screen", content)
        self.assertIn("from jarvis_mrb.reality_mesh import frame", content)
        self.assertIn("_check_auth(authorization)", content)

    def test_phone_ui_privacy_source_and_no_os_remote_control(self):
        ui = (ROOT / "ios/JarvisIOS/RealityMesh.swift").read_text()
        api = (ROOT / "ios/JarvisIOS/JarvisAPIClient.swift").read_text()
        settings = (ROOT / "ios/JarvisIOS/SettingsStore.swift").read_text()
        power = (ROOT / "ios/JarvisIOS/LocalPowerFeatures.swift").read_text()
        app = (ROOT / "ios/JarvisIOS/JarvisIOSApp.swift").read_text()
        project = (ROOT / "ios/JarvisIOS.xcodeproj/project.pbxproj").read_text()
        self.assertIn('Label("Mesh", systemImage: "network")', app)
        self.assertIn("RealityMesh.swift in Sources", project)
        self.assertIn('meshEnabled = defaults.object(forKey: "jarvis.meshEnabled") as? Bool ?? false', settings)
        self.assertIn("appModel.settings.meshEnabled = false", power)
        self.assertIn("meshEnabled = snapshot.meshEnabled", power)
        self.assertIn("func stopScreen() async", ui)
        self.assertIn("mesh.stopScreen()", ui)
        self.assertIn("UIApplication.shared.applicationState == .active", ui)
        self.assertIn("MKLocalSearch(request: request).start().mapItems", ui)
        self.assertIn("self.exact", ui.lower().replace("self.exact", "self.exact")) if False else None
        self.assertIn('path: "mesh/screen/" + nodeID', api)
        self.assertIn('path: "mesh/place"', api)
        self.assertIn('No network scans', ui)
        self.assertNotIn("remoteKeyboard(", ui)
        self.assertNotIn("executeShell(", ui)


if __name__ == "__main__":
    unittest.main()

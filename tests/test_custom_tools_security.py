from __future__ import annotations

import socket
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jarvis_mrb.custom_tools as custom_tools


class CustomToolsSecurityTests(unittest.TestCase):
    def test_allowed_hosts_reject_private_literal_and_host_syntax_smuggling(self) -> None:
        for value in (
            "127.0.0.1",
            "10.0.0.8",
            "169.254.169.254",
            "::1",
            "https://api.example.com",
            "api.example.com:443",
            "user@api.example.com",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    custom_tools._normalize_allowed_hosts([value])

    def test_safe_plan_is_canonicalized_without_network_access(self) -> None:
        method, url, headers, body = custom_tools._validate_plan(
            {
                "method": "GET",
                "url": "https://API.Example.COM/v1/status?city=Pasadena",
                "headers": {"Accept": "application/json"},
                "body": None,
            },
            hosts=["api.example.com"],
            risk="read",
        )
        self.assertEqual(method, "GET")
        self.assertEqual(url, "https://API.Example.COM/v1/status?city=Pasadena")
        self.assertEqual(headers, {"Accept": "application/json"})
        self.assertIsNone(body)

    def test_plan_rejects_credentials_and_secret_channels(self) -> None:
        cases = [
            {
                "method": "GET",
                "url": "https://user:password@api.example.com/v1",
                "headers": {},
                "body": None,
            },
            {
                "method": "GET",
                "url": "https://api.example.com/v1?access_token=secret",
                "headers": {},
                "body": None,
            },
            {
                "method": "GET",
                "url": "https://api.example.com/v1",
                "headers": {"X-Auth-Token": "secret"},
                "body": None,
            },
            {
                "method": "POST",
                "url": "https://api.example.com/v1",
                "headers": {},
                "body": {"client_secret": "secret"},
            },
        ]
        for plan in cases:
            with self.subTest(plan=plan):
                with self.assertRaises(ValueError):
                    custom_tools._validate_plan(
                        plan,
                        hosts=["api.example.com"],
                        risk="external_write",
                    )

    def test_plan_rejects_host_and_framing_header_override(self) -> None:
        for header in (
            "Host",
            "Content-Length",
            "Transfer-Encoding",
            "Connection",
            "Proxy-Connection",
            "Upgrade",
        ):
            with self.subTest(header=header):
                with self.assertRaisesRegex(ValueError, "protected HTTP header"):
                    custom_tools._validate_plan(
                        {
                            "method": "GET",
                            "url": "https://api.example.com/v1",
                            "headers": {header: "attacker-controlled"},
                            "body": None,
                        },
                        hosts=["api.example.com"],
                        risk="read",
                    )

    def test_plan_rejects_header_crlf(self) -> None:
        with self.assertRaisesRegex(ValueError, "CR/LF"):
            custom_tools._validate_plan(
                {
                    "method": "GET",
                    "url": "https://api.example.com/v1",
                    "headers": {"X-Note": "safe\r\nHost: evil.example"},
                    "body": None,
                },
                hosts=["api.example.com"],
                risk="read",
            )

    def test_dns_resolution_rejects_any_nonpublic_answer(self) -> None:
        answers = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("93.184.216.34", 443),
            ),
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("127.0.0.1", 443),
            ),
        ]
        with patch.object(socket, "getaddrinfo", return_value=answers):
            with self.assertRaisesRegex(ValueError, "non-public"):
                custom_tools._resolve_public_addresses("api.example.com", 443)

    def test_pinned_request_connects_to_prevalidated_ip_for_allowed_tls_host(self) -> None:
        response = MagicMock()
        response.status = 200
        response.getheader.return_value = "application/json; charset=utf-8"
        response.read.return_value = b'{"ok":true}'

        connection = MagicMock()
        connection.getresponse.return_value = response

        with (
            patch.object(
                custom_tools,
                "_resolve_public_addresses",
                return_value=["93.184.216.34"],
            ),
            patch.object(
                custom_tools,
                "_PinnedHTTPSConnection",
                return_value=connection,
            ) as connection_type,
        ):
            status, content_type, text = custom_tools._request_pinned_https(
                "GET",
                "https://api.example.com/v1/status?q=x",
                {"Accept": "application/json"},
                None,
            )

        self.assertEqual(status, 200)
        self.assertEqual(content_type, "application/json; charset=utf-8")
        self.assertEqual(text, '{"ok":true}')
        connection_type.assert_called_once_with(
            "api.example.com",
            port=443,
            resolved_ip="93.184.216.34",
            timeout=20.0,
        )
        connection.request.assert_called_once_with(
            "GET",
            "/v1/status?q=x",
            body=None,
            headers={"Accept": "application/json"},
        )

    def test_run_rejects_private_dns_before_any_connection_or_repair(self) -> None:
        plan = {
            "method": "GET",
            "url": "https://api.example.com/v1/status",
            "headers": {},
            "body": None,
        }
        tool = {
            "name": "private_guard",
            "enabled": True,
            "risk": "read",
            "allowed_hosts": ["api.example.com"],
            "code": "print('{}')",
        }
        sandbox_result = SimpleNamespace(
            ok=True,
            stdout=__import__("json").dumps(plan) + "\n",
            message="",
        )
        private_answer = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("10.0.0.5", 443),
            )
        ]
        with (
            patch.object(custom_tools, "get_tool", return_value=tool),
            patch.object(custom_tools, "run_python", return_value=sandbox_result),
            patch.object(socket, "getaddrinfo", return_value=private_answer),
            patch.object(custom_tools, "_PinnedHTTPSConnection") as connection_type,
            patch.object(custom_tools, "queue_repair") as queue_repair,
        ):
            with self.assertRaisesRegex(ValueError, "non-public"):
                custom_tools.run("private_guard", {})

        connection_type.assert_not_called()
        queue_repair.assert_not_called()


if __name__ == "__main__":
    unittest.main()

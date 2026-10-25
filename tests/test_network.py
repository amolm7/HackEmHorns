import socket
import unittest
from unittest.mock import patch, MagicMock
from backend.runtime.mcp import public_address, _PinnedHTTPSHandler
from backend.contracts import Error


class NetworkBoundaryTests(unittest.TestCase):
    def test_mixed_public_private_dns_is_denied(self):
        addresses = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ]
        with patch("backend.runtime.mcp.socket.getaddrinfo", return_value=addresses):
            with self.assertRaises(Error):
                public_address("https://example.com")

    def test_https_connection_pins_ip_but_preserves_hostname(self):
        handler = _PinnedHTTPSHandler("93.184.216.34", MagicMock())

        def open_connection(factory, request, **kwargs):
            connection = factory("example.com", timeout=8, context=kwargs["context"])
            self.assertEqual(connection.host, "example.com")
            with patch("backend.runtime.mcp.socket.create_connection") as connect:
                connection._create_connection(("example.com", 443), 8)
                self.assertEqual(connect.call_args.args[0], ("93.184.216.34", 443))
            return "response"

        with patch.object(handler, "do_open", side_effect=open_connection):
            self.assertEqual(handler.https_open(MagicMock()), "response")

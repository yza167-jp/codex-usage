import csv
import io
import json
import struct
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_codex_usage import load_module


class FakeCloudThreadReader:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []
        self.closed = False

    def call(self, method, params):
        self.calls.append((method, dict(params)))
        return self.pages[(params["archived"], params["cursor"])]

    def close(self):
        self.closed = True


class RecordingSocket:
    def __init__(self):
        self.timeouts = []
        self.sent = []

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def sendall(self, data):
        self.sent.append(data)


class CloudUsageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    @staticmethod
    def response(rows=(), data_as_of="2026-10-04T12:00:00Z"):
        return {"threads": list(rows), "data_as_of": data_as_of}

    @staticmethod
    def websocket_frame(payload=b"", opcode=1, final=True, masked=False, rsv=0):
        first = (0x80 if final else 0) | rsv | opcode
        length = len(payload)
        if length < 126:
            second = length
            extended = b""
        elif length <= 65535:
            second = 126
            extended = struct.pack("!H", length)
        else:
            second = 127
            extended = struct.pack("!Q", length)
        key = b""
        if masked:
            second |= 0x80
            key = b"abcd"
            payload = bytes(value ^ key[i % 4] for i, value in enumerate(payload))
        return bytes((first, second)) + extended + key + payload

    def frame_reader(self, frames):
        reader = self.mod._CloudThreadReader.__new__(self.mod._CloudThreadReader)
        socket = RecordingSocket()
        reader.connection = SimpleNamespace(sock=socket)
        reader.response = SimpleNamespace(fp=io.BytesIO(b"".join(frames)))
        return reader, socket

    def test_report_identifies_lifetime_cloud_amounts_separately_from_local_period_usage(self):
        with patch.object(
            self.mod,
            "_cloud_request",
            return_value=self.response([{
                "thread_id": "cloud-1",
                "data_status": "complete",
                "usage_source": "backend",
                "five_hour_limit_percent": 12.5,
                "weekly_limit_percent": 34.0,
                "balance_usage_credits": 18.25,
            }]),
        ):
            report = self.mod.read_cloud_usage(Path("unused"), [{"id": "cloud-1", "title": "Cloud task"}])

        self.assertEqual(report["scope"], "lifetime")
        self.assertEqual(report["host"], "cloud")
        self.assertFalse(report["includes_descendants"])
        self.assertFalse(report["period_attribution_available"])
        self.assertFalse(report["token_counts_available"])
        self.assertEqual(report["data_as_of"], "2026-10-04T12:00:00+00:00")
        session = report["sessions"][0]
        self.assertEqual(session["scope"], "lifetime")
        self.assertEqual(session["host"], "cloud")
        self.assertEqual(session["weekly_limit_percent"], 34.0)
        self.assertIsNone(session["input_tokens"])

    def test_partial_response_preserves_real_zero_and_missing_amounts(self):
        row = {
            "thread_id": "partial",
            "data_status": "partial",
            "five_hour_limit_percent": 0,
            "weekly_limit_percent": None,
            "balance_usage_credits": 0.0,
        }
        with patch.object(self.mod, "_cloud_request", return_value=self.response([row])):
            session = self.mod.read_cloud_usage(Path("unused"), [{"id": "partial"}])["sessions"][0]

        self.assertEqual(session["data_status"], "partial")
        self.assertEqual(session["five_hour_limit_percent"], 0.0)
        self.assertIsNone(session["weekly_limit_percent"])
        self.assertEqual(session["balance_usage_credits"], 0.0)

    def test_unavailable_response_keeps_amounts_unknown_even_if_zero_is_returned(self):
        row = {
            "thread_id": "unavailable",
            "data_status": "unavailable",
            "five_hour_limit_percent": 0,
            "weekly_limit_percent": 75,
            "balance_usage_credits": 0,
        }
        with patch.object(self.mod, "_cloud_request", return_value=self.response([row])):
            session = self.mod.read_cloud_usage(Path("unused"), [{"id": "unavailable"}])["sessions"][0]

        self.assertEqual(session["data_status"], "unavailable")
        self.assertIsNone(session["five_hour_limit_percent"])
        self.assertIsNone(session["weekly_limit_percent"])
        self.assertIsNone(session["balance_usage_credits"])

    def test_repeated_thread_ids_are_queried_and_reported_once(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(self.mod, "_cloud_request", return_value=self.response([{
                "thread_id": "duplicate",
                "data_status": "complete",
                "weekly_limit_percent": 10,
            }])) as request:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    code = self.mod.main([
                        "cloud", "--cloud-thread", "duplicate", "--cloud-thread", "duplicate",
                        "--json", "--codex-home", td,
                    ])

        self.assertEqual(code, 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(len(report["sessions"]), 1)
        self.assertEqual(report["sessions"][0]["session_id"], "duplicate")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(
            [item["thread_id"] for item in request.call_args_list[0].args[2]["threads"]],
            ["duplicate"],
        )

    def test_cloud_usage_batches_thread_queries_in_groups_of_fifty(self):
        ids = [f"thread-{i:03d}" for i in range(102)]
        requests = []

        def fake_request(_home, _path, body):
            if _path.endswith("/query"):
                return self.response([])
            batch = body["threads"]
            requests.append(batch)
            return self.response([
                {"thread_id": item["thread_id"], "data_status": "complete"}
                for item in batch
            ])

        with patch.object(self.mod, "_cloud_request", side_effect=fake_request):
            report = self.mod.read_cloud_usage(Path("unused"), [{"id": sid} for sid in ids])

        self.assertEqual([len(batch) for batch in requests], [50, 50, 2])
        self.assertEqual([item["thread_id"] for item in requests[0]], ids[:50])
        self.assertEqual([item["thread_id"] for item in requests[-1]], ids[100:])
        self.assertTrue(all(item["descendant_thread_ids"] == [] for batch in requests for item in batch))
        self.assertEqual(len(report["sessions"]), 102)

    def test_invalid_cloud_thread_list_raises_cloud_usage_error(self):
        with patch.object(self.mod, "_cloud_request", return_value={"threads": None}):
            with self.assertRaises(self.mod.CloudUsageError):
                self.mod.read_cloud_usage(Path("unused"), [{"id": "thread"}])

    def test_non_object_cloud_thread_row_raises_cloud_usage_error(self):
        with patch.object(self.mod, "_cloud_request", return_value={"threads": [None]}):
            with self.assertRaises(self.mod.CloudUsageError):
                self.mod.read_cloud_usage(Path("unused"), [{"id": "thread"}])

    def test_json_output_preserves_report_fields(self):
        report = {
            "scope": "lifetime",
            "host": "cloud",
            "data_as_of": "2026-10-04T12:00:00+00:00",
            "sessions": [{"session_id": "cloud-1", "title": "任务", "scope": "lifetime"}],
        }

        rendered = self.mod.render_cloud_usage(report, "json")

        self.assertEqual(json.loads(rendered), report)

    def test_csv_output_has_one_row_per_session_and_keeps_unknown_amounts_blank(self):
        report = {
            "scope": "lifetime",
            "host": "cloud",
            "data_as_of": "2026-10-04T12:00:00+00:00",
            "sessions": [{
                "session_id": "cloud-1",
                "title": "Cloud task",
                "host": "cloud",
                "scope": "lifetime",
                "data_status": "partial",
                "usage_source": "backend",
                "weekly_limit_percent": None,
                "five_hour_limit_percent": 0.0,
                "balance_usage_credits": None,
            }],
        }

        rendered = self.mod.render_cloud_usage(report, "csv")
        rows = list(csv.DictReader(io.StringIO(rendered)))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["session_id"], "cloud-1")
        self.assertEqual(rows[0]["five_hour_limit_percent"], "0.0")
        self.assertEqual(rows[0]["weekly_limit_percent"], "")
        self.assertEqual(rows[0]["balance_usage_credits"], "")
        self.assertEqual(rows[0]["data_as_of"], report["data_as_of"])

    def test_table_output_labels_lifetime_scope_and_unknown_values(self):
        report = {
            "scope": "lifetime",
            "host": "cloud",
            "data_as_of": None,
            "sessions": [{
                "session_id": "cloud-1",
                "title": "Cloud task",
                "data_status": "partial",
                "weekly_limit_percent": None,
                "five_hour_limit_percent": 0.0,
                "balance_usage_credits": None,
            }],
        }

        rendered = self.mod.render_cloud_usage(report, "table", details=True)

        self.assertIn("lifetime", rendered)
        self.assertIn("Data as of: unavailable", rendered)
        self.assertIn("Cloud task", rendered)
        self.assertIn("0.0000", rendered)
        self.assertIn("partial", rendered)
        self.assertIn("Partial/unavailable data is not zero", rendered)

    def test_cloud_terminal_removes_remote_control_sequences(self):
        report = {
            "data_as_of": None,
            "sessions": [{
                "title": "task\x1b]52;c;payload\x07\x9b2J",
                "data_status": "partial\x1b[2J",
                "weekly_limit_percent": None,
                "five_hour_limit_percent": None,
                "balance_usage_credits": None,
            }],
        }
        rendered = self.mod.render_cloud_usage(report)
        self.assertNotIn("\x1b", rendered)
        self.assertNotIn("\x07", rendered)
        self.assertNotIn("\x9b", rendered)
        self.assertEqual(json.loads(self.mod.render_cloud_usage(report, "json")), report)

    def test_cloud_thread_option_with_local_period_returns_clear_error(self):
        with tempfile.TemporaryDirectory() as td:
            stderr = io.StringIO()
            with patch.object(self.mod, "_cloud_request") as request:
                with redirect_stderr(stderr):
                    code = self.mod.main(["24h", "--cloud-thread", "thread", "--codex-home", td])

        self.assertEqual(code, 2)
        self.assertIn("--cloud-thread requires the cloud lifetime report", stderr.getvalue())
        request.assert_not_called()

    def test_missing_local_auth_fails_safely_without_exposing_secrets(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(self.mod.CloudUsageError) as caught:
                self.mod._cloud_request(Path(td), "/wham/usage/thread_usage/query_v2", {})

        message = str(caught.exception)
        self.assertIn("existing Codex ChatGPT login", message)
        self.assertNotIn("secret", message.lower())
        self.assertNotIn(td, message)

    def test_cloud_redirect_handler_refuses_redirects(self):
        handler = self.mod._NoCloudRedirects()

        redirected = handler.redirect_request(object(), None, 302, "Found", {}, "https://example.invalid/")

        self.assertIsNone(redirected)

    def test_discovery_paginates_current_and_archived_threads(self):
        pages = {
            (False, None): {
                "data": [{"id": "current-1", "name": "Current one", "createdAt": 1791100000}],
                "nextCursor": "current-next",
            },
            (False, "current-next"): {
                "data": [{"id": "current-2", "title": "Current two"}],
                "nextCursor": None,
            },
            (True, None): {
                "data": [{"id": "archived-1", "preview": "Archived one"}],
                "nextCursor": "archived-next",
            },
            (True, "archived-next"): {
                "data": [{"id": "archived-2", "createdAt": "2026-10-03T01:00:00Z"}],
                "nextCursor": None,
            },
        }
        reader = FakeCloudThreadReader(pages)
        with patch.object(self.mod, "_CloudThreadReader", return_value=reader):
            threads = self.mod.discover_cloud_threads(Path("unused"))

        self.assertEqual(
            [(params["archived"], params["cursor"]) for _, params in reader.calls],
            [(False, None), (False, "current-next"), (True, None), (True, "archived-next")],
        )
        self.assertTrue(all(params["limit"] == 100 for _, params in reader.calls))
        self.assertTrue(all(params["sortKey"] == "updated_at" for _, params in reader.calls))
        self.assertEqual([thread["id"] for thread in threads], [
            "current-1", "current-2", "archived-1", "archived-2",
        ])
        self.assertEqual(threads[0]["title"], "Current one")
        self.assertEqual(threads[0]["created_at"], "2026-10-04T07:46:40+00:00")
        self.assertEqual(threads[1]["title"], "Current two")
        self.assertEqual(threads[2]["title"], "Archived one")
        self.assertEqual(threads[3]["created_at"], "2026-10-03T01:00:00+00:00")
        self.assertEqual([thread["archived"] for thread in threads], [False, False, True, True])
        self.assertTrue(reader.closed)

    def test_repeated_discovery_cursor_fails_and_closes_reader(self):
        repeated = {"data": [], "nextCursor": "same-cursor"}
        reader = FakeCloudThreadReader({
            (False, None): repeated,
            (False, "same-cursor"): repeated,
        })
        with patch.object(self.mod, "_CloudThreadReader", return_value=reader):
            with self.assertRaisesRegex(self.mod.CloudUsageError, "repeated or invalid cursor"):
                self.mod.discover_cloud_threads(Path("unused"), include_archived=False)

        self.assertEqual(len(reader.calls), 2)
        self.assertTrue(reader.closed)

    def test_discovery_does_not_double_count_threads_seen_in_both_inventories(self):
        duplicate_current = {"data": [{"id": "shared", "name": "Current title"}], "nextCursor": None}
        duplicate_archived = {"data": [{"id": "shared", "name": "Archived title"}], "nextCursor": None}
        reader = FakeCloudThreadReader({
            (False, None): duplicate_current,
            (True, None): duplicate_archived,
        })
        with patch.object(self.mod, "_CloudThreadReader", return_value=reader):
            threads = self.mod.discover_cloud_threads(Path("unused"))
        with patch.object(self.mod, "_cloud_request", return_value=self.response([{
            "thread_id": "shared", "data_status": "complete", "weekly_limit_percent": 12,
        }])) as request:
            report = self.mod.read_cloud_usage(Path("unused"), threads)

        self.assertEqual(len(threads), 1)
        self.assertEqual(threads[0]["title"], "Archived title")
        self.assertTrue(threads[0]["archived"])
        self.assertEqual(len(report["sessions"]), 1)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].args[2]["threads"], [{
            "thread_id": "shared", "created_at": None, "descendant_thread_ids": [],
        }])

    def test_cloud_no_archived_option_queries_only_current_threads(self):
        reader = FakeCloudThreadReader({
            (False, None): {
                "data": [{"id": "current", "name": "Current task"}], "nextCursor": None,
            },
        })
        with tempfile.TemporaryDirectory() as td:
            stdout = io.StringIO()
            with patch.object(self.mod, "_CloudThreadReader", return_value=reader), patch.object(
                self.mod, "_cloud_request", return_value=self.response([{
                    "thread_id": "current", "data_status": "complete",
                }]),
            ):
                with redirect_stdout(stdout):
                    code = self.mod.main([
                        "24h", "--cloud", "--no-archived", "--no-quota", "--no-cache",
                        "--json", "--codex-home", td,
                    ])

        self.assertEqual(code, 0)
        self.assertEqual([params["archived"] for _, params in reader.calls], [False])
        report = json.loads(stdout.getvalue())
        self.assertEqual([item["session_id"] for item in report["cloud_usage"]["sessions"]], ["current"])

    def test_cloud_flag_adds_lifetime_report_to_json_when_local_home_is_empty(self):
        reader = FakeCloudThreadReader({
            (False, None): {
                "data": [{"id": "cloud-1", "name": "Cloud task"}], "nextCursor": None,
            },
            (True, None): {"data": [], "nextCursor": None},
        })
        with tempfile.TemporaryDirectory() as td:
            stdout = io.StringIO()
            with patch.object(self.mod, "_CloudThreadReader", return_value=reader), patch.object(
                self.mod, "_cloud_request", return_value=self.response([{
                    "thread_id": "cloud-1", "data_status": "complete", "weekly_limit_percent": 20,
                }]),
            ):
                with redirect_stdout(stdout):
                    code = self.mod.main([
                        "24h", "--cloud", "--no-quota", "--no-cache", "--json", "--codex-home", td,
                    ])

        self.assertEqual(code, 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["sessions"], [])
        self.assertEqual(report["cloud_usage"]["scope"], "lifetime")
        self.assertEqual(report["cloud_usage"]["sessions"][0]["session_id"], "cloud-1")
        self.assertEqual(report["cloud_usage"]["sessions"][0]["weekly_limit_percent"], 20.0)

    def test_cloud_flag_adds_cloud_scope_to_csv_when_local_home_is_empty(self):
        reader = FakeCloudThreadReader({
            (False, None): {
                "data": [{"id": "cloud-1", "name": "Cloud task"}], "nextCursor": None,
            },
            (True, None): {"data": [], "nextCursor": None},
        })
        with tempfile.TemporaryDirectory() as td:
            stdout = io.StringIO()
            with patch.object(self.mod, "_CloudThreadReader", return_value=reader), patch.object(
                self.mod, "_cloud_request", return_value=self.response([{
                    "thread_id": "cloud-1", "data_status": "complete", "weekly_limit_percent": 20,
                }]),
            ):
                with redirect_stdout(stdout):
                    code = self.mod.main([
                        "24h", "--cloud", "--no-quota", "--no-cache", "--csv", "--codex-home", td,
                    ])

        self.assertEqual(code, 0)
        rows = list(csv.DictReader(io.StringIO(stdout.getvalue())))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["session_id"], "cloud-1")
        self.assertEqual(rows[0]["host"], "cloud")
        self.assertEqual(rows[0]["scope"], "lifetime")

    def test_receive_reassembles_fragmented_text_and_answers_ping(self):
        first = b'{"id":1,'
        ping = b"ping-token"
        final = b'"result":{"ok":true}}'
        reader, socket = self.frame_reader([
            self.websocket_frame(first, opcode=1, final=False),
            self.websocket_frame(ping, opcode=9),
            self.websocket_frame(final, opcode=0, final=True),
        ])

        message = reader._receive(self.mod.time.monotonic() + 5)

        self.assertEqual(message, {"id": 1, "result": {"ok": True}})
        self.assertEqual(len(socket.sent), 1)
        pong = socket.sent[0]
        self.assertEqual(pong[0] & 0x0F, 10)
        self.assertTrue(pong[1] & 0x80)
        mask = pong[2:6]
        payload = pong[6:]
        self.assertEqual(bytes(value ^ mask[i % 4] for i, value in enumerate(payload)), ping)

    def test_receive_rejects_oversized_websocket_frame(self):
        reader, _ = self.frame_reader([self.websocket_frame(b"12345")])
        reader.MAX_MESSAGE_BYTES = 4

        with self.assertRaisesRegex(self.mod.CloudUsageError, "exceeds the size limit"):
            reader._receive(self.mod.time.monotonic() + 5)

    def test_receive_rejects_reserved_websocket_framing_bits(self):
        reader, _ = self.frame_reader([self.websocket_frame(b"{}", rsv=0x40)])

        with self.assertRaisesRegex(self.mod.CloudUsageError, "unsupported WebSocket framing"):
            reader._receive(self.mod.time.monotonic() + 5)

    def test_receive_rejects_masked_server_frames(self):
        reader, _ = self.frame_reader([self.websocket_frame(b"{}", masked=True)])

        with self.assertRaisesRegex(self.mod.CloudUsageError, "unsupported WebSocket framing"):
            reader._receive(self.mod.time.monotonic() + 5)

    def test_receive_rejects_peer_close_frame(self):
        reader, _ = self.frame_reader([self.websocket_frame(opcode=8)])

        with self.assertRaisesRegex(self.mod.CloudUsageError, "connection closed"):
            reader._receive(self.mod.time.monotonic() + 5)

    def test_receive_rejects_truncated_response_after_connection_closes(self):
        reader, _ = self.frame_reader([bytes((0x81, 5)) + b"ab"])

        with self.assertRaisesRegex(self.mod.CloudUsageError, "closed before completing"):
            reader._receive(self.mod.time.monotonic() + 5)

    def test_reader_call_allows_only_initialize_and_thread_list(self):
        for method in ("initialize", "thread/list"):
            with self.subTest(method=method):
                reader = self.mod._CloudThreadReader.__new__(self.mod._CloudThreadReader)
                reader.request_id = 0
                sent = []
                with patch.object(reader, "_send", side_effect=lambda payload: sent.append(json.loads(payload))), patch.object(
                    reader, "_receive", side_effect=lambda _deadline: {"id": reader.request_id, "result": {"ok": True}},
                ):
                    self.assertEqual(reader.call(method, {}), {"ok": True})
                self.assertEqual(sent[0]["method"], method)

        reader = self.mod._CloudThreadReader.__new__(self.mod._CloudThreadReader)
        reader.request_id = 0
        with patch.object(reader, "_send") as send:
            with self.assertRaisesRegex(self.mod.CloudUsageError, "only read-only inventory requests"):
                reader.call("thread/read", {})
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()

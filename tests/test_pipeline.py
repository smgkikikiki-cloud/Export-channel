import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
import wave

import narration as n


class FakeResponse(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Type": "text/event-stream", "Speechify-Audio-Content-Type": "audio/L16; rate=24000; channels=1", "Speechify-Request-Id": "test-request"}


def event(kind, data):
    return f"event: {kind}\r\ndata: {json.dumps(data)}\r\n\r\n".encode()


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_long_text_keeps_every_character_and_respects_limit(self):
        text = ("Dr. Smith tested the YJ in 1987. It had a 4.2-liter engine.\n\n" * 900) + "The end. 🚙"
        parts = n.split_text(text)
        self.assertGreater(len(parts), 1)
        self.assertEqual("".join(parts), text)
        self.assertTrue(all(n.units(p) <= n.MAX_INPUT for p in parts))
        self.assertTrue(all(p.strip() for p in parts))
        self.assertTrue(all(n.units(p) <= 30 for p in n.split_text("🚙" * 101, 30)))

    def test_fifteen_minutes_is_three_lossless_five_minute_wavs(self):
        # A deterministic, changing PCM pattern catches dropped/duplicated bytes at joins.
        pcm = bytes(range(256)) * (n.RATE * n.WIDTH * 900 // 256)
        pcm += bytes(range((n.RATE * n.WIDTH * 900) % 256))
        source = self.root / "source.pcm"
        source.write_bytes(pcm)
        out = self.root / "out"
        parts = n.export_audio([source], out)
        self.assertEqual([p["duration_seconds"] for p in parts], [300, 300, 300])
        reconstructed = bytearray()
        for part in parts:
            with wave.open(str(out / part["file"]), "rb") as reader:
                self.assertEqual(reader.getframerate(), 24000)
                self.assertEqual(reader.getnchannels(), 1)
                self.assertEqual(reader.getsampwidth(), 2)
                reconstructed.extend(reader.readframes(reader.getnframes()))
        self.assertEqual(bytes(reconstructed), pcm)

    def test_remainder_is_not_padded_or_discarded(self):
        source = self.root / "source.pcm"
        source.write_bytes(b"\x01\x02" * (n.RATE * 301))
        parts = n.export_audio([source], self.root / "out")
        self.assertEqual([p["duration_seconds"] for p in parts], [300, 1])

    def test_cached_rerun_and_local_reexport_make_no_new_api_call(self):
        calls = []
        def fake(body, key, destination):
            calls.append(body)
            destination.write_bytes(b"\x01\x02" * n.RATE)
            return {"duration_seconds": 1}
        output = n.run("Hello world.", self.root, "local-test-secret", transport=fake, log=lambda _: None)
        (output / "narration_001.wav").unlink()
        n.run("Hello world.", self.root, "", transport=fake, log=lambda _: None)
        self.assertEqual(len(calls), 1)
        self.assertTrue((output / "narration_001.wav").exists())
        for path in self.root.rglob("*.json"):
            self.assertNotIn("local-test-secret", path.read_text())

    def test_incomplete_request_blocks_retries(self):
        calls = []
        def broken(body, key, destination):
            calls.append(body)
            destination.write_bytes(b"\x00\x00" * 100)
            raise TimeoutError("connection lost")
        for attempt in range(2):
            with self.assertRaises(n.PipelineError):
                n.run("Hello world.", self.root, "secret", transport=broken, log=lambda _: None)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(list((self.root / ".cache").rglob("audio.partial.pcm"))), 1)

    def test_corrupted_cache_is_not_regenerated(self):
        calls = []
        def fake(body, key, destination):
            calls.append(body)
            destination.write_bytes(b"\x00\x00" * 100)
            return {}
        n.run("Hello.", self.root, "secret", transport=fake, log=lambda _: None)
        list((self.root / ".cache").rglob("audio.pcm"))[0].write_bytes(b"damaged")
        with self.assertRaises(n.PipelineError):
            n.run("Hello.", self.root, "secret", transport=fake, log=lambda _: None)
        self.assertEqual(len(calls), 1)

    def test_voice_and_model_change_the_cache_identity(self):
        first = n.make_plan("Hello.", self.root)["rows"][0]["key"]
        second = n.make_plan("Hello.", self.root, "another_voice")["rows"][0]["key"]
        third = n.make_plan("Hello.", self.root, model="simba-3.0")["rows"][0]["key"]
        self.assertEqual(len({first, second, third}), 3)

    def test_sse_marks_only_unknown_events_and_done(self):
        pcm = b"\x01\x02" * n.RATE
        stream = b": heartbeat\n\n" + event("future.event", {"ignore": True})
        stream += event("speech.chunk", {"audio": base64.b64encode(pcm[:24000]).decode()})
        stream += event("speech.chunk", {"audio": base64.b64encode(pcm[24000:]).decode()})
        stream += event("speech.chunk", {"speech_marks": [{"value": "Hello", "start_time": 0, "end_time": 1000}]})
        stream += event("speech.done", {"audio_duration_ms": 1000, "billable_characters_count": 5})
        calls = []
        def opener(request, timeout):
            calls.append(request)
            self.assertEqual(request.get_header("Accept"), "audio/pcm")
            self.assertEqual(json.loads(request.data)["input"], "Hello")
            return FakeResponse(stream)
        destination = self.root / "audio.pcm"
        result = n.stream_to_pcm(n.request_body("Hello", n.DEFAULT_VOICE, n.DEFAULT_MODEL), "secret", destination, opener)
        self.assertEqual(destination.read_bytes(), pcm)
        self.assertEqual(result["speech_marks"][0]["value"], "Hello")
        self.assertEqual(len(calls), 1)

    def test_sse_eof_and_error_cannot_be_success(self):
        for end in (b"", event("speech.error", {"error": {"code": "upstream_failure"}})):
            stream = event("speech.chunk", {"audio": base64.b64encode(b"\x00\x00" * 100).decode()}) + end
            with self.assertRaises(n.PipelineError):
                n.stream_to_pcm(n.request_body("Hello", n.DEFAULT_VOICE, n.DEFAULT_MODEL), "secret", self.root / "partial.pcm", lambda *args, **kwargs: FakeResponse(stream))

    def test_lock_prevents_double_submission(self):
        with n.exclusive(self.root):
            with self.assertRaises(n.PipelineError):
                with n.exclusive(self.root):
                    self.fail("Second run acquired the same lock")

    def test_pcm_duration_mismatch_cannot_be_success(self):
        stream = event("speech.chunk", {"audio": base64.b64encode(b"\x00\x00" * n.RATE).decode()})
        stream += event("speech.done", {"audio_duration_ms": 5000})
        with self.assertRaises(n.PipelineError):
            n.stream_to_pcm(n.request_body("Hello", n.DEFAULT_VOICE, n.DEFAULT_MODEL), "secret", self.root / "partial.pcm", lambda *args, **kwargs: FakeResponse(stream))


if __name__ == "__main__":
    unittest.main()

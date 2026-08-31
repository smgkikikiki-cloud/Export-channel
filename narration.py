"""Small Speechify-to-WAV pipeline. Python standard library only."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import uuid
import urllib.error
import urllib.request
import wave
from contextlib import contextmanager

ENDPOINT = "https://api.speechify.ai/v1/audio/stream/with-timestamps"
RATE = 24000
WIDTH = 2
MAX_INPUT = 19500  # Headroom below the documented 20,000-character ceiling.
DEFAULT_VOICE = "geffen_32"
DEFAULT_MODEL = "simba-3.2"


class PipelineError(RuntimeError):
    pass


def units(text):
    return len(text.encode("utf-16-le")) // 2


def split_text(text, limit=MAX_INPUT):
    """Keep every character; split only when the API ceiling requires it."""
    if not text.strip():
        raise PipelineError("Paste an English narration first.")
    result = []
    rest = text
    while units(rest) > limit:
        end = min(len(rest), limit)
        while units(rest[:end]) > limit:
            end -= 1
        window = rest[:end]
        candidates = [m.end() for m in re.finditer(r"\n\s*\n|[.!?][\"')\]]*\s+", window)]
        cut = next((x for x in reversed(candidates) if x >= end // 2), None)
        if cut is None:
            spaces = [m.end() for m in re.finditer(r"\s+", window)]
            cut = spaces[-1] if spaces else end
        result.append(rest[:cut])
        rest = rest[cut:]
    if rest:
        result.append(rest)
    assert "".join(result) == text
    return result


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PipelineError(f"Cannot read {path.name}; kept existing files. No automatic regeneration.") from exc


@contextmanager
def exclusive(root):
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".run-lock"
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise PipelineError("Another run holds .run-lock. If the app crashed, close all copies before removing that empty folder.") from exc
    try:
        yield
    finally:
        lock.rmdir()


def request_body(text, voice, model):
    return {"input": text, "voice_id": voice, "model": model, "language": "en-US"}


def cache_key(body):
    identity = {"endpoint": ENDPOINT, "accept": "audio/pcm", "format": "s16le-24000-mono", "body": body}
    return digest(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def cache_status(root, key):
    entry = root / ".cache" / key
    state_file = entry / "state.json"
    pcm = entry / "audio.pcm"
    if not state_file.exists():
        return "blocked" if entry.exists() else "new"
    state = read_json(state_file)
    if state.get("status") != "complete" or not pcm.exists():
        return "blocked"
    data = pcm.read_bytes()
    if not data or len(data) % WIDTH or digest(data) != state.get("sha256"):
        return "blocked"
    return "cached"


def make_plan(text, root, voice=DEFAULT_VOICE, model=DEFAULT_MODEL):
    if not voice.strip() or not model.strip():
        raise PipelineError("Voice ID and model are required.")
    parts = split_text(text)
    rows = []
    for index, part in enumerate(parts, 1):
        body = request_body(part, voice.strip(), model.strip())
        key = cache_key(body)
        rows.append({"index": index, "body": body, "key": key, "status": cache_status(root, key), "characters": len(part)})
    new_chars = sum(r["characters"] for r in rows if r["status"] == "new")
    return {"text": text, "voice": voice.strip(), "model": model.strip(), "rows": rows,
            "input_characters": len(text), "new_characters_upper_bound": new_chars,
            "estimated_minutes_at_150_wpm": len(text.split()) / 150}


def sse_events(response):
    name = ""
    lines = []
    for raw in response:
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if lines:
                yield name, "\n".join(lines)
            name, lines = "", []
        elif line.startswith("event:"):
            name = line[6:].lstrip()
        elif line.startswith("data:"):
            lines.append(line[5:].lstrip())
    if lines:
        yield name, "\n".join(lines)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward this API key to another endpoint.
        return None


def stream_to_pcm(body, api_key, destination, opener=None):
    """Exactly one HTTP attempt. Only speech.done can complete a synthesis."""
    request = urllib.request.Request(
        ENDPOINT, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json",
                 "Accept": "audio/pcm", "Speechify-Request-Id": str(uuid.uuid4())})
    open_request = opener or urllib.request.build_opener(NoRedirect()).open
    marks, terminal, request_id = [], None, None
    try:
        with open_request(request, timeout=180) as response:
            if "text/event-stream" not in response.headers.get("Content-Type", ""):
                raise PipelineError("Expected an event stream; response saved as incomplete. No retry.")
            audio_type = response.headers.get("Speechify-Audio-Content-Type", "").lower()
            if not audio_type.startswith(("audio/l16", "audio/pcm")):
                raise PipelineError("API did not confirm PCM audio. Stopping without retry.")
            if "rate=" in audio_type and not re.search(r"rate=\s*24000(?:;|$)", audio_type):
                raise PipelineError("Unexpected PCM sample rate. Stopping without retry.")
            if "channels=" in audio_type and not re.search(r"channels=\s*1(?:;|$)", audio_type):
                raise PipelineError("Unexpected PCM channel count. Stopping without retry.")
            request_id = response.headers.get("Speechify-Request-Id")
            with destination.open("wb") as output:
                for event, payload in sse_events(response):
                    if event and event not in ("speech.chunk", "speech.done", "speech.error"):
                        continue
                    data = json.loads(payload)
                    kind = event or data.get("type")
                    if kind == "speech.error":
                        raise PipelineError("Speechify reported a synthesis error after starting. No automatic retry.")
                    if kind == "speech.chunk":
                        if data.get("audio"):
                            output.write(base64.b64decode(data["audio"], validate=True))
                        marks.extend(data.get("speech_marks") or [])
                    if kind == "speech.done":
                        terminal = data
                        break
    except urllib.error.HTTPError as exc:
        raise PipelineError(f"Speechify HTTP {exc.code}. Check credentials, balance, model and voice. No automatic retry.") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PipelineError("Connection interrupted. The provider may already have charged. Partial data retained; no automatic retry.") from None
    if terminal is None:
        raise PipelineError("Stream ended without speech.done. Partial data retained; no automatic retry.")
    size = destination.stat().st_size
    if size == 0 or size % WIDTH:
        raise PipelineError("Invalid PCM byte count. Partial data retained; no automatic retry.")
    duration = size / (RATE * WIDTH)
    expected = terminal.get("audio_duration_ms")
    if expected is not None and abs(duration - float(expected) / 1000) > 0.5:
        raise PipelineError("PCM duration does not match provider duration. No automatic retry.")
    return {"request_id": request_id, "speech_marks": marks, "provider_summary": terminal, "duration_seconds": duration}


def synthesize(row, root, api_key, transport=stream_to_pcm):
    key = row["key"]
    entry = root / ".cache" / key
    status = cache_status(root, key)
    if status == "cached":
        return entry / "audio.pcm"
    if status != "new":
        raise PipelineError(f"Request {row['index']} has a failed, incomplete or damaged cache entry. No automatic retry. See README recovery instructions.")
    if not api_key.strip():
        raise PipelineError("Enter your Speechify API key locally; do not put it in GitHub or chat.")
    entry.mkdir(parents=True)
    write_json(entry / "request.json", row["body"])
    write_json(entry / "state.json", {"status": "started"})
    partial = entry / "audio.partial.pcm"
    try:
        metadata = transport(row["body"], api_key.strip(), partial)
        content = partial.read_bytes()
        if not content or len(content) % WIDTH:
            raise PipelineError("Invalid PCM; refusing to mark the cache complete.")
        write_json(entry / "metadata.json", metadata)
        os.replace(partial, entry / "audio.pcm")
        write_json(entry / "state.json", {"status": "complete", "sha256": digest(content), "bytes": len(content)})
    except Exception as exc:
        # Never persist exception strings: they could contain credentials or provider payloads.
        write_json(entry / "state.json", {"status": "needs_review", "error_type": type(exc).__name__})
        if isinstance(exc, PipelineError):
            raise
        raise PipelineError("Synthesis did not complete. Data retained; no automatic retry.") from None
    return entry / "audio.pcm"


def write_wav(path, pcm):
    temporary = path.with_name(path.name + ".tmp")
    with wave.open(str(temporary), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(WIDTH)
        output.setframerate(RATE)
        output.writeframes(pcm)
    os.replace(temporary, path)


def export_audio(pcm_paths, output, chunk_seconds=300):
    if not math.isfinite(chunk_seconds) or chunk_seconds <= 0:
        raise PipelineError("Chunk length must be positive.")
    pcm = b"".join(path.read_bytes() for path in pcm_paths)
    chunk_bytes = round(chunk_seconds * RATE) * WIDTH
    if not pcm or len(pcm) % WIDTH or chunk_bytes < WIDTH:
        raise PipelineError("Invalid audio or chunk length.")
    output.mkdir(parents=True, exist_ok=True)
    write_wav(output / "narration_full.wav", pcm)
    parts = []
    for index, start in enumerate(range(0, len(pcm), chunk_bytes), 1):
        payload = pcm[start:start + chunk_bytes]
        name = f"narration_{index:03d}.wav"
        write_wav(output / name, payload)
        parts.append({"file": name, "start_seconds": start / (RATE * WIDTH),
                      "duration_seconds": len(payload) / (RATE * WIDTH)})
    return parts


def run(text, root, api_key="", voice=DEFAULT_VOICE, model=DEFAULT_MODEL, log=print, transport=stream_to_pcm):
    root = Path(root).resolve()
    with exclusive(root):
        plan = make_plan(text, root, voice, model)
        if any(row["status"] == "blocked" for row in plan["rows"]):
            raise PipelineError("An earlier request needs review. Nothing new was sent. See README recovery instructions.")
        paths = []
        for row in plan["rows"]:
            log(f"Request {row['index']}/{len(plan['rows'])}: {row['status']}")
            paths.append(synthesize(row, root, api_key, transport))
        job_key = digest(json.dumps([r["key"] for r in plan["rows"]]).encode())[:16]
        output = root / "output" / job_key
        parts = export_audio(paths, output)
        (output / "script.txt").write_text(text, encoding="utf-8")
        (output / "footage").mkdir(exist_ok=True)
        write_json(output / "manifest.json", {"voice": voice, "model": model,
                   "sample_rate": RATE, "format": "PCM WAV 16-bit mono", "chunk_seconds": 300,
                   "parts": parts, "requests": [{"key": r["key"], "characters": r["characters"]} for r in plan["rows"]]})
        log(f"Ready: {len(parts)} audio files plus full narration. {output}")
        return output


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent / "work")
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--generate", action="store_true", help="Explicitly allow new API requests. Default is a free plan.")
    args = parser.parse_args()
    try:
        script = args.script.read_text(encoding="utf-8-sig")
        if args.generate:
            run(script, args.root, os.environ.get("SPEECHIFY_API_KEY", ""), args.voice, args.model)
        else:
            plan = make_plan(script, args.root, args.voice, args.model)
            print(json.dumps({k: v for k, v in plan.items() if k not in ("text", "rows")}, indent=2))
            print("Requests:", [r["status"] for r in plan["rows"]])
    except (PipelineError, OSError) as exc:
        raise SystemExit(str(exc))

# Narration Desk

A small, separate production tool: **final English script → Speechify → five-minute audio files**. A separate footage agent collects relevant source material. The creator assembles everything in CapCut.

This is a fresh project. It does not touch the old video pipeline, Gemini settings, existing API projects, or existing repositories.

## Current implementation

- A local desktop window for pasting text, with a masked API-key field.
- Free review of input size, new requests and cached requests before generation.
- Long-form Speechify streaming with an explicit completion event.
- Large API requests; text is split only if it exceeds the API limit.
- Exact 300-second WAV exports plus a complete WAV. The final part contains the remainder.
- Completed request caching by exact text, voice, model, endpoint and audio settings.
- Partial responses are retained; incomplete requests stop and are never retried automatically.
- One local run at a time. No silent alternative provider or model.
- Original script and an audio manifest accompany every export.

Uses Python's standard library, including Tkinter. **No pip packages, FFmpeg, browser server, cloud hosting or database are required.** This desktop implementation is the initial interface, not a requirement to build a website later.

## Start on Windows

1. Install Python 3.11 or newer, including Tcl/Tk and the Python launcher.
2. Extract this folder. Double-click `start_windows.bat`.
3. Obtain a Speechify **API** key from [Speechify's developer dashboard](https://platform.speechify.ai/). Enter it in the app. A consumer reader subscription is not the API setup.
4. Leave the initial model `simba-3.2` and example voice `geffen_32`, or enter your chosen compatible English voice ID. This default follows the provider's example; it is not a claim that this is the best voice for your channel.
5. Paste a short approved paragraph for the first live test. Click **Review**, inspect the request count, then **Generate audio**.
6. Click **Open output folder**. Listen to the sample before generating a full episode. A different sample is a separate request; a sample is not secretly generated for every episode.
7. For an episode, paste the complete final script, review, then generate. Drag `narration_001.wav`, `narration_002.wav`, etc. into CapCut consecutively with no gaps or crossfades. Alternatively use `narration_full.wav` alone.

The initial API test is still required: no account credentials were supplied and no paid generation was performed while preparing this starter. The desktop window has not been visually tested on Windows.

## What “five minutes” means

The **actual produced audio** is divided at 5:00, 10:00, 15:00, etc. Exactly 15:00 produces three files. A 15:12 narration produces three five-minute files and a twelve-second remainder. The tool does not speed up the voice, rewrite the script or discard content to force a runtime.

Cuts may occur within a sentence or word. These are exact consecutive PCM sample ranges: rejoining the WAV files without gaps reproduces the complete PCM byte-for-byte. There is no extra silence or MP3 encoder padding at these joins. If you want independently playable sections ending on sentences, that is a different export mode and is not implemented here.

API request boundaries and exported audio boundaries are independent. A typical 15-minute English script may fit in a single long API request; a word-count estimate is not a duration guarantee. When the API ceiling requires multiple requests, boundaries prefer paragraphs or sentences. The provider may change intonation across those generation boundaries; the local exporter does not fabricate transitions.

Output is 24 kHz, 16-bit mono WAV, approximately 14.4 MB per five minutes. Converting these files to MP3 later should be a local operation, never a new TTS request.

## Cost and duplicate prevention

Review performs no network requests. It shows submitted characters as an upper bound, including whitespace. It does not claim to know your remaining allowance or exact invoice. Speechify's terminal response records actual billable characters when provided.

A successful unchanged request is reused, including after an app restart or a deleted export file. Changing the text, voice or model intentionally creates a different request. For a script fitting one request, editing it requires one new full-script synthesis; fine-grained paragraph retakes are outside this starter's scope.

Work is stored in `work/`, excluded from Git. Keep that folder when upgrading the app: deleting or moving to a different cache discards local duplicate protection. Do not clear it as routine troubleshooting. The API key is held in memory or read from `SPEECHIFY_API_KEY`; it is never written by this app.

### Incomplete work and recovery

A timeout, HTTP error, missing `speech.done`, invalid format, duration mismatch or damaged cache stops the run. A previous request may already have used paid characters. No automatic retry is attempted, including on 429 or server errors. The next run stops before sending any new requests when it finds a blocked entry.

For a controlled retry, ask your coding agent to inspect the specific `work/.cache/<hash>/` entry and any available Speechify dashboard/request record. Preserve the entry by moving it to `work/reviewed_failures/` only after you explicitly decide to allow that request to be billed again. Then rerun. Never clear all caches, and never relabel partial audio as complete. This starter deliberately has no generic “retry everything” button.

If the app was forcibly closed, an empty `work/.run-lock` directory can remain. Close every copy of the app before removing only that empty lock directory. This does not change any synthesis state or authorize a retry.

## Files for the new project

- `CLAUDE.md`: project constraints and the next coding steps.
- `START_HERE.md`: copy-ready first message to the coding agent.
- `FOOTAGE_AGENT.md`: the independent footage-research assignment.
- `narration.py`: Speechify transport, cache and lossless WAV exporter; also a CLI.
- `app.py`: local desktop interface.
- `tests/test_pipeline.py`: offline behavior tests using simulated provider responses.

Do not upload API keys, the `work/` folder or generated media to GitHub. The audio workflow works without the footage agent; the footage agent does not need the API key.

## Development commands

Run from this folder:

```bash
python -m unittest discover -s tests -v
python app.py
python narration.py episode.txt
```

The last command is a free plan. Adding `--generate` explicitly enables Speechify calls and reads the key from `SPEECHIFY_API_KEY`.

## Verified provider references

Documentation checked on 31 August 2026. API behavior is implemented from these documents but is **not yet verified against the user's account**.

- [Long-form streaming guide](https://docs.speechify.ai/build/streaming-tts-guide): short speech requests allow 2,000 characters; streaming allows 20,000.
- [Streaming with timestamps](https://docs.speechify.ai/build/api-reference/v1/audio/stream/with-timestamps): event stream with `speech.chunk`, `speech.done` and `speech.error`. We use the completion signal to avoid silently treating an interrupted stream as finished. Marks are retained but no subtitle or video synchronization system is built.
- [Speech-mark event examples](https://docs.speechify.ai/build/guides/text-to-speech/speech-marks): audio payload is base64 in the `audio` field.
- [Streaming format guide](https://docs.speechify.ai/build/guides/text-to-speech/streaming): `Accept: audio/pcm` returns little-endian 24 kHz mono PCM. WAV containers are created locally.
- [API pricing](https://speechify.ai/pricing): check your dashboard before choosing a plan. At this check the public page lists 50,000 free TTS characters/month and a $10 Starter plan including 1 million characters/month. We do not hard-code a financial quote into the app.

## Explicitly out of scope

Script generation or rewriting, translation, video assembly, automated image-to-narration matching, automatic publishing, CapCut project generation, multi-channel management, provider switching, video generation, stock purchases and automated footage downloads are not implemented. The footage agent has a separate operating brief and starts after receiving an episode script.

# Narration Desk: project instructions

The owner is rebuilding a content workflow to remove complexity. The intended system is:

1. The owner supplies final English narration.
2. This tool calls Speechify and produces audio files of five minutes each.
3. A separate research agent collects relevant footage into a useful asset bank.
4. The owner edits the audio and footage in CapCut.

## Non-negotiable scope

- Work only in this new repository. Do not access or modify the previous video pipeline, Gemini API configuration, billing or other projects.
- Never rewrite, summarize, translate, fact-check into a new version, censor, expand or truncate the narration automatically. Preserve input order and characters.
- Speechify is the only synthesis provider. No provider/model fallback without an explicit owner decision.
- Keep API input chunks large. Split text only to fit the provider ceiling, using natural boundaries when available. Export segmentation is performed locally on already generated audio.
- Five minutes means exactly 300 seconds of actual audio per complete export. Retain the final remainder. Never regenerate, time-stretch, pad or drop speech to hit a target runtime.
- The user finishes videos in CapCut. Do not build a renderer, timeline engine, scene matcher, auto editor or publishing service.
- Keep the audio engine independent of footage research, LLM vendors and research failures.
- No paid calls during installation, startup, review, tests, formatting or export. The Generate action authorizes only the reviewed generation.
- Never persist keys in code, request metadata, exception logs or Git. Do not ask the owner to paste a key into chat.
- Cache only confirmed complete audio. Hash exact request settings and verify audio integrity. Preserve cache across revisions.
- Do not automatically retry paid synthesis. Incomplete requests require specific review because the first attempt may have been charged.
- Do not claim exactly-once billing: the cache prevents repeat submissions within the retained local work directory, not across lost caches or independent computers.
- Do not invent Speechify idempotency support for synthesis. Its general idempotency guide does not establish support on this route.

## Existing starter

`narration.py` and `app.py` provide a Python standard-library desktop implementation. `tests/test_pipeline.py` verifies lossless segmentation, streaming completion checks, cache reuse and failure behavior offline. This is initial working code, not proof of live account compatibility or Windows UI validation.

Default: `simba-3.2`, example compatible English voice `geffen_32`, endpoint `https://api.speechify.ai/v1/audio/stream/with-timestamps`, PCM output at 24 kHz. Use current official Speechify API reference and the account's supported model/voice list before changing these. If a documented endpoint is unavailable, report the exact mismatch; do not silently replace the architecture or repeatedly call billable routes.

## First session

1. Read README and inspect the starter. Run offline tests. No paid calls.
2. Help the owner open the desktop app on Windows. Fix actual setup issues with the smallest change. Do not replace it with a hosted application by default.
3. Have the owner enter the API key locally. Use an owner-approved short paragraph and the Generate button for the first live sample.
4. Confirm HTTP response type, PCM header/sample rate, `speech.done`, readable WAV and audible completeness. Report actual billable characters from provider metadata if supplied.
5. Listen with the owner to choose the voice. Do not describe the default voice as quality-tested when it has not been heard.
6. Run the first real episode, then rerun without changes and verify no new synthesis request. Check generated audio duration and all output files.
7. Give the same final script to the independent footage agent using `FOOTAGE_AGENT.md`. Do not wait for footage to produce audio.

## Future changes need a concrete reason

Add a control only when the owner needs it. A small voice dropdown or local MP3 export may be useful later. Do not preemptively add accounts, databases, queues, containers, agents, subscriptions, analytics, asset-ranking frameworks or multi-provider abstractions.

The first success criterion is one real episode imported into CapCut, with complete usable audio and a relevant footage bank. It is not an elaborate dashboard.

# First message for Claude / a coding agent

I am starting a new repository named `narration-desk`. The attached starter contains the initial code; read `CLAUDE.md` and `README.md` before changing anything.

My workflow is intentionally small: I paste a final English script, Speechify makes the narration, this tool exports five-minute WAV files, and a separate agent gathers related footage. I edit everything in CapCut myself.

Start by inspecting the existing implementation and running its offline tests. Then help me launch the app on Windows and complete one short Speechify test with my key entered locally. Do not generate paid audio until I initiate the reviewed generation. Do not touch my old project, Gemini API, or existing billing settings. Do not rewrite my script, create a video editor, or add unnecessary services.

The starter has not been tested against my Speechify account, and its Windows UI still needs a live check. Verify those honestly. Preserve all completed audio and never automatically retry a potentially billable failed request.

For the second agent, use `FOOTAGE_AGENT.md`. It must gather footage relevant to my actual script, identify exact vehicles/years when relevant, record sources and reuse conditions, download permitted assets where possible, and keep undownloaded candidates separate. It must not edit the final video.

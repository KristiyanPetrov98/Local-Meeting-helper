# Retrieval stall fix — 2026-11-10

## Report and evidence

On the Windows laptop, a manual briefing stayed at “Retrieving project evidence” beyond the advertised 60-second deadline; cancellation also timed out. The operator confirmed that Ollama's `/api/tags` responds, the exact models are installed, a direct `/api/embed` call returns one embedding with CPU/context/unload settings matching the application, and `pip check` reports no broken requirements. This establishes a working standalone embedding request, not a confirmed root cause for the application stall.

Inspection found two app-side problems:

- Six local HTTPX client sites constructed a default TLS context synchronously, including the recurring resource poll. HTTPX loads/parses its CA bundle even when the eventual destination is plain HTTP. Slow filesystem/certificate loading can block the event loop and delay otherwise asynchronous deadlines, HTTP handling and cancellation. The unnecessary certificate-loading path is verified by a regression test; the operator's exact Windows delay has not been reproduced here.
- Hybrid retrieval could wait on indexing or query embeddings for essentially the full answer budget. It also generated a query embedding before checking whether that project had vectors for the current model digest.

## Changes

`ollama_http.py` now creates a dedicated HTTP-only client without CA loading. A request hook rejects HTTPS, non-loopback hosts and ports other than 11434. Proxies and redirects remain disabled. Generation, embeddings, resource polling/unloading and onboarding diagnostics/pulls all use this client. External Hugging Face model downloads retain normal HTTPS certificate verification; no system-wide TLS settings are changed.

Semantic query setup has a combined 10-second budget covering the embedding lock, model identity checks and query inference. Hybrid search falls back to actual source-verified keyword results with an explicit warning. Semantic-only searches return 503 on timeout. Projects without current vectors do not invoke query embedding inference. Project scope, valid citations, the overall answer deadline and manual-only briefing behavior remain unchanged. Generation may still wait for its shared inference lock; retrieval fallback is not a guarantee that model inference will succeed.

Fourteen new regression cases cover real HTTPX transport construction without CA loading, forbidden destinations, stalled lock/identity/embedding calls, scoped keyword fallback, empty indexes, responsive cancellation, overall deadline expiry and continuing to a cited answer after a retrieval timeout. Model/stall fixtures test orchestration; they do not establish real model latency.

See `retrieval-fix-validation.json` for the executed suites. The source application was tested on Linux. Windows/laptop confirmation and installer rebuilding remain pending. Previous M7 reports describe the prior source digest and are historical evidence; this patch does not qualify a release or refresh missing hardware evidence.

## Update and retest on the laptop

Fully quit PM Copilot before replacing files. For a Git clone:

```powershell
Set-Location "F:\Apps\PM Helper\Local-Meeting-helper"
git pull --ff-only origin main
npm.cmd run build
npm.cmd start
```

For an extracted ZIP, copy the updated repository contents into that same folder and replace source files while retaining `.venv` and `node_modules`, then run the last two commands. Dependencies/model weights have not changed. Leave the existing loopback Ollama server running.

Start a consented session, wait for a complete question in the transcript and request a briefing. Inspect Request history and any Context and retrieval notes. Test cancellation on another request. Confirm that transcript packets continue and backend controls respond during retrieval. If the stall persists, record whether packet counts freeze, the request status/error and the Ollama server log timestamps; further investigation is required rather than declaring Windows fixed.

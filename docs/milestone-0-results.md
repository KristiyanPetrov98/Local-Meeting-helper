# Milestone 0 evidence and decision

Date: 2026-11-03. **Milestone 0 is incomplete: hardware feasibility is blocked.**
This repository contains foundation, candidate probes and architecture, not a working
meeting application. No later milestone was implemented. No target-laptop configuration
has been validated or selected.

## Actual execution in this task

Host inventory: Linux x86_64, Python 3.12.14, Node v24.22.1, 5 logical CPUs reported,
35,743,748,096 bytes host RAM reported (container availability may differ). No
nvidia-smi, Ollama or dotnet executable. No Windows session/Meet/audio source.
Evidence: cloud-inventory.json, cloud-inference-attempt.json,
cloud-capture-attempt.json. These artifacts contain actual execution results, not
simulated laptop performance. No model weights downloaded or inference attempted
past the explicit missing-hardware preflight.

| Check | Outcome | Evidence / limitation |
|---|---|---|
| Inventory script execution | PASS | Actual Linux inventory recorded |
| Portable benchmark checks | PASS | 5 unittest tests executed, all passed |
| Python compilation | PASS | Both scripts passed py_compile |
| RTX 4080 identity, driver, VRAM, power limit | BLOCKED | No NVIDIA interface on host |
| 8B Q4 inference and model identity | BLOCKED | No GPU or Ollama; tag/digest not validated |
| 4096 / 6144 / 8192 VRAM and latency | UNRUN | No measurements; no numeric estimates substituted |
| Whisper Medium CUDA vs CPU | UNRUN | Model/runtime not installed; host is not target |
| Concurrent Whisper + 8B and 90-minute stability | UNRUN | Target hardware required |
| EN/BG ASR quality / actual transcript lag | UNRUN | Consented live speech required |
| Windows microphone and Meet loopback | BLOCKED | Audio probe not run on Windows |
| Chrome process-specific loopback | UNRUN | Native feasibility implementation outstanding |
| WGC selected-window capture | BLOCKED | Probe preflight returned requires Windows |
| Capture isolation, echo, two monitors, recovery | UNRUN | Operator target tests required |
| Windows full dependency lock / clean build | UNRUN | Direct pins only; no app build yet |

PASS on portable tests covers percentile computation, null empty samples, missing-GPU
preflight, non-Windows capture preflight and fixed local inference destination. It does
not validate actual Ollama, faster-whisper, WGC or WASAPI integrations. No actual GPU
memory/latency, ASR timings, or concurrency statistics are available.

## Provisional configuration, not a measured recommendation

Retain Qwen3-VL 8B instruct Q4_K_M, 4096 context, OLLAMA_NUM_PARALLEL=1 and a 2048 MiB
reserve as the first candidate. Benchmark multilingual Whisper Medium GPU
int8_float16 against CPU int8; CPU is the proposed hybrid candidate when GPU headroom
is insufficient. Neither path is selected as the final configuration. Keep embedding
and diarization models off GPU during these runs. Evaluate larger contexts only after
reserve and latency pass. Test 4B only after 8B fails measured feasibility or explicit
selection. No basis exists here to recommend replacing 8B.

## Blockers and next action

Run the documented benchmark and capture matrix on the actual Windows 11 RTX 4080
laptop, then review metadata-only results and human source/quality observations.
This cloud environment cannot expose that laptop's GPU or Windows audio session.
Native process-loopback probe and full Windows dependency lock still require work
within M0. Architecture decisions remain provisional until target evidence resolves
VRAM, thermal, latency, ASR quality and capture compatibility risks.

Stop at M0. Approval is required before M1; there is no readiness or release claim.

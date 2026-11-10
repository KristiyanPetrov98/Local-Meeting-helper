# ADR 0001: Keep 8B as the primary candidate

Accepted for feasibility design, not hardware-qualified. Start Qwen3-VL 8B Q4_K_M at
4096 context. Compare GPU and CPU Whisper Medium under the same live workload. Do not
select 4B based on this Linux environment lacking a GPU. Expand context only when
measured reserve and continuous transcription remain acceptable. No cloud inference.

# Windows capture feasibility protocol — UNVERIFIED

No Windows session, audio devices, Google Meet or WGC runtime is attached to this task.
The Python probes are candidate tooling; .NET production capture is not implemented.

## Audio

Enumerate devices using capture_probe.py devices. With recording consent, choose the
WASAPI loopback corresponding to Meet's actual output, not a default device guess:

```powershell
.\.venv\Scripts\python scripts/capture_probe.py audio --device 12 --consent --seconds 120 --output results/headphones-loopback.json
```

Run a second instance on microphone index; use speakers then headphones. A remote
participant speaks a known script while the local mic is muted, then the local user
speaks while remote is silent. Record whether each intended source registers non-silent
callbacks and whether the other remains isolated. Nonzero RMS alone is not proof of
Meet-specific audio. Play an unrelated application concurrently: system loopback is
expected to include it. Chrome process-tree loopback needs a future C#
ActivateAudioInterfaceAsync/AUDIOCLIENT_ACTIVATION_PARAMS probe (Windows build support
must be checked). It is **not tested or implemented here**. Browser processes may
share audio; process capture is not necessarily tab capture. System output loopback
is the explicit fallback candidate, pending validation.

Record callback gaps, frame counts, overflow flags, selected route, device switch and
disconnect behavior. At 48 kHz over 120s expect approximately 5.76 million frames per
source; compare actual device rate and wall time with tolerance for startup. Unplug,
replug, change default output, mute and resume. The probe has no automatic recovery;
that capability remains unverified. Compare local+remote live transcripts manually for
echo/duplicates under speakers; energy counters cannot verify echo suppression.

## Selected window via Windows.Graphics.Capture

Create a synthetic window with a moving counter, choose its exact unique title:

```powershell
.\.venv\Scripts\python scripts/capture_probe.py window --window 'M0 test counter' --consent --seconds 120 --output results/wgc.json
```

The windows-capture dependency uses WGC. Verify actual backend behavior on target.
Frames are transient, hashed only to compare change, with only aggregate counts saved.
Use two monitors; resize/move target; cover it with another window; animate an unrelated
window while target is static; minimize, restore, close and restart target. Confirm
selected-window isolation, changing frame counts for target animation, and safe
closure. A count alone cannot prove pixel correctness or source isolation; an in-memory
human preview is still needed (not implemented). No screenshot persistence is allowed.
Protected/minimized windows can behave differently: record each actual result.

## Sharing safety

Use a private Meet with a second consenting observer. Share only a Chrome tab via
Present now > A tab; confirm preview and observer view exclude unrelated windows.
Do not claim content exclusion for whole-display/window sharing. No Electron
content-protection verification exists at M0; hide future mini window during unverified
broader sharing modes. This protocol does not enforce Meet's native picker choice.

Artifact template: timestamp, OS build, Chrome/Meet version, source type, route,
headphones/speakers, duration, expected behavior, observed counters, operator findings,
PASS/FAIL/BLOCKED/UNRUN, and reason. Never attach media or transcript contents.

# M2 implementation, dependencies and acceptance report

Date: 2026-11-06. **M2 retrieval code is implemented; real-model semantic qualification
is pending.** M1/M3 are preserved. M4–M7 were not started. This task did not validate
Windows capture, Whisper/diarization quality, laptop VRAM or continuous 8B concurrency.

## 1. Features implemented

- Project-specific document upload/drag-drop with validation, SHA-256 content hashing,
  indexing phases/errors, unchanged-content detection and retained original revisions.
- Text extraction/chunking for PDF, DOCX, PPTX, XLSX, CSV, text/Markdown, specified code
  languages, JSON/YAML/XML, GraphQL/Proto and OpenAPI specifications. Precise page,
  paragraph, heading, slide, cell-range, endpoint or code-line/character locations.
- Original modification metadata and timestamp provenance: internal > filesystem >
  import. Source bytes, revisions, chunks and vectors persist locally in SQLite.
- Per-project FTS5 lexical search; local Ollama embedding adapter, persisted normalized
  vectors and NumPy semantic retrieval; hybrid reciprocal-rank ranking and recency ties.
- Stable, verifiable citation IDs; immutable earlier source revisions; scoped citation
  validation and plain-text source previews. Project/document deletion invalidates
  removed citations and cannot delete another project's knowledge.
- Potential source-conflict flags with cited differing values and newest-source preference.
- Queued indexing with parser subprocess/resource limits, deferred work during active
  sessions, bounded embedding batches and query access between background batches.
- Dashboard document management, search modes, source browsing/previews, model/dependency
  diagnostics, reindex and confirmed deletion. Missing embeddings are an explicit
  keyword-only mode, never simulated semantic results.

## 2. Files/components changed

| Area | Main changes |
|---|---|
| API / storage | document_api.py, document_store.py, documents.py, document_parser.py, document_worker.py, embeddings.py; Store/app integration |
| Dashboard | KnowledgePanel.tsx, client upload method, shared-state integration and styles |
| Contracts | Regenerated OpenAPI and TypeScript document/search/citation schemas |
| Dependencies / setup | requirements-documents.in/.lock, scripts/setup-m2.ps1 |
| Tests | tests/api/test_documents.py; no-model portable fixtures; tests/e2e/m2.spec.ts and shared Electron helpers |
| Documentation / CI | This report, m2-architecture.md, dependency/validation JSON, README/component notes and existing CI installation steps |

All paths above are relative to their existing services/api, apps/web, packages,
scripts, tests or docs boundaries. Original M0/M1/M3 reports and code remain present.
No commit, push, environment publication or external deployment was performed.

## 3. Dependency check and actual installation

Recorded evidence: **m2-dependencies.json**. Actual host is Linux, Python 3.12.14,
SQLite 3.53.1. FTS5 creation/query support was tested successfully. Existing NumPy,
PyYAML and HTTPX were reused. Missing parser packages were installed with artifact-hash
verification from the generated universal lock; pip check reports no broken requirements.

| Component | Version / status |
|---|---|
| pypdf | 6.1.3 installed |
| python-docx | 1.2.0 installed |
| python-pptx | 1.0.2 installed |
| openpyxl | 3.1.5 installed |
| defusedxml | 0.7.1 installed |
| NumPy | 2.2.6 installed |
| PyYAML | 6.0.3 installed |
| HTTPX | 0.28.1 installed |
| lxml / Pillow / XlsxWriter | Transitive dependencies installed and locked |
| SQLite FTS5 | Available and exercised |
| Ollama runtime | CLI absent; local model API unavailable |
| qwen3-embedding:0.6b | Missing / not run |
| Official model registry | Environment proxy rejected CONNECT with 403 |

No new credentials are required for the ordinary public Ollama embedding model. The
remaining requirement is local Ollama plus the exact model. Keyword search/import can
be tested without either. No separate database server, GPU, C# helper, cloud account
or hosted inference is required for M2. M3's optional native/model prerequisites remain
separate. Windows installation of the new lock is provided, not claimed as executed.

## 4. Tests actually executed

Final results are recorded in m2-validation.json. The Linux run executed:

- **70 API/parser/pipeline tests passed**, including 45 M2 cases and the 24 existing
  M1/M3 cases plus immediate parent-death process cleanup. Actual PDF/Office containers were generated/read, and actual parser
  subprocesses, SQLite FTS5, retention/isolation and stored-source verification ran.
- **6 Electron/Playwright tests passed**, including real upload, browser File/drag-drop,
  indexing, keyword search, preview, changed-file revisions, earlier citation resolution,
  project switching, restart and deletion. Existing M1/M3 flows also ran.
- **4 Vitest shell tests**, **5 preserved M0 unittest checks**, and **3 .NET audio tests**
  passed. Total: **88 passed, zero failures/skips on this Linux run**.
- TypeScript checks, production web/Electron builds, Python compilation, contract
  generation/consistency and dependency compatibility checks passed.

Semantic protocol, ranking, caching and model-digest tests use explicit deterministic
fixtures and actual NumPy operations. They do **not** prove real Qwen embedding quality,
latency or Ollama CPU residency. A transport fixture asserts fixed loopback destination,
CPU options, keep_alive=0 and no outbound proxy/redirect use. Production code contains
no fake-vector fallback. Actual local Ollama availability and registry access were
checked separately and failed as recorded above.

Parent-death cleanup was strengthened so pending HTTP model requests cannot delay
killing owned capture/model/parser children; real child-process termination and
Electron crash recovery were tested. The initial API run found a parser-worker working-directory dependency; it was fixed
and the entire suite rerun successfully. Citation checks also reject corrupted quotes
and locations, cross-project IDs, invented IDs and deleted references. Incremental
cache reuse, model changes, queued-job restart recovery, file limits and non-execution
of imported code are tested. Remote CI workflows were updated, not executed here.

## 5. Acceptance and remaining limitations

| Criterion | Result |
|---|---|
| Supported parser families and source locations | PASS for exercised fixtures |
| Upload, local persistence, incremental revisions and progress/errors | PASS |
| Project-specific lexical search and independent FTS statistics | PASS |
| Scoped citation verification, previews and deletion | PASS |
| Hybrid/semantic protocol, NumPy ranking and vector-cache plumbing | PASS with test fixtures |
| Actual qwen3-embedding model inference and retrieval quality | **UNRUN / dependency blocked** |
| Real-model CPU placement / unloading / latency | **UNRUN** |
| Potential structured-fact conflict flags and recency provenance | PASS for exercised cases; heuristic only |
| M1/M3 automated regression checks | PASS on Linux |
| Windows end-to-end M2 install/run | **UNRUN** |
| Real 8B + ASR + retrieval workload on the RTX 4080 | **UNRUN** |

Limits are explicit: 50 documents, 20,000 current chunks/project; 20 MiB, two million
extracted characters, 10,000 units and 4,000 chunks/file; 100 chunks in the source-browse
list; ten search hits. Large archives, over-limit inputs and parser timeouts fail
visibly. Parser hard memory/CPU limits are applied on Linux; Windows process-level
memory containment is not qualified. Full security/performance qualification remains M7.

Scanned PDFs require Phase 2 OCR. Text-oriented Office extraction does not establish
complete coverage of complex layouts, grouped shapes, charts, diagrams or image text.
Formula text is retained without evaluating formulas or external links. Contradiction
flags cover bounded, matching scoped facts; arbitrary prose/semantic contradictions
can be missed or produce false positives. Source timestamps are reported metadata,
not independent authentication. Originals/historical revisions consume local disk until
deleted; they are not governed by transcript retention. No model-generated answers are
implemented before M4. Source deletion intentionally invalidates its citations.

## 6. Manual Windows test

Prerequisites: Python 3.12 x64 and Node 24. From the repository root:

```powershell
.\scripts\setup-m2.ps1
npm start
```

This installs the document lock and builds the application. It preserves an existing
M3 virtual environment; it does not download Whisper/diarization or build native capture.
For semantic search, install Ollama from its official distribution, start its local
service, and run this explicit one-time model installation:

```powershell
ollama pull qwen3-embedding:0.6b
ollama list
```

The download needs Internet access. Subsequent document/query embeddings are local.
Do not disable TLS verification to work around a proxy denial. Qwen3-VL 8B remains the
primary future generation candidate; no substitution or generation-model pull is part
of M2. Requests select CPU embeddings and immediate model release, but monitor the
actual laptop before treating these settings as validated GPU-resource behavior.

1. Create/select Project A. Add a Markdown/code file, a text PDF and an Office file.
   Observe queued/parsing/indexing/ready states. Without Ollama, expect the explicit
   keyword-ready warning. Check a failed/macro/over-limit file shows an error and no hits.
2. Search a unique source phrase in Keyword mode. Open View citation and verify the
   filename, hash/revision, page/heading/range/line and quote against the original file.
   Imported HTML/code must display as text and execute nothing.
3. Upload the same file unchanged: the revision should stay the same. Change one
   section and upload under the same filename: revision should increment, current
   search should reflect the change, and earlier saved citation IDs should still
   resolve to their retained source with a superseded warning.
4. Add two documents in the same scope with `release date: Monday` and `release date:
   Friday`, using distinct `updated_at` dates. Search release date; inspect both
   citations and confirm the newer revision is preferred, not silently asserted true.
5. Create Project B. Search A's unique phrase and confirm it produces no A evidence.
   Switch back to A and confirm its files/search remain. Restart and repeat.
6. With Ollama/model installed, Refresh model status, Reindex, then use Hybrid and
   Semantic-only modes with a paraphrase rather than a literal keyword. Verify relevant
   sources and measure latency. This is the outstanding real-model qualification.
7. Start a consented M1/M3 session, upload a document and confirm indexing remains
   queued. Stop/pause and confirm it resumes. Run the actual laptop concurrency test
   separately; portable regression tests do not establish uninterrupted real ASR.
8. Delete a disposable document with confirmation. Search/previews/citation resolution
   should stop returning it; another project's documents must remain intact.

Automated reproduction (activate the virtual environment before code generation):

```powershell
.\.venv\Scripts\python -m pip install --require-hashes -r services/api/requirements-dev.lock -r services/api/requirements-documents.lock
.\.venv\Scripts\python -m pytest tests/api -q
.\.venv\Scripts\python -m unittest discover -s tests -v
npm run contracts
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

The existing native .NET tests require the M3 SDK and can be run separately. The POSIX
subprocess stress fixture is intentionally skipped on Windows; portable API tests never
activate real microphones. Linux Electron requires a graphical/X display; this task
used Xorg :99 and system Chromium, with real X11 hotkey delivery enabled.

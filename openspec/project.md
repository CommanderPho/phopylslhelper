# Project Context

## Purpose
Provide a small, reliable Python helper library/CLI for working with Lab Streaming Layer (LSL) streams during neuroscience/biometrics experiments. Initial focus is on reading/writing EEG and marker streams (e.g., Emotiv EPOC), session timestamp alignment, simple buffering, and utilities to discover and monitor LSL outlets.

## Tech Stack
- **Language**: Python (>=3.9.13)
- **Core libraries**: `pylsl (>=1.17.6)`, `pytz (>=2025.2)`
- **Packaging/Env**: `pyproject.toml` (PEP 621), `uv` for dependency management/locking (`uv.lock` present)
- **Spec process**: OpenSpec (see `openspec/AGENTS.md`)
- **OS target**: Windows 10+ (cross-platform LSL where possible)

## Project Conventions

### Code Style
- Follow PEP 8 and prefer explicit, descriptive names.
- Use PEP 484 type hints for all public functions and data structures.
- Docstrings: Google-style or Numpy-style; include parameter/return descriptions and units where relevant.
- Avoid deep nesting; prefer small functions with clear responsibilities.

### Architecture Patterns
- Keep LSL I/O separated from domain logic (functional core, imperative shell).
- Prefer small, single-purpose modules (e.g., `lsl_discovery`, `lsl_reader`, `lsl_writer`, `markers`, `time_sync`).
- Design for real-time: non-blocking reads, bounded buffers, graceful reconnection.
- Keep CLI entrypoints thin; push logic into importable modules.

### Testing Strategy
- Use `pytest` for unit tests; prefer deterministic, hermetic tests for utilities.
- Provide LSL integration tests that spin up a local test stream with `pylsl.StreamInfo` and validate read/write paths. Mark with `@pytest.mark.lsl` so they can be skipped in CI if no LSL is available.
- Include time-related tests (timestamp drift, alignment) and marker round-trip tests.

### Git Workflow
- Trunk-based with short-lived feature branches: `feat/…`, `fix/…`, `chore/…`, `docs/…`.
- Conventional Commits for messages (`feat:`, `fix:`, `refactor:`, etc.).
- Use OpenSpec for any change that adds capabilities, changes behavior, or introduces patterns. Reference the `change-id` in PR titles/descriptions.

## Domain Context
- Lab Streaming Layer (LSL) provides a discovery and transport layer for time-synchronized streams (EEG, markers, etc.).
- Typical EEG streams (e.g., Emotiv EPOC) expose `type=EEG`, `channel_count`≈14–32, `channel_format=float32`, and a nominal sampling rate (e.g., 128/256 Hz). Actual device specifics vary by model/software.
- Marker streams use irregular, event-based samples (often `cf_string`) and must be timestamped precisely for alignment with continuous data streams.
- Accurate time synchronization is critical; prefer LSL-provided clock corrections and avoid blocking operations in hot paths.

## Important Constraints
- Real-time processing: minimize latency and jitter; avoid long blocking calls in reader loops.
- Robustness: handle transient disconnects and stream restarts without data loss where feasible.
- Windows 10 support is required; aim to remain cross-platform.
- Python >= 3.9.13 per `pyproject.toml`.
- External licensing or SDKs for specific devices (e.g., Emotiv) may apply; the project should not embed proprietary SDKs.

## External Dependencies
- `pylsl`: LSL bindings used for discovery, stream info, inlets/outlets, and clock synchronization.
- `pytz`: Timezone handling for logs and exported metadata.
- External systems: an LSL runtime environment with producing outlets (e.g., EEG acquisition software) on the local network/host.

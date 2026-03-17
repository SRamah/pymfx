# Changelog

All notable changes to pymfx are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.0.0] — 2026-03-16

### Added
- `pymfx.parse()` — read a `.mfx` file into Python objects
- `pymfx.write()` — serialize a `MfxFile` to `.mfx` text (auto-computes checksums)
- `pymfx.validate()` — full V01–V21 rule set from the `.mfx` v1.0 spec
- `pymfx.compute_checksum()` / `verify_checksum()` — SHA-256 per spec §7
- Dataclasses: `MfxFile`, `Meta`, `Trajectory`, `TrajectoryPoint`, `Events`, `Event`, `Index`, `Extension`, `SchemaField`
- CLI: `pymfx --validate`, `pymfx --checksum`, `pymfx --info`
- Notebooks: `01_quickstart.ipynb`, `02_build_from_scratch.ipynb`
- Zero external runtime dependencies (Python ≥ 3.10 stdlib only)

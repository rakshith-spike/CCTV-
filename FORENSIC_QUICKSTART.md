# FORENSIC-X

Multi-Vendor DVR/NVR Forensic Analysis Platform, extending the existing CamTrace CCTV application.

## Run locally

Requirements: Python 3.11+, Node.js 20+, and FFmpeg/FFprobe.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm ci --prefix frontend
npm run build --prefix frontend
python scripts/download_models.py
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

Open http://127.0.0.1:8001. The built frontend and API share this port. The existing `start.sh`, PowerShell, and Windows launchers remain available for development.

For an offline demonstration without AI initialization:

```bash
CCTV_DISABLE_AI=1 python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

This mode supports acquisition, hashing, demo recovery/search, playback, timelines, custody and reports. Real AI inference requires the original dependencies and model weights. The dashboard reports AI availability.

## Three-minute judge workflow

1. Dashboard → New forensic case. Use `CASE-2026-00421`, `Parking Area Incident`, and an investigator name (choose a different ID if it already exists).
2. Acquisition → Load demo DVR/NVR evidence. This generates three short synthetic recordings locally; no sample media or database is committed to Git.
3. Evidence → inspect vendor declarations, metadata, acquisition times, MD5 and SHA-256. Click Verify integrity now.
4. Recovery → select original evidence → Start recovery → Open recovered video.
5. Forensic Analysis → keep DEMO DATA enabled → search `Find the person carrying a red backpack` → Open evidence at the matching offset.
6. Timeline → inspect camera events and simple temporal correlations.
7. Chain of Custody → inspect the action history.
8. Reports → Generate forensic report → Open report → Print / Save as PDF.

## Inputs for real evidence

Create a case, then use Acquisition to import MP4, AVI, MKV, MOV or other supported standard videos, ZIP, IMG or BIN. Supply source, vendor, device and channel only when known. Unknown fields remain UNKNOWN. Optional recording start must include an offset, e.g. `2026-09-30T20:14:32+05:30`.

After acquisition, select Evidence → Start analysis. Refresh until the video is READY. Open Forensic Analysis, disable DEMO DATA, and search for visible objects or attributes. The existing all-footage AI investigation, camera controls, alerts and footage library remain available. Use Acquisition for the case-based forensic preservation workflow; the legacy footage library remains a general video workspace.

## Real functionality

- Persistent SQLite case/evidence records alongside existing tables.
- Logical acquisition with real MD5/SHA-256 copy verification, read-only original files and separate analysis copies.
- Explicit re-verification detects changed or missing originals and blocks failed-integrity evidence export/recovery.
- Metadata probing and intact standard-video extraction from ZIP archives.
- Existing YOLO/CLIP/Qdrant inference, video player and FFmpeg clips.
- Case-scoped search, source-offset events, supplied-time normalization and simple same-object/different-camera/120-second correlation.
- Digital custody history and saved printable HTML report snapshots, with browser PDF printing.
- Common vendor adapter registry for Hikvision, Dahua, CP Plus, Honeywell, TP-Link, Godrej, Uniview, Matrix and Generic DVR/NVR.

## Demo and limitations

Synthetic diagram footage, sample recording dates, vendor labels, scripted search findings and recovery candidate/corruption/fragmentation counts are DEMO DATA. Demo recovery copies a generated recording; it does not recover deleted sectors. Hashes, copying and playback of demo files are real.

Vendor selection is operator-declared, not automatic detection. Proprietary DVR parsers, physical imaging and universal deleted-DVR recovery are not implemented. IMG/BIN evidence can be preserved and hashed but is not automatically decoded. Unknown recording times are excluded from absolute cross-camera correlation. Correlations do not identify a person. AI relevance is not a probability or proof of an event.

The prototype has no user authentication; investigator names and supplied metadata are self-declared. Read-only permissions are not a hardware write blocker. The local custody database is not tamper-proof or legally certified. Integrity badges reflect the most recent verification; reports recheck all case evidence. Run on localhost.

## Validation

```bash
npm run build --prefix frontend
HF_HUB_OFFLINE=1 .venv/bin/python -m pytest backend/tests -q
```

The implementation was validated with a successful frontend build and 22 passing backend tests, including original AI/search/clip/live-capture tests and new forensic acquisition, tamper detection, ZIP extraction, demo, timeline and report tests. Offline test execution requires cached model weights.

Local `data/`, evidence, databases, model weights, `.env`, dependencies and build output are excluded from Git. Back up `data/` separately to retain your local cases.

import html
import json
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, field_validator
from backend.config import DATA, MAX_UPLOAD
from backend.storage import db
from backend.api.schemas import SearchRequest
from . import service as s
from .vendors import ADAPTERS

router = APIRouter(prefix='/api/forensics')
VIDEOS = {'.mp4', '.avi', '.mkv', '.mov', '.webm', '.m4v', '.wmv', '.flv', '.ts', '.3gp'}


class CaseCreate(BaseModel):
    id: str = Field(default_factory=lambda: s.ident('CASE'), pattern=r'^[A-Za-z0-9_-]{1,60}$')
    name: str = Field(min_length=1, max_length=150)
    investigator: str = Field(min_length=1, max_length=100)
    description: str = Field(default='', max_length=4000)

    @field_validator('name', 'investigator')
    @classmethod
    def clean(cls, v):
        if not v.strip():
            raise ValueError('Cannot be blank')
        return v.strip()


@router.get('/vendors')
def vendors():
    return [a.identify() for a in ADAPTERS.values()]


@router.get('/cases')
def cases():
    return db.rows('SELECT * FROM forensic_cases ORDER BY created_at DESC')


@router.post('/cases', status_code=201)
def create_case(body: CaseCreate):
    import sqlite3
    try:
        db.execute('INSERT INTO forensic_cases(id,name,investigator,description,status,created_at) VALUES(?,?,?,?,?,?)',
                   (body.id, body.name, body.investigator, body.description, 'UNDER ANALYSIS', s.now()))
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'Case ID already exists')
    s.audit(body.id, None, 'Case Created')
    return s.case(body.id)


@router.patch('/cases/{cid}')
def case_status(cid: str, status: str):
    s.case(cid)
    if status not in ('OPEN', 'UNDER ANALYSIS', 'CLOSED'):
        raise HTTPException(422, 'Invalid case status')
    db.execute('UPDATE forensic_cases SET status=? WHERE id=?', (status, cid))
    s.audit(cid, None, 'Case status changed', details=status)
    return s.case(cid)


@router.get('/summary')
def summary():
    ev = [s.evidence(r['id']) for r in db.rows('SELECT id FROM forensic_evidence')]
    events = [event for c in cases() for event in s.timeline(c['id'])]
    return dict(active_cases=sum(c['status'] != 'CLOSED' for c in cases()), evidence_sources=len(ev),
                recovered_files=sum(e['kind'] == 'DERIVED' for e in ev), forensic_events=len(events),
                ai_findings=sum(not e['demo'] and e.get('confidence') is not None for e in events),
                demo_findings=sum(e['demo'] for e in events), verified=sum(e['integrity']=='VERIFIED' for e in ev))


@router.get('/cases/{cid}')
def detail(cid: str):
    c = s.case(cid)
    evidence = [s.public(s.evidence(r['id'])) for r in db.rows('SELECT id FROM forensic_evidence WHERE case_id=?', (cid,))]
    events = s.timeline(cid)
    return dict(case=c, evidence=evidence, timeline=events, correlations=s.correlations(events),
                analysis=[json.loads(r['data']) for r in db.rows('SELECT data FROM forensic_searches WHERE case_id=? ORDER BY created_at', (cid,))],
                custody=db.rows('SELECT * FROM forensic_custody WHERE case_id=? ORDER BY seq', (cid,)),
                recovery=[json.loads(r['data']) for r in db.rows('SELECT r.data FROM forensic_recovery r JOIN forensic_evidence e ON e.id=r.evidence_id WHERE e.case_id=?', (cid,))],
                reports=db.rows('SELECT id,created_at FROM forensic_reports WHERE case_id=? ORDER BY created_at DESC', (cid,)))


@router.post('/cases/{cid}/acquire', status_code=201)
def acquire(cid: str, file: UploadFile = File(...), source: str = Form('Imported file'), vendor: str = Form('UNKNOWN'),
            device: str = Form('UNKNOWN'), channel: str = Form('UNKNOWN'), recorded_at: str = Form('')):
    s.case(cid)
    if vendor not in ADAPTERS or max(len(source), len(device), len(channel)) > 150:
        raise HTTPException(422, 'Invalid vendor or metadata too long')
    start = s.now()
    filename = Path((file.filename or 'evidence').replace('\\', '/')).name
    if Path(filename).suffix.lower() not in VIDEOS | {'.zip', '.img', '.bin'}:
        raise HTTPException(415, 'Choose a supported video, ZIP archive, IMG or BIN file')
    if recorded_at:
        try:
            dt = datetime.fromisoformat(recorded_at.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                raise ValueError()
            recorded_at = dt.isoformat()
        except ValueError:
            raise HTTPException(422, 'Recording start must include a timezone offset, or leave it blank for UNKNOWN')
    with tempfile.TemporaryDirectory(dir=DATA) as temp:
        path = Path(temp) / ('incoming' + Path(filename).suffix)
        size = 0
        with path.open('wb') as target:
            while chunk := file.file.read(1024*1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, 'Evidence exceeds upload limit')
                if shutil.disk_usage(DATA).free < len(chunk)*3 + 256*1024*1024:
                    raise HTTPException(507, 'Insufficient free storage')
                target.write(chunk)
        if not size:
            raise HTTPException(422, 'Empty evidence file')
        return s.ingest(cid, path, filename, source, vendor, device, channel, recorded_at or None, started=start)


@router.post('/evidence/{eid}/verify')
def verify(eid: str):
    return s.verify(s.evidence(eid))


@router.get('/evidence/{eid}/export')
def export(eid: str):
    e = s.evidence(eid)
    if s.verify(e)['integrity'] != 'VERIFIED':
        raise HTTPException(409, 'Evidence integrity failed; export blocked')
    s.audit(e['case_id'], eid, 'Evidence Exported', e['integrity'])
    return FileResponse(e['path'], filename=e['filename'], media_type='application/octet-stream')


@router.post('/evidence/{eid}/analyze')
def analyze(eid: str, request: Request):
    e = s.evidence(eid)
    if e['demo']:
        s.audit(e['case_id'], eid, 'Analysis Started', e['integrity'], 'DEMO DATA — scripted findings, no AI inference')
        return {'status': 'DEMO DATA — scripted findings available in forensic search'}
    if not e['metadata']:
        raise HTTPException(422, 'No decodable video; extract a supported recording first')
    if s.verify(e)['integrity'] != 'VERIFIED':
        raise HTTPException(409, 'Evidence integrity failed')
    if not request.app.state.ai_enabled:
        raise HTTPException(503, 'AI unavailable. Install full requirements and enable AI; demo search remains available.')
    # Refresh working copy only when no processing is active.
    vid = s.ensure_video(e)
    pipeline = request.app.state.pipeline
    with pipeline.lock:
        if vid in pipeline.active:
            raise HTTPException(409, 'Analysis already running')
        video = db.one('SELECT path FROM videos WHERE id=?', (vid,))
        shutil.copyfile(e['path'], video['path'])
        if s.hashes(video['path'])['sha256'] != e['sha256']:
            raise HTTPException(409, 'Analysis copy hash mismatch')
        s.audit(e['case_id'], eid, 'Analysis Started', e['integrity'])
        pipeline.enqueue(vid)
    return {'status': 'QUEUED'}


@router.post('/evidence/{eid}/recover')
def recover(eid: str):
    e = s.evidence(eid)
    if e['kind'] != 'ORIGINAL':
        raise HTTPException(422, 'Select original evidence for recovery')
    if s.verify(e)['integrity'] != 'VERIFIED':
        raise HTTPException(409, 'Evidence integrity failed')
    existing = db.one('SELECT data FROM forensic_recovery WHERE evidence_id=?', (eid,))
    if existing:
        return json.loads(existing['data'])
    s.audit(e['case_id'], eid, 'Recovery Started', e['integrity'])
    result = dict(evidence_id=eid, mode='PROTOTYPE RECOVERY', total_recordings=0, deleted_candidates=None,
                  corrupted_segments=None, fragmented_files=None, recoverable_files=0, recovered_files=0, recovered_ids=[], demo=e['demo'])
    if e['demo']:
        child = s.ingest(e['case_id'], e['path'], 'recovered-demo.mp4', 'Synthetic recovery working copy', e['vendor'], e['device'], e['channel'], e['recording_start'], True, eid)
        result.update(total_recordings=3, deleted_candidates=1, corrupted_segments=1, fragmented_files=1, recoverable_files=1, recovered_files=1, recovered_ids=[child['id']],
                      note='DEMO DATA: candidate/corruption/fragmentation counts are simulated. Playable output is a verified copy of synthetic footage; no deleted sectors were recovered.')
    elif e['format'] == 'ZIP':
        result.update(mode='STANDARD ARCHIVE EXTRACTION', corrupted_segments=0, note='Extracts intact supported videos from ZIP; does not recover deleted DVR sectors. Unsupported members are skipped.')
        try:
            with zipfile.ZipFile(e['path']) as archive:
                members = [m for m in archive.infolist() if not m.is_dir() and Path(m.filename).suffix.lower() in VIDEOS]
                if len(members) > 100 or sum(m.file_size for m in members) > min(MAX_UPLOAD, 2*1024**3):
                    raise HTTPException(413, 'Archive extraction limited to 100 recordings / 2 GB')
                result['total_recordings'] = len(members)
                with tempfile.TemporaryDirectory(dir=DATA) as temp:
                    for i, member in enumerate(members):
                        path = Path(temp) / f'member-{i}{Path(member.filename).suffix}'
                        # Never use archive member paths on disk; bound actual streamed bytes.
                        size = 0
                        with archive.open(member) as src, path.open('wb') as dst:
                            while chunk := src.read(1024*1024):
                                size += len(chunk)
                                if size > min(MAX_UPLOAD, 2*1024**3):
                                    raise HTTPException(413, 'Archive member too large')
                                dst.write(chunk)
                        try:
                            s.probe(path)
                        except ValueError:
                            result['corrupted_segments'] += 1
                            continue
                        child = s.ingest(e['case_id'], path, Path(member.filename.replace('\\', '/')).name, 'ZIP extraction', e['vendor'], e['device'], e['channel'], None, False, eid)
                        result['recovered_ids'].append(child['id'])
            result['recovered_files'] = result['recoverable_files'] = len(result['recovered_ids'])
        except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
            s.audit(e['case_id'], eid, 'Recovery Failed', e['integrity'], 'Unreadable, encrypted or invalid archive')
            raise HTTPException(422, 'Unreadable, encrypted or invalid ZIP archive') from exc
    else:
        result['note'] = 'Proprietary/deleted DVR recovery unavailable in prototype. Use DEMO DATA to demonstrate recovery or import a ZIP containing intact recordings.'
    db.execute('INSERT INTO forensic_recovery(evidence_id,data) VALUES(?,?)', (eid, json.dumps(result)))
    s.audit(e['case_id'], eid, 'Recovery Completed', e['integrity'], result['note'])
    return result


@router.post('/cases/{cid}/demo')
def load_demo(cid: str):
    s.case(cid)
    existing = [s.public(s.evidence(r['id'])) for r in db.rows('SELECT id FROM forensic_evidence WHERE case_id=?', (cid,))]
    if any(e['demo'] for e in existing):
        return detail(cid)
    from .demo import generate
    with tempfile.TemporaryDirectory(dir=DATA) as temp:
        path = Path(temp) / 'synthetic-demo.mp4'
        generate(path)
        for i in range(3):
            recorded = datetime(2026, 9, 30, 15, 11, 0, tzinfo=timezone.utc) + timedelta(seconds=i*30)
            e = s.ingest(cid, path, f'DEMO-CAM-{i+1:02}.mp4', 'DEMO DVR/NVR — generated diagram footage', ['Hikvision','Dahua','Uniview'][i], 'NVR (DEMO)', f'DEMO-CAM-{i+1:02}', recorded.isoformat(), True)
            event = dict(video_id=e['video_id'], camera=e['channel'], offset=4.0, timestamp=(recorded+timedelta(seconds=4)).isoformat(),
                         description='Person carrying a red backpack — scripted sample finding', object_type='person', confidence=None, demo=True)
            db.execute('INSERT INTO forensic_events(id,evidence_id,data) VALUES(?,?,?)', (s.ident('EVT'), e['id'], json.dumps(event)))
    s.audit(cid, None, 'Demo findings loaded', details='DEMO DATA — synthetic recordings, timestamps and scripted findings')
    return detail(cid)


@router.post('/cases/{cid}/search')
def forensic_search(cid: str, body: SearchRequest, request: Request, demo: bool = False):
    events = s.timeline(cid)
    s.audit(cid, None, 'Analysis Started', details=('DEMO DATA — keyword search of scripted findings: ' if demo else 'Existing AI search: ') + body.query)
    if demo:
        terms = set(re.findall(r'[a-z]+', body.query.lower())) - {'find','the','a','an','wearing','carrying','with','for','me','show','person','someone'}
        result = [e for e in events if e['demo'] and (not terms or terms <= set(re.findall(r'[a-z]+', e['description'].lower())))]
        return save_search(cid, body.query, {'mode': 'DEMO DATA — scripted keyword search, not AI inference', 'results': result})
    if not request.app.state.ai_enabled:
        raise HTTPException(503, 'Real AI is unavailable in lightweight mode. Enable the existing AI pipeline or choose DEMO DATA search.')
    matches = []
    for row in db.rows('SELECT id,video_id FROM forensic_evidence WHERE case_id=? AND video_id IS NOT NULL', (cid,)):
        if s.evidence(row['id'])['demo']:
            continue
        v = db.one('SELECT status FROM videos WHERE id=?', (row['video_id'],))
        if v['status'] != 'READY':
            continue
        result = request.app.state.search.search(**(body.model_dump() | {'video_id': row['video_id']}))
        for match in result['results']:
            matches.append(match | {'evidence_id': row['id']})
    return save_search(cid, body.query, {'mode': 'AI-ASSISTED FORENSIC ANALYSIS — retrieval scores are not probabilities', 'results': sorted(matches, key=lambda x: x['score'], reverse=True)})


def save_search(cid, query, result):
    result = result | {'query': query, 'searched_at': s.now()}
    db.execute('INSERT INTO forensic_searches(id,case_id,created_at,data) VALUES(?,?,?,?)',
               (s.ident('FIND'), cid, result['searched_at'], json.dumps(result)))
    return result


@router.post('/cases/{cid}/reports')
def report(cid: str):
    s.case(cid)
    for row in db.rows('SELECT id FROM forensic_evidence WHERE case_id=?', (cid,)):
        s.verify(s.evidence(row['id']))
    rid = s.ident('RPT')
    s.audit(cid, None, 'Report Generated', details=rid)
    snapshot = detail(cid)
    snapshot['generated_at'] = s.now()
    snapshot['final_integrity'] = 'VERIFIED' if snapshot['evidence'] and all(e['integrity']=='VERIFIED' for e in snapshot['evidence']) else 'NOT VERIFIED'
    snapshot['limitations'] = 'Local prototype. Digital chain-of-custody log is not legally certified or tamper-proof. Operator identities and metadata are self-declared. Demo entries are synthetic. No universal proprietary DVR parsing or deleted-sector recovery. Correlations are temporal/object heuristics, not identity matches.'
    db.execute('INSERT INTO forensic_reports(id,case_id,created_at,data) VALUES(?,?,?,?)', (rid, cid, snapshot['generated_at'], json.dumps(snapshot)))
    return {'id': rid, 'url': f'/api/forensics/reports/{rid}'}


@router.get('/reports/{rid}')
def get_report(rid: str):
    row = db.one('SELECT data FROM forensic_reports WHERE id=?', (rid,))
    if not row:
        raise HTTPException(404, 'Report not found')
    report = json.loads(row['data'])
    def render(value):
        if isinstance(value, dict):
            return '<table>' + ''.join('<tr><th>' + html.escape(str(k).replace('_', ' ').title()) + '</th><td>' + render(v) + '</td></tr>' for k, v in value.items()) + '</table>'
        if isinstance(value, list):
            return ''.join('<article>' + render(v) + '</article>' for v in value) or '<p>None recorded</p>'
        return html.escape('UNKNOWN' if value is None else str(value))
    sections = ''.join('<section><h2>' + html.escape(title.replace('_', ' ').title()) + '</h2>' + render(value) + '</section>' for title, value in report.items() if title != 'reports')
    return HTMLResponse('<!doctype html><html><head><meta charset="utf-8"><title>FORENSIC-X Report</title><style>body{font:14px system-ui;max-width:1000px;margin:40px auto;padding:24px;color:#172213}table{border-collapse:collapse;width:100%;table-layout:fixed}td,th{border:1px solid #ddd;text-align:left;vertical-align:top;padding:8px;overflow-wrap:anywhere}th{width:24%;background:#f4f6f1}article{margin:16px 0}h2{border-bottom:2px solid #92af6c;padding-bottom:8px}section{margin:32px 0}@media print{button{display:none}body{font-size:10px;margin:0}tr{break-inside:avoid}}</style></head><body><h1>FORENSIC-X · Forensic Report</h1><p>Multi-Vendor DVR/NVR Forensic Analysis Platform</p><button onclick="window.print()">Print / Save as PDF</button>' + sections + '</body></html>')

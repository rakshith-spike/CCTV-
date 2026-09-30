"""Local forensic records layered on the existing SQLite/video pipeline."""
import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import HTTPException
from backend.config import DATA
from backend.storage import db
from backend.processing.media import probe
from .vendors import ADAPTERS


def now():
    return datetime.now(timezone.utc).isoformat()


def ident(prefix):
    return prefix + '-' + uuid.uuid4().hex[:12].upper()


def init():
    (DATA / 'evidence').mkdir(exist_ok=True)
    with db.connection() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS forensic_cases(id TEXT PRIMARY KEY, name TEXT NOT NULL, investigator TEXT NOT NULL, description TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL, demo INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS forensic_evidence(id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES forensic_cases(id), video_id TEXT REFERENCES videos(id), parent_id TEXT REFERENCES forensic_evidence(id), data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS forensic_custody(seq INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT REFERENCES forensic_cases(id), evidence_id TEXT, action TEXT, actor TEXT, timestamp TEXT, integrity TEXT, details TEXT);
        CREATE TABLE IF NOT EXISTS forensic_recovery(evidence_id TEXT PRIMARY KEY REFERENCES forensic_evidence(id), data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS forensic_events(id TEXT PRIMARY KEY, evidence_id TEXT REFERENCES forensic_evidence(id), data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS forensic_searches(id TEXT PRIMARY KEY, case_id TEXT REFERENCES forensic_cases(id), created_at TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS forensic_reports(id TEXT PRIMARY KEY, case_id TEXT REFERENCES forensic_cases(id), created_at TEXT, data TEXT NOT NULL);
        ''')


def case(cid):
    result = db.one('SELECT * FROM forensic_cases WHERE id=?', (cid,))
    if not result:
        raise HTTPException(404, 'Case not found')
    return result


def audit(cid, eid, action, integrity='NOT VERIFIED', details='', actor=None):
    db.execute('INSERT INTO forensic_custody(case_id,evidence_id,action,actor,timestamp,integrity,details) VALUES(?,?,?,?,?,?,?)',
               (cid, eid, action, actor or case(cid)['investigator'], now(), integrity, details))


def evidence(eid):
    row = db.one('SELECT * FROM forensic_evidence WHERE id=?', (eid,))
    if not row:
        raise HTTPException(404, 'Evidence not found')
    return json.loads(row['data']) | {k: row[k] for k in ('id', 'case_id', 'video_id', 'parent_id')}


def save(e):
    db.execute('UPDATE forensic_evidence SET video_id=?,data=? WHERE id=?',
               (e.get('video_id'), json.dumps(e), e['id']))


def public(e):
    result = {k: v for k, v in e.items() if k != 'path'}
    if e.get('video_id'):
        v = db.one('SELECT status,error FROM videos WHERE id=?', (e['video_id'],))
        result['analysis_status'] = v['status'] if v else 'UNAVAILABLE'
        result['analysis_error'] = v['error'] if v else None
        result['source_url'] = f"/api/videos/{e['video_id']}/source"
    return result


def hashes(path):
    md5, sha = hashlib.md5(), hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            md5.update(chunk)
            sha.update(chunk)
    return {'md5': md5.hexdigest(), 'sha256': sha.hexdigest()}


def verify(e):
    try:
        current = hashes(e['path'])
        status = 'VERIFIED' if all(current[k] == e[k] for k in current) else 'MISMATCH'
    except OSError:
        current, status = {}, 'MISSING'
    e.update(integrity=status, verified_at=now(), current_hashes=current)
    save(e)
    audit(e['case_id'], e['id'], 'Integrity checked', status)
    return public(e)


def ingest(cid, path, filename, source='Imported file', vendor='UNKNOWN', device='UNKNOWN', channel='UNKNOWN', recorded_at=None, demo=False, parent=None, started=None):
    case(cid)
    eid = ident('EVD')
    suffix = Path(filename).suffix.lower()
    target = DATA / 'evidence' / (eid + suffix)
    start = started or now()
    expected = hashes(path)
    shutil.copyfile(path, target)
    actual = hashes(target)
    if actual != expected:
        target.unlink()
        raise HTTPException(409, 'Acquisition copy hash mismatch')
    target.chmod(0o444)
    metadata = {}
    if suffix not in ('.zip', '.img', '.bin'):
        try:
            metadata = probe(target)
        except ValueError:
            pass  # Preserve unreadable evidence, too.
    end = None
    if recorded_at and metadata:
        end = (datetime.fromisoformat(recorded_at) + timedelta(seconds=metadata['duration'])).isoformat()
    e = dict(id=eid, case_id=cid, filename=filename, path=str(target), size=target.stat().st_size,
             source=source, **ADAPTERS[vendor].identify(), device=device, channel=channel,
             format=suffix.lstrip('.').upper(), codec=metadata.get('codec', 'UNKNOWN'),
             recording_start=recorded_at, recording_end=end,
             timezone='UTC offset supplied by operator' if recorded_at else 'UNKNOWN',
             timestamp_basis='DEMO DATA' if demo else 'Operator supplied' if recorded_at else 'UNKNOWN',
             acquisition_start=start, acquisition_end=now(), acquisition_method='DEMO ACQUISITION — synthetic file copy' if demo else 'Logical file acquisition — verified copy (no physical disk imaging)',
             read_only=True, status='ACQUIRED', integrity='VERIFIED', verified_at=now(),
             **actual, metadata=metadata, demo=demo, kind='DERIVED' if parent else 'ORIGINAL', parent_id=parent, video_id=None)
    db.execute('INSERT INTO forensic_evidence(id,case_id,parent_id,data) VALUES(?,?,?,?)', (eid, cid, parent, json.dumps(e)))
    for action in ('Evidence Imported', 'Evidence Acquired', 'MD5 + SHA-256 Generated'):
        audit(cid, eid, action, 'VERIFIED', e['acquisition_method'])
    if metadata:
        ensure_video(e)
    return public(e)


def ensure_video(e):
    if e.get('video_id'):
        return e['video_id']
    vid = str(uuid.uuid4())
    path = DATA / 'uploads' / (vid + Path(e['filename']).suffix)
    shutil.copyfile(e['path'], path)
    if hashes(path)['sha256'] != e['sha256']:
        path.unlink(missing_ok=True)
        raise HTTPException(409, 'Analysis copy hash mismatch')
    cam = e['channel'] if e['channel'] != 'UNKNOWN' else 'CAM-UNSPECIFIED'
    db.execute('INSERT OR IGNORE INTO cameras(id,name) VALUES(?,?)', (cam, cam))
    meta = e['metadata']
    keys = ['id', 'filename', 'path', 'camera_id', 'recorded_at', *meta]
    db.execute('INSERT INTO videos(' + ','.join(keys) + ') VALUES(' + ','.join('?' for _ in keys) + ')',
               (vid, e['filename'], str(path), cam, e['recording_start'], *meta.values()))
    e['video_id'] = vid
    save(e)
    audit(e['case_id'], e['id'], 'Analysis working copy created', e['integrity'])
    return vid


def timeline(cid):
    case(cid)
    events = []
    for row in db.rows('SELECT id FROM forensic_evidence WHERE case_id=?', (cid,)):
        e = evidence(row['id'])
        stored = db.rows('SELECT id,data FROM forensic_events WHERE evidence_id=?', (e['id'],))
        for event in stored:
            events.append(json.loads(event['data']) | {'id': event['id'], 'evidence_id': e['id']})
        if not e.get('video_id') or e['demo']:
            continue
        for segment in db.rows('SELECT id,timestamp,payload FROM video_segments WHERE video_id=? ORDER BY timestamp', (e['video_id'],)):
            payload = json.loads(segment['payload'])
            for i, detection in enumerate(payload.get('detected_objects', [])):
                offset = segment['timestamp']
                absolute = (datetime.fromisoformat(e['recording_start']) + timedelta(seconds=offset)).astimezone(timezone.utc).isoformat() if e['recording_start'] else None
                events.append(dict(id=f"{segment['id']}-{i}", evidence_id=e['id'], video_id=e['video_id'], camera=e['channel'], offset=offset,
                                   timestamp=absolute, description=detection['label']+' detected', object_type=detection['label'],
                                   confidence=detection.get('confidence'), demo=False))
        for a in db.rows('SELECT * FROM alerts WHERE video_id=?', (e['video_id'],)):
            absolute = (datetime.fromisoformat(e['recording_start']) + timedelta(seconds=a['timestamp'])).astimezone(timezone.utc).isoformat() if e['recording_start'] else None
            events.append(dict(id=a['id'], evidence_id=e['id'], video_id=e['video_id'], camera=e['channel'], offset=a['timestamp'], timestamp=absolute, description=a['event_type']+': '+a['details'], object_type='rule event', confidence=None, demo=False))
    return sorted(events, key=lambda x: (x['timestamp'] is None, x['timestamp'] or '', x['evidence_id'], x['offset']))


def correlations(events):
    result = []
    for i, a in enumerate(events):
        if not a['timestamp']:
            continue
        for b in events[i+1:]:
            if not b['timestamp'] or a['camera'] == b['camera'] or a['object_type'] != b['object_type'] or a['demo'] != b['demo']:
                continue
            delta = abs((datetime.fromisoformat(b['timestamp'])-datetime.fromisoformat(a['timestamp'])).total_seconds())
            if delta <= 120:
                result.append(dict(first=a['id'], second=b['id'], seconds=delta, basis='Same object type, different camera, within 120 seconds; not identity matching', demo=a['demo']))
    return result

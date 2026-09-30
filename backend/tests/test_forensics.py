import hashlib
import io
import json
import zipfile
from pathlib import Path
from backend.forensics import service as s
from backend.storage import db


def create(client):
    r = client.post('/api/forensics/cases', json={'id':'CASE-2026-00421','name':'Parking Area Incident','investigator':'Investigator'})
    assert r.status_code == 201, r.text
    return r.json()['id']


def test_acquisition_hashes_mismatch_and_report(client):
    cid = create(client)
    original = b'opaque DVR image\x00\x01'
    r = client.post(f'/api/forensics/cases/{cid}/acquire', files={'file':('source.img', original)}, data={'vendor':'UNKNOWN'})
    assert r.status_code == 201, r.text
    e = r.json()
    assert 'path' not in e
    assert e['md5'] == hashlib.md5(original).hexdigest()
    assert e['sha256'] == hashlib.sha256(original).hexdigest()
    assert e['recording_start'] is None and e['timezone'] == 'UNKNOWN'
    assert e['integrity'] == 'VERIFIED'
    path = Path(s.evidence(e['id'])['path'])
    assert path.stat().st_mode & 0o222 == 0
    assert client.get(f"/api/forensics/evidence/{e['id']}/export").content == original
    path.chmod(0o644)
    path.write_bytes(b'tampered')
    result = client.post(f"/api/forensics/evidence/{e['id']}/verify").json()
    assert result['integrity'] == 'MISMATCH'
    assert result['sha256'] == e['sha256']  # Never overwrite baseline hashes.
    assert client.get(f"/api/forensics/evidence/{e['id']}/export").status_code == 409
    assert client.post(f"/api/forensics/evidence/{e['id']}/recover").status_code == 409
    report = client.post(f'/api/forensics/cases/{cid}/reports').json()
    snapshot = json.loads(db.one('SELECT data FROM forensic_reports WHERE id=?',(report['id'],))['data'])
    assert snapshot['final_integrity'] == 'NOT VERIFIED'
    assert any(a['action'] == 'Report Generated' for a in snapshot['custody'])
    page = client.get(report['url'])
    assert page.status_code == 200 and 'MISMATCH' in page.text


def test_demo_recovery_search_timeline_player_and_report(client):
    cid = create(client)
    r = client.post(f'/api/forensics/cases/{cid}/demo')
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data['evidence']) == 3 and len(data['timeline']) == 3
    assert len(data['correlations']) == 3
    e = data['evidence'][0]
    assert e['demo'] and e['video_id']
    source = client.get(e['source_url'], headers={'Range':'bytes=0-100'})
    assert source.status_code == 206 and len(source.content) == 101
    assert client.delete('/api/videos/'+e['video_id']).status_code == 409
    recovered = client.post(f"/api/forensics/evidence/{e['id']}/recover").json()
    assert recovered['recovered_files'] == 1 and recovered['demo']
    assert client.post(f"/api/forensics/evidence/{e['id']}/recover").json() == recovered
    child = s.evidence(recovered['recovered_ids'][0])
    assert child['parent_id'] == e['id'] and child['sha256'] == e['sha256']
    results = client.post(f'/api/forensics/cases/{cid}/search?demo=true', json={'query':'Find the person carrying a red backpack'}).json()
    assert len(results['results']) == 3
    assert not client.post(f'/api/forensics/cases/{cid}/search?demo=true', json={'query':'white car'}).json()['results']
    event = results['results'][0]
    clip = client.post('/api/clips', json={'video_id':event['video_id'],'start':event['offset'],'end':event['offset']+3,'context':False})
    assert clip.status_code == 200, clip.text
    assert clip.json()['start'] == 4
    assert client.get(clip.json()['url']).status_code == 200
    report = client.post(f'/api/forensics/cases/{cid}/reports').json()
    assert client.get(report['url']).status_code == 200
    assert len(client.post(f'/api/forensics/cases/{cid}/demo').json()['evidence']) == 4  # Idempotent demo loader.


def test_zip_extraction_preserves_paths_and_unknown_time(client):
    from backend.forensics.demo import generate
    import tempfile
    cid = create(client)
    with tempfile.TemporaryDirectory() as temp:
        video = Path(temp)/'sample.mp4'
        generate(video)
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, 'w') as archive:
            archive.writestr('../../escape.mp4', video.read_bytes())
            archive.writestr('broken.mp4', b'broken recording')
        e = client.post(f'/api/forensics/cases/{cid}/acquire', files={'file':('recordings.zip',payload.getvalue())}).json()
        r = client.post(f"/api/forensics/evidence/{e['id']}/recover")
        assert r.status_code == 200, r.text
        r = r.json()
        assert r['recovered_files'] == 1 and r['corrupted_segments'] == 1
        child = s.evidence(r['recovered_ids'][0])
        assert child['filename'] == 'escape.mp4' and not child['demo']
        assert Path(child['path']).parent == s.DATA/'evidence'
        assert child['recording_start'] is None


def test_validation_and_unknown_time_exclusion(client):
    cid = create(client)
    assert client.post('/api/forensics/cases', json={'id':cid,'name':'x','investigator':'y'}).status_code == 409
    assert client.post(f'/api/forensics/cases/{cid}/acquire', files={'file':('x.bin',b'x')}, data={'vendor':'Made up'}).status_code == 422
    assert client.post(f'/api/forensics/cases/{cid}/acquire', files={'file':('x.bin',b'x')}, data={'recorded_at':'2026-09-30T12:00:00'}).status_code == 422
    assert client.post(f'/api/forensics/cases/{cid}/acquire', files={'file':('x.bin',b'')}).status_code == 422
    assert client.get('/api/forensics/cases/missing').status_code == 404
    unknown = dict(id='a',timestamp=None,camera='A',object_type='person',demo=False)
    known = dict(id='b',timestamp='2026-09-30T12:00:00+00:00',camera='B',object_type='person',demo=False)
    assert s.correlations([unknown,known]) == []

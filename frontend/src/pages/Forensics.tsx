import { useEffect, useState } from 'react';
import { api, post, time } from '../services/api';
import InvestigationView from '../components/InvestigationView';

const root = '/forensics';
export default function Forensics({ page, navigate }: { page: string; navigate: (p: string) => void }) {
  const [cases, setCases] = useState<any[]>([]);
  const [cid, setCid] = useState(localStorage.getItem('forensic-case') || '');
  const [data, setData] = useState<any>(null);
  const [selected, setSelected] = useState('');
  const [vendors, setVendors] = useState<any[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [match, setMatch] = useState<any>(null);
  const [results, setResults] = useState<any>(null);
  const [demo, setDemo] = useState(true);
  const [query, setQuery] = useState('Find the person carrying a red backpack');
  async function refresh(id = cid) {
    const all = await api(root + '/cases'); setCases(all);
    if (id) setData(await api(root + `/cases/${id}`));
  }
  async function run(work: () => Promise<any>) {
    setBusy(true); setError(''); setNotice('');
    try { await work(); } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  useEffect(() => { void run(async () => { await refresh(); setVendors(await api(root + '/vendors')); }); }, [cid, page]);
  useEffect(() => { setMatch(null); setResults(null); }, [page, cid]);
  function choose(id: string) { setCid(id); localStorage.setItem('forensic-case', id); setData(null); setSelected(''); setResults(null); }
  const evidence = data?.evidence || [];
  const active = evidence.find((e: any) => e.id === selected) || evidence[0];
  function openEvent(event: any) {
    const e = evidence.find((x: any) => x.id === event.evidence_id);
    if (!e?.video_id) return;
    if ('score' in event) { setMatch(event); return; }
    setMatch({ video_id: e.video_id, camera_id: event.camera, filename: e.filename, duration: e.metadata.duration,
      timestamp: event.offset, start: event.offset, end: Math.min(e.metadata.duration, event.offset + 3),
      object_type: event.object_type, frame_path: '', event_type: event.description, recorded_at: e.recording_start });
  }
  const eventRows = (events: any[]) => <div className="panel table-wrap"><table><thead><tr><th>Evidence / Camera</th><th>Event</th><th>Timestamp / Offset</th><th>Confidence</th><th>Review</th></tr></thead><tbody>{events.map((event: any, i: number) => <tr key={event.id || i}>
    <td>{event.evidence_id}<small>{event.camera || event.camera_id}</small></td><td>{event.demo && <span className="badge">DEMO DATA</span>} {event.description || event.object_type}</td>
    <td>{event.timestamp && typeof event.timestamp === 'string' ? <><span>{event.timestamp}</span><small>{new Date(event.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST</small></> : 'Absolute time UNKNOWN'}<small>Source offset {time(event.offset ?? event.timestamp)}</small></td>
    <td>{event.demo ? 'Scripted; no AI confidence' : event.confidence != null ? event.confidence.toFixed(3) : event.score != null ? `${event.score.toFixed(3)} relevance` : 'Not available'}</td>
    <td><button onClick={() => openEvent(event)}>Open evidence</button></td></tr>)}</tbody></table>{!events.length && <p className="empty compact">No events yet. Load demo evidence or analyze a recording.</p>}</div>;
  if (match) return <><p className="note">{evidence.find((e: any) => e.video_id === match.video_id)?.demo ? 'DEMO DATA — synthetic diagram footage and scripted findings. No AI inference.' : 'Evidence working copy · source offsets shown below.'}</p><InvestigationView match={match} onClose={() => setMatch(null)} /></>;
  return <section className="forensics">
    <div className="section-heading"><div><p className="eyebrow">FORENSIC-X / INVESTIGATOR WORKSPACE</p><h1>{page === 'Investigation' ? 'AI-assisted Forensic Analysis' : page}</h1><p className="subtitle">Multi-Vendor DVR/NVR Forensic Analysis Platform</p></div>
      <button disabled={busy} onClick={() => navigate('Cases')}>+ New forensic case</button></div>
    <div className="panel forensic-toolbar"><label>Active case <select aria-label="Active case" value={cid} onChange={e => choose(e.target.value)}><option value="">Select a case</option>{cases.map(c => <option value={c.id} key={c.id}>{c.id} · {c.name}</option>)}</select></label>
      <button disabled={busy || !cid} onClick={() => void run(async () => { await post(root + `/cases/${cid}/demo`, {}); await refresh(); setNotice('DEMO DATA loaded: 3 synthetic recordings with real hashes and scripted findings.'); })}>Load demo DVR/NVR evidence</button>
      <button disabled={busy} onClick={() => void run(() => refresh())}>Refresh</button>
      {busy && <span role="status">Working…</span>}</div>
    {error && <p className="error" role="alert">{error}</p>}{notice && <p className="note" role="status">{notice}</p>}
    {page === 'Cases' && <><form className="panel forensic-form" onSubmit={ev => { ev.preventDefault(); const f = new FormData(ev.currentTarget); void run(async () => { const c = await post(root + '/cases', Object.fromEntries(f)); choose(c.id); setNotice('Case created. Open Acquisition to import evidence.'); }); }}>
      <h3>New forensic case</h3><label>Case ID<input name="id" defaultValue={`CASE-${new Date().getFullYear()}-${Date.now().toString().slice(-5)}`} required pattern="[A-Za-z0-9_-]{1,60}" /></label>
      <label>Case name<input name="name" required maxLength={150} placeholder="Parking Area Incident" /></label><label>Investigator<input name="investigator" required maxLength={100} placeholder="Investigator name (self-declared)" /></label>
      <label>Description<input name="description" maxLength={4000} /></label><button className="primary" disabled={busy}>Create case</button></form>
      {data && <div className="panel forensic-form"><h3>{data.case.name}</h3><p>{data.case.description || 'No description'}</p><p>{data.case.investigator} · Created {new Date(data.case.created_at).toLocaleString()}</p><label>Status<select value={data.case.status} onChange={e => { const status = e.target.value; void run(async () => { await api(root + `/cases/${cid}?status=${encodeURIComponent(status)}`, {method:'PATCH'}); await refresh(); }); }}>{['OPEN','UNDER ANALYSIS','CLOSED'].map(s => <option key={s}>{s}</option>)}</select></label><div className="forensic-actions">{['Acquisition','Evidence','Recovery','Timeline','Investigation','Chain of Custody','Reports'].map(p => <button key={p} onClick={() => navigate(p)}>{p === 'Investigation' ? 'Analysis' : p}</button>)}</div></div>}</>}
    {!cid && page !== 'Cases' && <div className="empty panel">Create or select a case to begin.</div>}
    {cid && page === 'Acquisition' && <form className="panel forensic-form" onSubmit={ev => { ev.preventDefault(); const form = ev.currentTarget; const body = new FormData(form); void run(async () => { const e = await api(root + `/cases/${cid}/acquire`, {method:'POST', body}); setSelected(e.id); await refresh(); setNotice(`${e.id}: ACQUIRED · MD5 + SHA-256 verified. Open Evidence for details.`); form.reset(); }); }}>
      <h3>Acquire evidence</h3><p className="note">Logical file acquisition. Read-only preserved copy; analysis uses working copies. Physical disk imaging is not implemented. Unknown metadata stays UNKNOWN.</p>
      <label>Evidence file<input name="file" type="file" accept=".mp4,.avi,.mkv,.mov,.zip,.img,.bin,.webm,.m4v,.wmv,.flv,.ts,.3gp" required /></label>
      <label>Source<input name="source" defaultValue="Imported DVR/NVR recording" maxLength={150} /></label>
      <label>Vendor (operator declared)<select name="vendor">{vendors.map(v => <option key={v.vendor}>{v.vendor}</option>)}</select></label>
      <label>Device type<select name="device"><option>UNKNOWN</option><option>DVR</option><option>NVR</option><option>CCTV</option><option>Disk image</option></select></label>
      <label>Channel<input name="channel" defaultValue="UNKNOWN" maxLength={150} /></label>
      <label>Recording start (optional ISO timestamp with UTC offset)<input name="recorded_at" placeholder="2026-09-30T20:14:32+05:30" /></label>
      <button className="primary" disabled={busy}>Start acquisition · Generate hashes</button></form>}
    {cid && ['Evidence','Recovery'].includes(page) && <><div className="panel table-wrap"><table><thead><tr><th>Evidence</th><th>Source / Vendor</th><th>Kind</th><th>Integrity at last check</th><th>Details</th></tr></thead><tbody>{evidence.map((e: any) => <tr key={e.id}><td>{e.id}<small>{e.filename}</small>{e.demo && <span className="badge">DEMO DATA</span>}</td><td>{e.source}<small>{e.vendor} · {e.device} · {e.channel}</small></td><td>{e.kind}{e.parent_id && <small>Parent {e.parent_id}</small>}</td><td>{e.integrity}<small>{new Date(e.verified_at).toLocaleString()}</small></td><td><button onClick={() => setSelected(e.id)}>Select evidence</button></td></tr>)}</tbody></table>{!evidence.length && <p className="empty compact">No evidence. Open Acquisition or load demo evidence.</p>}</div>
      {active && <div className="panel forensic-form"><h3>{active.id} · {active.filename}</h3><p className="note">{active.demo ? 'DEMO DATA · ' : ''}{active.parser_status}. Vendor basis: {active.vendor_basis}.</p>
        <div className="forensic-actions"><button disabled={busy} onClick={() => void run(async () => { await post(root + `/evidence/${active.id}/verify`, {}); await refresh(); })}>Verify integrity now</button>
          <a className="button" href={`/api/forensics/evidence/${active.id}/export`}>Export evidence</a>
          <button disabled={busy || !active.video_id} onClick={() => void run(async () => { const r = await post(root + `/evidence/${active.id}/analyze`, {}); setNotice(r.status); await refresh(); })}>Start analysis</button>
          {page === 'Recovery' && <button className="primary" disabled={busy || active.kind !== 'ORIGINAL'} onClick={() => void run(async () => { await post(root + `/evidence/${active.id}/recover`, {}); await refresh(); })}>Start recovery</button>}</div>
        {page === 'Evidence' && <><dl className="forensic-metadata">{Object.entries({ 'Case': cid, Source: active.source, Vendor: active.vendor, Device: active.device, Channel: active.channel, 'File size': `${active.size.toLocaleString()} bytes`, Format: active.format, Codec: active.codec, 'Recording start (original)': active.recording_start || 'UNKNOWN', 'Recording end': active.recording_end || 'UNKNOWN', Timezone: active.timezone, 'Normalized start (UTC)': active.recording_start ? new Date(active.recording_start).toISOString() : 'UNKNOWN', 'Timestamp basis':active.timestamp_basis, 'Acquisition start': active.acquisition_start, 'Acquisition end': active.acquisition_end, Method:active.acquisition_method, 'Original read-only':active.read_only ? 'Yes — file permissions; not a hardware write blocker' : 'No', 'Acquisition status':active.status, 'Analysis status':active.analysis_status || 'No supported video', Integrity:active.integrity, MD5:active.md5, 'SHA-256':active.sha256 }).map(([k,v]) => <div key={k}><dt>{k}</dt><dd>{String(v)}</dd></div>)}</dl>
          {active.source_url && <div className="player-panel"><div className="panel-label">{active.demo ? 'DEMO DATA — SYNTHETIC DIAGRAM FOOTAGE' : 'ANALYSIS WORKING COPY'}</div><video controls playsInline preload="metadata" src={active.source_url} onError={() => setError('Browser cannot decode this format. Use Open evidence to generate an H.264 clip.')} /><button onClick={() => openEvent({evidence_id:active.id,camera:active.channel,offset:0,object_type:'Recording',description:'Evidence review'})}>Open evidence in review player</button></div>}
          <h3>Detected events</h3>{eventRows((data?.timeline || []).filter((e:any) => e.evidence_id === active.id))}
          <h3>Digital chain-of-custody log</h3><Custody entries={(data?.custody || []).filter((e:any) => e.evidence_id === active.id)} /></>}
        {page === 'Recovery' && <><p className="note">PROTOTYPE RECOVERY · ZIP extraction is real. Deleted/corrupted/fragmented DVR recovery is demonstrated only with labelled synthetic data.</p>{(data?.recovery || []).filter((r:any) => r.evidence_id === active.id).map((r:any) => <div key={r.evidence_id}><h3>{r.demo ? 'DEMO DATA — ' : ''}{r.mode}</h3><div className="stats-grid">{['total_recordings','deleted_candidates','corrupted_segments','fragmented_files','recoverable_files','recovered_files'].map(k => <div className="panel stat" key={k}><span>{k.replaceAll('_',' ')}</span><strong>{r[k] ?? 'N/A'}</strong></div>)}</div><p className="note">{r.note}</p>{r.recovered_ids.map((id:string) => <button key={id} onClick={() => {const e = evidence.find((e:any)=>e.id===id); openEvent({evidence_id:id,camera:e.channel,offset:0,object_type:'Recovered recording',description:'Recovered evidence review'});}}>Open recovered video · {id}</button>)}</div>)}</>}
      </div>}</>}
    {cid && page === 'Investigation' && <><form className="panel forensic-form" onSubmit={e => { e.preventDefault(); void run(async () => { setResults(await post(root + `/cases/${cid}/search?demo=${demo}`, {query})); await refresh(); }); }}><label>Forensic search<input aria-label="Forensic search" value={query} onChange={e => setQuery(e.target.value)} required maxLength={500} /></label><label><input type="checkbox" checked={demo} onChange={e => {setDemo(e.target.checked); setResults(null);}} /> DEMO DATA — search scripted findings (no AI inference)</label><button className="primary" disabled={busy}>Search case evidence</button></form>{results && <><p className="note">{results.mode}</p>{eventRows(results.results)}</>}</>}
    {cid && page === 'Timeline' && <><p className="note">Absolute times are shown only when supplied. Unknown timezone recordings retain source offsets and are excluded from cross-camera time correlation.</p>{eventRows(data?.timeline || [])}<h3>Related events · simple temporal correlation</h3><p className="note">Same object type on different cameras within 120 seconds. These links do not establish the same person's identity.</p>{(data?.correlations || []).map((c:any,i:number) => <div className="panel forensic-toolbar" key={i}>{c.demo && <span className="badge">DEMO DATA</span>}{[c.first,c.second].map((id:string,j:number) => {const e = data.timeline.find((e:any)=>e.id===id); return <button key={id} onClick={()=>openEvent(e)}>{j ? '→ ' : ''}{e.camera} · {time(e.offset)}</button>;})}<span>{c.seconds}s apart</span></div>)}</>}
    {cid && page === 'Chain of Custody' && <><p className="note">DIGITAL CHAIN-OF-CUSTODY LOG · Local audit history, not legal certification. Investigator names are self-declared; no authentication is configured.</p><Custody entries={data?.custody || []} /></>}
    {cid && page === 'Reports' && <div className="panel forensic-form"><h3>Forensic report</h3><p>Re-verify all original and derived evidence, then freeze case information, acquisition, hashes, recovery, analysis, timeline, correlations and custody into a report snapshot.</p><button className="primary" disabled={busy} onClick={() => void run(async () => { await post(root + `/cases/${cid}/reports`, {}); await refresh(); setNotice('Report generated. Open the report below; Print / Save as PDF is available.'); })}>Generate forensic report</button>{(data?.reports || []).map((r:any) => <a className="button" target="_blank" rel="noreferrer" key={r.id} href={`/api/forensics/reports/${r.id}`}>Open report · {new Date(r.created_at).toLocaleString()}</a>)}</div>}
  </section>;
}
function Custody({entries}:{entries:any[]}) { return <div className="panel table-wrap"><table><thead><tr><th>UTC timestamp</th><th>Action / User</th><th>Evidence</th><th>Integrity</th></tr></thead><tbody>{entries.map(e => <tr key={e.seq}><td>{e.timestamp}</td><td>{e.action}<small>{e.actor} · {e.details}</small></td><td>{e.evidence_id || 'Case'}</td><td>{e.integrity}</td></tr>)}</tbody></table></div>; }

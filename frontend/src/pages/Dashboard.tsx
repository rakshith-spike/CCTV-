import { useEffect, useState } from "react";
import { api } from "../services/api";
import {
  Video,
  Film,
  Activity,
  Clock,
  ArrowUpRight,
  Database,
  Radio,
  Cpu,
  Layers,
  Search,
  Upload,
  MonitorPlay,
  CheckCircle2,
} from "lucide-react";
import { time } from "../services/api";

export default function Dashboard({
  data,
  health,
  navigate,
  openSearch,
}: {
  data: any;
  health: any;
  navigate: (s: string) => void;
  openSearch: (id: string) => void;
}) {
  const [forensic, setForensic] = useState<any>(null);
  useEffect(() => { api('/forensics/summary').then(setForensic).catch(() => setForensic(null)); }, [data]);
  function formatFreeDisk(bytes?: number) {
    if (!bytes) return "—";
    const gb = bytes / (1024 * 1024 * 1024);
    return `${gb.toFixed(1)} GB free`;
  }

  return (
    <>
      <div className="section-heading">
        <div>
          <p className="eyebrow">OVERVIEW / LOCAL WORKSPACE</p>
          <h1>Forensic Operations Overview</h1>
          <p className="subtitle">
            Multi-Vendor DVR/NVR Forensic Analysis Platform
          </p>
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          <button onClick={() => navigate("Acquisition")}>
            <Upload size={14} /> Acquire evidence
          </button>
          <button className="primary" onClick={() => navigate("Cases")}>
            + New forensic case
            <ArrowUpRight size={16} />
          </button>
        </div>
      </div>

      <div className="stats-grid">
        {Object.entries({"Active cases": forensic?.active_cases, "Evidence sources": forensic?.evidence_sources, "Recovered files": forensic?.recovered_files, "Forensic events": forensic?.forensic_events, "AI findings": forensic?.ai_findings, "Integrity verified": forensic ? `${forensic.verified} / ${forensic.evidence_sources}` : '—'}).map(([label,value]) => <div className="panel stat" key={label}><ShieldIcon /><span>{label}</span><strong>{value ?? '—'}</strong></div>)}
      </div>
      <p className="note">Integrity reflects the last verification; re-verify evidence before export. {forensic?.demo_findings || 0} scripted DEMO DATA findings are excluded from AI findings.</p>
      {/* System Engine Status Strip */}
      <div
        className="panel"
        style={{
          padding: "16px 20px",
          marginBottom: "24px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "14px",
          background: "#161b1e",
          border: "1px solid #283035",
          borderRadius: "6px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span className={`dot ${health ? "" : "offline"}`} />
          <strong>AI Pipeline Engine:</strong>
          <span style={{ color: "#a5b4bc", fontSize: "12px" }}>
            {health?.ai_enabled ? "Available" : "Unavailable — acquisition and demo remain available"}
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap", fontSize: "11px" }}>
          <span style={{ display: "flex", alignItems: "center", gap: "5px" }}>
            <Cpu size={13} color="var(--accent)" /> YOLOv8n ({health?.detector_acceleration || "CPU"})
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: "5px" }}>
            <Layers size={13} color="var(--accent)" /> CLIP ViT-B/32 ({health?.acceleration || "CPU"})
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: "5px" }}>
            <Database size={13} color="#9ec5db" /> Qdrant ({health?.vector_db || "Unavailable"})
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: "5px", color: "#8a98a0" }}>
            Storage: {formatFreeDisk(health?.storage_free_bytes)}
          </span>
        </div>

        <button
          onClick={() => navigate("Cameras")}
          style={{ fontSize: "11px", padding: "6px 12px" }}
        >
          <MonitorPlay size={13} /> Open Camera Wall
        </button>
      </div>

      {/* Recent Investigations & Alerts */}
      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-label">
            RECENT INVESTIGATIONS
            <SearchLink onClick={() => navigate("Investigation")} />
          </div>
          {data?.searches.length ? (
            data.searches.map((s: any) => (
              <button
                className="list-row"
                key={s.id}
                onClick={() => openSearch(s.id)}
              >
                <span>
                  <strong>{s.query}</strong>
                  <small>{new Date(s.created_at).toLocaleString()}</small>
                </span>
                <ArrowUpRight size={16} />
              </button>
            ))
          ) : (
            <div className="empty compact">
              No investigations yet. Try searching for "person in red shirt" or "white car".
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-label">
            RECENT ALERTS
            <SearchLink onClick={() => navigate("Alerts")} />
          </div>
          {data?.alerts.length ? (
            data.alerts.map((a: any) => (
              <button
                className="list-row"
                key={a.id}
                onClick={() => navigate("Alerts")}
              >
                <span>
                  <strong>{a.event_type}</strong>
                  <small>
                    Camera: {a.camera_id} · {time(a.timestamp)}
                  </small>
                </span>
                <span className={`badge ${a.status === "NEW" ? "failed" : "ready"}`}>
                  {a.status}
                </span>
              </button>
            ))
          ) : (
            <div className="empty compact">No active rule alerts.</div>
          )}
        </section>
      </div>

      {/* System Health Footer Strip */}
      <section className="panel health-strip" style={{ marginTop: "24px" }}>
        <div>
          <span className={`dot ${health ? "" : "offline"}`} />
          <strong>
            {health ? "FORENSIC-X Server Online" : "Backend Disconnected"}
          </strong>
        </div>
        <span>Device: {health?.device || "Local host"}</span>
        <span>FFmpeg: {health?.ffmpeg || "Available"}</span>
        <span>Sample Rate: {health?.sample_fps || 1} FPS</span>
      </section>
    </>
  );
}

function SearchLink({ onClick }: { onClick: () => void }) {
  return (
    <button className="text-button" onClick={onClick}>
      View all
      <ArrowUpRight size={13} />
    </button>
  );
}

function ShieldIcon() { return <CheckCircle2 size={20} />; }

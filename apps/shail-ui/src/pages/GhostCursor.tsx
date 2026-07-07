import React, { useEffect, useState } from 'react';
import { api, GhostSession, GhostSessionDetail } from '../api';

const MONO = 'ui-monospace, "SF Mono", Menlo, monospace';
const CARD = { background: '#0d0d0d', border: '1px solid #161616', borderRadius: 9 } as const;
const BTN = { background: '#222', border: '1px solid #333', color: '#fff', borderRadius: 4, padding: '4px 8px', cursor: 'pointer', fontSize: 12, fontFamily: MONO };

export function GhostCursor() {
  const [sessions, setSessions] = useState<GhostSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSession, setSelectedSession] = useState<GhostSessionDetail | null>(null);
  
  const [bulkStart, setBulkStart] = useState('');
  const [bulkEnd, setBulkEnd] = useState('');

  const fetchSessions = async () => {
    setLoading(true);
    try {
      const data = await api.getGhostSessions();
      setSessions(data);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  const openSession = async (id: string) => {
    try {
      const data = await api.getGhostSession(id);
      setSelectedSession(data);
    } catch (e) {
      console.error(e);
    }
  };

  const deleteSession = async (id: string) => {
    if (!confirm('Delete this session?')) return;
    try {
      await api.deleteGhostSession(id);
      if (selectedSession?.session_id === id) {
        setSelectedSession(null);
      }
      await fetchSessions();
    } catch (e) {
      console.error(e);
    }
  };

  const doBulkDelete = async () => {
    if (!confirm('Are you sure you want to bulk delete sessions in this range?')) return;
    try {
      const start = bulkStart ? new Date(bulkStart).toISOString() : undefined;
      let end = undefined;
      if (bulkEnd) {
        const d = new Date(bulkEnd);
        d.setUTCHours(23, 59, 59, 999);
        end = d.toISOString();
      }
      const res = await api.bulkDeleteGhostSessions(start, end);
      alert(`Deleted ${res.deleted_count} sessions.`);
      await fetchSessions();
    } catch (e) {
      console.error(e);
      alert('Bulk delete failed.');
    }
  };

  if (selectedSession) {
    return (
      <div style={{ flex: 1, overflowY: 'auto', padding: '32px 40px' }}>
        <button onClick={() => setSelectedSession(null)} style={{
          background: 'none', border: 'none', color: '#666', fontSize: 12,
          padding: 0, cursor: 'pointer', marginBottom: 18, fontFamily: MONO,
        }}>← All Sessions</button>

        <div style={{ marginBottom: 22 }}>
          <div style={{ fontSize: 11, color: '#666', letterSpacing: '0.1em', fontFamily: MONO }}>
            SESSION REPLAY · READ ONLY
          </div>
          <h1 style={{ margin: '6px 0 0', fontSize: 26, fontWeight: 500, color: '#fff' }}>
            {selectedSession.intent_text || 'Unnamed Task'}
          </h1>
          <p style={{ margin: '6px 0 0', fontSize: 12, color: '#666' }}>
            {new Date(selectedSession.created_at).toLocaleString()} · {selectedSession.status} · {selectedSession.completed_steps}/{selectedSession.total_steps} steps
          </p>
        </div>

        <div style={{ ...CARD, padding: 16 }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 14, color: '#ccc', fontFamily: MONO }}>Clicky Event Log</h3>
          {selectedSession.clicky_log && selectedSession.clicky_log.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {selectedSession.clicky_log.map((evt, idx) => (
                <div key={idx} style={{ padding: '8px 12px', background: '#111', borderRadius: 4, fontSize: 12, fontFamily: MONO, color: '#aaa' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ color: '#fff' }}>{evt.event || evt.action_type || 'event'}</span>
                    <span style={{ color: '#666' }}>{evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString() : ''}</span>
                  </div>
                  <pre style={{ margin: 0, color: '#888', whiteSpace: 'pre-wrap', overflowX: 'auto' }}>
                    {JSON.stringify(evt.properties || evt, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: 12, color: '#666' }}>No events recorded.</div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 40px', display: 'flex', flexDirection: 'column' }}>
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 11, color: '#666', letterSpacing: '0.1em', fontFamily: MONO }}>GHOST CURSOR</div>
          <h1 style={{ margin: '6px 0 0', fontSize: 26, fontWeight: 500, color: '#fff' }}>Session Viewer</h1>
          <p style={{ margin: '6px 0 0', fontSize: 12, color: '#666' }}>
            Review past executions.
          </p>
        </div>
        
        <div style={{ ...CARD, padding: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ fontSize: 11, color: '#888', fontFamily: MONO }}>Bulk Delete:</div>
          <input type="date" value={bulkStart} onChange={e => setBulkStart(e.target.value)} style={{ ...BTN }} title="Start Date (Inclusive)" />
          <span style={{ color: '#666' }}>to</span>
          <input type="date" value={bulkEnd} onChange={e => setBulkEnd(e.target.value)} style={{ ...BTN }} title="End Date (Inclusive)" />
          <button onClick={doBulkDelete} style={{ ...BTN, background: '#422', borderColor: '#633', color: '#f88' }}>Execute</button>
        </div>
      </div>

      {loading ? (
        <div style={{ color: '#666', fontSize: 13 }}>Loading sessions...</div>
      ) : sessions.length === 0 ? (
        <div style={{ color: '#666', fontSize: 13 }}>No Ghost Cursor sessions recorded yet.</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14 }}>
          {sessions.map(s => (
            <div key={s.session_id} style={{ ...CARD, padding: 16, display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, alignItems: 'flex-start' }}>
                <div style={{ fontSize: 10, color: '#666', fontFamily: MONO }}>{new Date(s.created_at).toLocaleString()}</div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={() => deleteSession(s.session_id)} style={{ background: 'none', border: 'none', color: '#844', cursor: 'pointer', fontSize: 12, padding: 0 }} title="Delete">✕</button>
                </div>
              </div>
              <div style={{ fontSize: 15, fontWeight: 500, color: '#fff', marginBottom: 8, cursor: 'pointer' }} onClick={() => openSession(s.session_id)}>
                {s.intent_text || 'Unnamed Task'}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 'auto', fontSize: 11, color: '#888', fontFamily: MONO }}>
                <span>Status: <span style={{ color: s.status === 'success' || s.status === 'completed' ? '#4a4' : s.status === 'failed' ? '#a44' : '#aaa' }}>{s.status}</span></span>
                <span>{s.completed_steps}/{s.total_steps} steps</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

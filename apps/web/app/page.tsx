'use client';

import { ChangeEvent, useEffect, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API_BASE_URL || '/api/v1';

type CaseItem = { id: string; name: string; status: string; documents: number; findings: number };
type Finding = { id: string; rule_id: string; title: string; severity: string; status: string; explanation: string; evidence: string; confidence: number };
type Report = { finding_count: number; unresolved_findings: number; screening_score: number; risk_level: string; disclaimer: string; findings: Finding[] };

async function request(path: string, options?: RequestInit) {
  const response = await fetch(API + path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || 'Request failed');
  }
  return response.json();
}

export default function Home() {
  const [health, setHealth] = useState('Checking system…');
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [selected, setSelected] = useState('');
  const [findings, setFindings] = useState<Finding[]>([]);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [caseName, setCaseName] = useState('');
  const [report, setReport] = useState<Report | null>(null);

  const load = async () => {
    try {
      const [h, c] = await Promise.all([request('/health'), request('/cases')]);
      setHealth(h.status === 'ok' ? 'System connected' : 'System unavailable');
      setCases(c.items || []);
      if (!selected && c.items?.[0]) setSelected(c.items[0].id);
    } catch (e) {
      setHealth('System unavailable');
      setMessage(e instanceof Error ? e.message : 'Unable to connect');
    }
  };

  const loadFindings = async (caseId: string) => {
    if (!caseId) return;
    try { setFindings(await request(`/cases/${caseId}/findings`)); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Unable to load findings'); }
  };

  useEffect(() => { load(); }, []);
  useEffect(() => { if (selected) loadFindings(selected); }, [selected]);

  const createCase = async () => {
    if (caseName.trim().length < 3) return setMessage('Enter an inspection case name.');
    setBusy(true);
    try {
      const created = await request('/cases', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({name: caseName.trim()}) });
      setCaseName('');
      setSelected(created.id);
      await load();
      setMessage('Inspection case created.');
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Could not create case'); }
    finally { setBusy(false); }
  };

  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !selected) return;
    setBusy(true);
    setMessage('Uploading and analyzing document…');
    setReport(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const doc = await request(`/cases/${selected}/documents`, {method:'POST', body:form});
      setMessage(`Analyzed ${doc.filename}: ${doc.findings_count ?? 0} screening finding(s).`);
      await load();
      await loadFindings(selected);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Document processing failed');
    } finally {
      setBusy(false);
      event.target.value = '';
    }
  };

  const review = async (id: string, status: 'accepted' | 'rejected' | 'needs_review') => {
    try {
      await request(`/findings/${id}`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});
      await loadFindings(selected);
      await load();
      setMessage('Finding review status updated.');
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Review failed'); }
  };

  const generateReport = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      setReport(await request(`/cases/${selected}/report`, {method:'POST'}));
      setMessage('Screening scorecard generated for human review.');
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Report generation failed'); }
    finally { setBusy(false); }
  };

  const current = cases.find(c => c.id === selected);

  return (
    <main className="shell">
      <header className="topbar">
        <div><div className="brand">ShramAI <span>Inspector</span></div><div className="sub">Evidence-first labour compliance workspace</div></div>
        <div className="status"><i />{health}</div>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">DIGITAL SHRAM SANKALP · PROBLEM #5</p>
          <h1>Inspect faster. <em>Review with evidence.</em></h1>
          <p>Upload labour records, extract text, run transparent screening checks, and keep the final decision with the authorized human reviewer.</p>
          <div className="heroActions">
            <label className="primary">Upload document<input type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" onChange={upload} disabled={!selected || busy}/></label>
            <button className="secondary" onClick={generateReport} disabled={!selected || busy}>Generate report</button>
          </div>
        </div>
        <div className="heroCard"><small>CASES</small><strong>{cases.length}</strong><span>inspection case{cases.length === 1 ? '' : 's'}</span><div className="divider"/><small>SELECTED STATUS</small><b>{current?.status?.replaceAll('_',' ') || '—'}</b></div>
      </section>

      {message && <div className="notice">{message}</div>}

      <section className="workspace">
        <aside className="panel casesPanel">
          <div className="panelHead"><div><p className="eyebrow dark">WORKSPACE</p><h2>Inspection cases</h2></div></div>
          <div className="newCase"><input value={caseName} onChange={e=>setCaseName(e.target.value)} placeholder="New case name"/><button onClick={createCase} disabled={busy}>+</button></div>
          {cases.map(c => <button className={`case ${selected === c.id ? 'selected' : ''}`} key={c.id} onClick={()=>setSelected(c.id)}><span className="caseDot"/><div><strong>{c.name}</strong><small>{c.id} · {c.documents} docs · {c.findings} findings</small></div></button>)}
        </aside>

        <section className="panel findingsPanel">
          <div className="panelHead"><div><p className="eyebrow dark">HUMAN REVIEW</p><h2>Findings {selected && <span className="count">{findings.length}</span>}</h2></div><span className="pill">Evidence-linked</span></div>
          {findings.length === 0 ? <div className="empty"><div className="emptyIcon">✓</div><h3>No findings yet</h3><p>Upload a PDF, PNG or JPEG to begin document extraction and screening.</p></div> :
            <div className="findings">{findings.map(f => <article className="finding" key={f.id}><div className="findingTop"><span className={`severity ${f.severity}`}>{f.severity}</span><span className="confidence">{f.confidence}% confidence</span></div><h3>{f.title}</h3><p>{f.explanation}</p><div className="evidence"><span>Evidence</span><code>{f.evidence}</code></div><div className="findingBottom"><small>Rule {f.rule_id} · {f.status.replaceAll('_',' ')}</small><div><button onClick={()=>review(f.id,'rejected')}>Dismiss</button><button className="accept" onClick={()=>review(f.id,'accepted')}>Accept for review</button></div></div></article>)}</div>}
        </section>
      </section>

      {report && <section className="panel report">
        <div className="panelHead"><div><p className="eyebrow dark">RISK SCREENING</p><h2>Inspection scorecard</h2></div><span className="pill">{report.risk_level} screening risk</span></div>
        <div className="reportStats"><strong>{report.screening_score}</strong><span>/ 100 screening score</span><strong>{report.finding_count}</strong><span>findings</span><strong>{report.unresolved_findings}</strong><span>needs review</span></div>
        <p>{report.disclaimer}</p>
      </section>}

      <footer>Assistive screening only · Final compliance determination remains with the authorized human reviewer · Demo data should be synthetic/redacted</footer>
    </main>
  );
}

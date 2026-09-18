'use client';

import { useEffect, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1';

type CaseItem = { id: string; name: string; status: string; documents: number; findings: number };

export default function Home() {
  const [health, setHealth] = useState('Checking API…');
  const [cases, setCases] = useState<CaseItem[]>([]);

  useEffect(() => {
    Promise.all([fetch(API + '/health').then(r => r.json()), fetch(API + '/cases').then(r => r.json())])
      .then(([h, c]) => { setHealth(h.status === 'ok' ? 'API connected' : 'API unavailable'); setCases(c.items || []); })
      .catch(() => setHealth('API unavailable'));
  }, []);

  return (
    <main className="shell">
      <header className="topbar">
        <div><div className="brand">ShramAI Inspector</div><div className="sub">AI-assisted labour compliance workspace</div></div>
        <div className="status">{health}</div>
      </header>
      <section className="hero">
        <div><p className="eyebrow">PROBLEM STATEMENT #5</p><h1>Evidence-first inspection, built for human review.</h1><p>Upload records, extract structured evidence, run deterministic checks and AI-assisted analysis, then review every finding before a report is finalized.</p><button>Start inspection</button></div>
        <div className="heroCard"><span>Today</span><strong>{cases.length ? cases.length : 0}</strong><small>active demo cases</small></div>
      </section>
      <section className="grid">
        <article><span>01</span><h2>Document intelligence</h2><p>OCR and extraction with page-level provenance for scanned records.</p></article>
        <article><span>02</span><h2>Compliance engine</h2><p>Versioned deterministic checks paired with retrieval-backed AI analysis.</p></article>
        <article><span>03</span><h2>Human verification</h2><p>Review, accept, reject or mark findings as needs review before reporting.</p></article>
      </section>
      <section className="panel"><div className="panelHead"><div><h2>Inspection cases</h2><p>Demo data only. Production connectors require authorization.</p></div><span className="pill">Synthetic</span></div>{cases.map(c => <div className="case" key={c.id}><div><strong>{c.name}</strong><small>{c.id}</small></div><div className="metrics"><span>{c.documents} docs</span><span>{c.findings} findings</span><b>{c.status.replace('_',' ')}</b></div></div>)}</section>
    </main>
  );
}

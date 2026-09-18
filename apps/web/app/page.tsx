'use client';

import { ChangeEvent, useEffect, useMemo, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API_BASE_URL || '/api/v1';

type CaseItem = { id:string; name:string; status:string; documents:number; findings:number };
type Finding = { id:string; rule_id:string; title:string; severity:string; status:string; explanation:string; evidence:string; confidence:number };
type Report = { finding_count:number; unresolved_findings:number; screening_score:number; risk_level:string; disclaimer:string };

async function request(path:string, options?:RequestInit) {
  const response = await fetch(API + path, options);
  const body = await response.json().catch(()=>({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}

export default function Home(){
  const [health,setHealth]=useState<'checking'|'online'|'offline'>('checking');
  const [cases,setCases]=useState<CaseItem[]>([]);
  const [selected,setSelected]=useState('');
  const [findings,setFindings]=useState<Finding[]>([]);
  const [tab,setTab]=useState<'overview'|'findings'|'documents'|'audit'>('overview');
  const [caseName,setCaseName]=useState('');
  const [busy,setBusy]=useState(false);
  const [notice,setNotice]=useState('');
  const [filter,setFilter]=useState('all');
  const [report,setReport]=useState<Report|null>(null);
  const [documents,setDocuments]=useState<any[]>([]);
  const [audit,setAudit]=useState<any[]>([]);

  const current=cases.find(c=>c.id===selected);
  const visibleFindings=useMemo(()=>filter==='all'?findings:findings.filter(f=>f.severity===filter),[findings,filter]);
  const score=useMemo(()=>{
    let d=0;
    findings.forEach(f=>{const w=f.severity==='high'?22:f.severity==='medium'?12:5;if(f.status==='accepted')d+=w;else if(f.status==='needs_review')d+=Math.max(1,Math.floor(w/2));});
    return Math.max(0,Math.min(100,100-d));
  },[findings]);

  const load=async()=>{
    try{
      await request('/health');
      setHealth('online');
      const c=await request('/cases');
      setCases(c.items||[]);
      if(!selected && c.items?.[0]) setSelected(c.items[0].id);
    }catch(e){setHealth('offline');setNotice(e instanceof Error?e.message:'API unavailable');}
  };
  const loadCase=async(id:string)=>{
    if(!id)return;
    try{
      const [f,d,a]=await Promise.all([request(`/cases/${id}/findings`),request(`/cases/${id}/documents`),request(`/cases/${id}/audit`)]);
      setFindings(f);setDocuments(d);setAudit(a);
    }catch(e){setNotice(e instanceof Error?e.message:'Could not load case data');}
  };
  useEffect(()=>{load();},[]);
  useEffect(()=>{loadCase(selected);},[selected]);

  const createCase=async()=>{
    if(caseName.trim().length<3)return setNotice('Enter a case name with at least 3 characters.');
    setBusy(true);
    try{
      const c=await request('/cases',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:caseName.trim()})});
      setCaseName('');setSelected(c.id);await load();setNotice('Inspection case created.');
    }catch(e){setNotice(e instanceof Error?e.message:'Could not create case');}
    finally{setBusy(false);}
  };

  const upload=async(e:ChangeEvent<HTMLInputElement>)=>{
    const file=e.target.files?.[0];e.target.value='';
    if(!file||!selected)return;
    setBusy(true);setNotice(`Analyzing ${file.name}…`);setReport(null);
    try{
      const form=new FormData();form.append('file',file);
      const d=await request(`/cases/${selected}/documents`,{method:'POST',body:form});
      setFindings(d.findings||[]);
      setNotice(`Analysis complete: ${d.findings_count} screening finding(s). AI status: ${d.ai_status}.`);
      await load();await loadCase(selected);
      setTab('findings');
    }catch(err){setNotice(err instanceof Error?err.message:'Document analysis failed');}
    finally{setBusy(false);}
  };

  const review=async(id:string,status:'accepted'|'rejected')=>{
    try{await request(`/findings/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});setFindings(x=>x.map(f=>f.id===id?{...f,status}:f));setNotice('Review decision saved.');await load();}catch(e){setNotice(e instanceof Error?e.message:'Review update failed');}
  };

  const generate=async()=>{
    setBusy(true);
    try{setReport(await request(`/cases/${selected}/report`,{method:'POST'}));setTab('overview');setNotice('Scorecard generated.');}
    catch{setReport({finding_count:findings.length,unresolved_findings:findings.filter(f=>f.status==='needs_review').length,screening_score:score,risk_level:score>=80?'Low':score>=60?'Moderate':'High',disclaimer:'Local scorecard fallback based on the findings currently loaded in this browser.'});setTab('overview');setNotice('Scorecard generated from the loaded findings.');}
    finally{setBusy(false);}
  };

  return <main className="app">
    <header className="top">
      <div className="brand"><div className="mark">S</div><div><strong>ShramAI <span>Inspector</span></strong><small>AI-assisted inspection workspace</small></div></div>
      <div className="topActions"><span className={`connection ${health}`}><i/> {health==='online'?'API connected':health==='checking'?'Connecting…':'Demo connection unavailable'}</span><button className="ghost" onClick={load}>↻ Refresh</button></div>
    </header>

    <div className="layout">
      <aside className="sidebar">
        <div className="sideLabel">WORKSPACE</div>
        {(['overview','findings','documents','audit'] as const).map(x=><button key={x} className={tab===x?'nav active':'nav'} onClick={()=>setTab(x)}><span>{x==='overview'?'⌂':x==='findings'?'◈':x==='documents'?'▤':'◷'}</span>{x[0].toUpperCase()+x.slice(1)}</button>)}
        <div className="sideDivider"/>
        <div className="sideLabel">CURRENT CASE</div>
        <select value={selected} onChange={e=>setSelected(e.target.value)} disabled={!cases.length}><option value="">Select case</option>{cases.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select>
        <div className="sideCard"><span>Problem statement</span><strong>#05</strong><small>AI-driven smart inspection for Shram Suvidha</small></div>
      </aside>

      <section className="content">
        <div className="pageHead">
          <div><p className="kicker">DIGITAL SHRAM SANKALP · PROBLEM #05</p><h1>Inspection intelligence</h1><p>Turn labour documents into evidence-linked screening signals for authorized human review.</p></div>
          <label className="uploadBtn">＋ Upload document<input type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" onChange={upload} disabled={!selected||busy}/></label>
        </div>

        {notice&&<div className={health==='offline'?'alert error':'alert'}><span>{health==='offline'?'!':'✓'}</span>{notice}<button onClick={()=>setNotice('')}>×</button></div>}

        <div className="stats">
          <div><span>ACTIVE CASE</span><strong>{current?current.name:'—'}</strong><small>{current?.id||'No case selected'}</small></div>
          <div><span>DOCUMENTS</span><strong>{documents.length}</strong><small>Uploaded records</small></div>
          <div><span>FINDINGS</span><strong>{findings.length}</strong><small>{findings.filter(f=>f.status==='needs_review').length} need review</small></div>
          <div><span>SCREENING SCORE</span><strong>{score}<em>/100</em></strong><small>{score>=80?'Low':score>=60?'Moderate':'High'} screening risk</small></div>
        </div>

        {!cases.length && <div className="emptyState"><div className="emptyArt">S</div><h2>Start an inspection case</h2><p>Create a synthetic demo case, then upload a PDF, PNG or JPEG. The platform extracts evidence and runs transparent screening checks.</p><div className="create"><input value={caseName} onChange={e=>setCaseName(e.target.value)} placeholder="e.g. Maharashtra Factory — Demo"/><button onClick={createCase} disabled={busy}>Create case</button></div></div>}

        {cases.length>0&&tab==='overview'&&<div className="grid2">
          <section className="card scoreCard"><div className="cardHead"><div><span className="mini">RISK SCREENING</span><h2>Compliance screening</h2></div><span className="badge blue">Human review</span></div><div className="scoreRow"><div className="ring"><strong>{score}</strong><span>/100</span></div><div><h3>{score>=80?'Low':score>=60?'Moderate':'High'} screening risk</h3><p>Prioritization aid based on configured findings and review status. It is not a legal compliance determination.</p><button className="darkBtn" onClick={generate} disabled={busy}>Generate scorecard →</button></div></div></section>
          <section className="card"><div className="cardHead"><div><span className="mini">QUICK START</span><h2>Inspect a document</h2></div></div><div className="steps"><div><b>01</b><span><strong>Upload</strong><small>PDF, scanned image or JPEG</small></span></div><div><b>02</b><span><strong>Extract</strong><small>Text, evidence and document signals</small></span></div><div><b>03</b><span><strong>Review</strong><small>Findings stay with a human reviewer</small></span></div></div><label className="dropzone">Drop a document here or <u>browse</u><input type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" onChange={upload} disabled={busy||!selected}/><small>Maximum 25 MB · PDF / PNG / JPEG</small></label></section>
          <section className="card wide"><div className="cardHead"><div><span className="mini">RECENT FINDINGS</span><h2>Review queue</h2></div><button className="linkBtn" onClick={()=>setTab('findings')}>View all →</button></div>{findings.length===0?<p className="muted">No findings yet. Upload a document to begin.</p>:<div className="queue">{findings.slice(0,4).map(f=><div className="queueRow" key={f.id}><span className={`sev ${f.severity}`}>{f.severity}</span><div><strong>{f.title}</strong><small>{f.evidence}</small></div><span className="confidence">{f.confidence}%</span></div>)}</div>}</section>
        </div>}

        {cases.length>0&&tab==='findings'&&<section className="card"><div className="cardHead"><div><span className="mini">HUMAN REVIEW QUEUE</span><h2>Evidence-linked findings</h2></div><div className="filters">{['all','high','medium','low'].map(x=><button key={x} className={filter===x?'filter active':'filter'} onClick={()=>setFilter(x)}>{x}</button>)}</div></div>{visibleFindings.length===0?<div className="emptySmall">No findings match this filter.</div>:<div className="findingList">{visibleFindings.map(f=><article className="findingCard" key={f.id}><div className="findingHeader"><span className={`sev ${f.severity}`}>{f.severity}</span><span className="confidence">{f.confidence}% confidence · {f.status.replaceAll('_',' ')}</span></div><h3>{f.title}</h3><p>{f.explanation}</p><div className="evidenceBox"><span>EVIDENCE</span><code>{f.evidence}</code></div><div className="findingFooter"><small>{f.rule_id}</small><div><button onClick={()=>review(f.id,'rejected')}>Dismiss</button><button className="accept" onClick={()=>review(f.id,'accepted')}>Accept</button></div></div></article>)}</div>}</section>}

        {cases.length>0&&tab==='documents'&&<section className="card"><div className="cardHead"><div><span className="mini">DOCUMENT REGISTER</span><h2>Source documents</h2></div><span className="badge blue">{documents.length} files</span></div><div className="table">{documents.length===0?<div className="emptySmall">No documents uploaded yet.</div>:documents.map(d=><div className="tableRow" key={d.id}><div className="fileIcon">PDF</div><div><strong>{d.filename}</strong><small>{d.id} · {(d.size_bytes/1024).toFixed(1)} KB</small></div><span className="statusText">{d.status}</span></div>)}</div></section>}

        {cases.length>0&&tab==='audit'&&<section className="card"><div className="cardHead"><div><span className="mini">AUDIT TRAIL</span><h2>Activity history</h2></div><span className="badge blue">Traceable</span></div><div className="timeline">{audit.length===0?<div className="emptySmall">No audit events yet.</div>:audit.map(e=><div className="event" key={e.id}><i/><div><strong>{e.action.replaceAll('_',' ')}</strong><small>{e.detail}</small><time>{new Date(e.created_at).toLocaleString()}</time></div></div>)}</div></section>}

        {report&&<section className="card reportCard"><div><span className="mini">GENERATED SCORECARD</span><h2>Inspection summary</h2><p>{report.disclaimer}</p></div><div className="reportNumbers"><strong>{report.screening_score}<small>/100</small></strong><span>{report.risk_level} risk · {report.finding_count} findings · {report.unresolved_findings} unresolved</span></div></section>}
      </section>
    </div>
    <footer>ShramAI Inspector · Assistive screening only · Synthetic/redacted demo data recommended · Final compliance determination remains with the authorized human reviewer.</footer>
  </main>
}

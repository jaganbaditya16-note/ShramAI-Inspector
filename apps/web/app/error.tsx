'use client';

export default function Error({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main style={{maxWidth:720,margin:'80px auto',padding:24,fontFamily:'system-ui'}}>
      <p style={{letterSpacing:'.12em',fontSize:12,color:'#667085'}}>SHRAMAI INSPECTOR</p>
      <h1>Something went wrong</h1>
      <p style={{color:'#667085'}}>The workspace could not render this view. No internal error details are exposed here.</p>
      <button onClick={reset} style={{padding:'10px 14px',borderRadius:10,border:'1px solid #d0d5dd',background:'#fff',cursor:'pointer'}}>Try again</button>
    </main>
  );
}

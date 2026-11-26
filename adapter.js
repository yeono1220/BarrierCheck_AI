/* Only same-origin calls; API credentials remain in local Python server. */
window.BarrierCheckAdapter = {
  isConnected: false,
  async run(pdfFile, {signal} = {}) {
    const res = await fetch('/api/review', {method:'POST', headers:{'Content-Type':'application/pdf'}, body:pdfFile, signal});
    const body = await res.json().catch(()=>null);
    if (!res.ok || !body) throw new Error(body?.error || `Backend response error (${res.status})`);
    return body.result;
  }
};
window.addEventListener('DOMContentLoaded', async () => {
  try {
    const res = await fetch('/api/status', {cache:'no-store'});
    const info = await res.json();
    if(res.ok && info.configured===true) {
      window.BarrierCheckAdapter.isConnected=true;
      window.BarrierCheckAdapter.label=info.label;
      window.BarrierCheckAdapter.outputContract=info.output_contract;
      configure();
      document.getElementById('engineText').textContent='Studio target: '+info.label;
      document.getElementById('integrationHint').textContent='Live API configured for '+info.label+'. Each PDF runs as a separate Studio job.';
    }
  } catch (_) { /* keep preview mode */ }
});

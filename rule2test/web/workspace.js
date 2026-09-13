"use strict";
const $ = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pretty = value => JSON.stringify(value, null, 2);
const code = value => "<pre>" + esc(pretty(value)) + "</pre>";
const badge = value => '<span class="badge ' + esc(value) + '">' + esc(value) + "</span>";
const details = (title, value) => "<details><summary>" + esc(title) + "</summary>" + code(value) + "</details>";
const state = {token:"", workflows:[], current:null, proposal:null, batch:null, busy:false, page:"overview"};
const titles = {overview:"Overview",intake:"Document intake",extraction:"AI rule review",tests:"Test workspace",knowledge:"Knowledge & reuse",evidence:"Run & evidence"};
function notice(message, error=false) { $("notice").hidden=false; $("notice").className=error?"error":""; $("notice").textContent=message; }
function actor() { const value=$("actor").value.trim(); if(!value) throw Error("Enter your reviewer identity in the header first."); return value; }
async function api(path, body) {
  const response=await fetch("/api/v1"+path, body===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":state.token},body:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok) throw Error((response.status===409?"Revision or state conflict. Refresh and inspect before retrying.\n":"")+(data.error||response.statusText)+(data.issues?"\n"+pretty(data.issues):""));
  return data;
}
function page(name) {
  if(!titles[name])return;
  state.page=name;
  for(const key of Object.keys(titles)) $("page-"+key).hidden=key!==name;
  document.querySelectorAll("nav [data-page]").forEach(b=>b.classList.toggle("active",b.dataset.page===name));
  $("page-title").textContent=titles[name];
}
function options(id, items, key, label) {
  const previous=$(id).value;
  $(id).innerHTML='<option value="">Select an item</option>'+items.map(x=>'<option value="'+esc(x[key])+'">'+esc(label(x))+"</option>").join("");
  if(items.some(x=>x[key]===previous))$(id).value=previous;
}
function metric(label, value, note) { return '<article class="metric"><p>'+esc(label)+'</p><strong>'+esc(value)+'</strong><small>'+esc(note)+'</small></article>'; }
function coverage(report) {
  if(!report)return "";
  return '<div class="metrics">'+["rule","branch","boundary","exception"].map(k=>metric(k[0].toUpperCase()+k.slice(1)+" coverage",(report[k].percent===null?"N/A":Number(report[k].percent).toFixed(0)+"%"),report[k].covered+" / "+report[k].total+" obligations · "+(report.mode==="executed inputs"?"executed":"designed"))).join("")+"</div>";
}
async function lists() {
  const [workflows, proposals, indexes, batches]=await Promise.all([api("/workflows"),api("/proposals"),api("/indexes"),api("/batches")]);
  state.workflows=workflows;
  options("workflow-select",workflows,"workflow_id",w=>w.title+" · r"+w.revision+" · "+w.status+" · "+w.workflow_id.slice(0,8));
  options("proposal-select",proposals,"proposal_id",p=>p.proposal_id.slice(0,8)+" · "+p.status+(p.simulated?" · simulated":""));
  options("index-select",indexes,"index_id",i=>i.index_id.slice(0,8)+" · "+i.records+" records"+(i.simulated?" · simulated":""));
  options("batch-select",batches,"batch_id",b=>b.batch_id.slice(0,8)+" · "+b.candidates+" candidates"+(b.simulated?" · simulated":""));
  $("overview-metrics").innerHTML=metric("Workflows",workflows.length,"Latest 100 workflows")+metric("Awaiting review",workflows.filter(w=>w.status==="in_review").length,"Explicit decisions required")+metric("Evidence ready",workflows.filter(w=>w.status==="evidenced").length,"Immutable execution packs")+metric("Knowledge indexes",indexes.length,"Reviewed source snapshots");
  $("workflow-list").innerHTML=workflows.length?'<div class="table-scroll"><table><thead><tr><th>Workflow</th><th>Status</th><th>Tests</th><th>Revision</th><th></th></tr></thead><tbody>'+workflows.map(w=>'<tr><td>'+esc(w.title)+'<small>'+esc(w.workflow_id)+'</small></td><td>'+badge(w.status)+'</td><td>'+w.tests+'</td><td>r'+w.revision+'</td><td><button data-open="'+esc(w.workflow_id)+'">Open workflow</button></td></tr>').join("")+"</tbody></table></div>":'<div class="empty">Your evidence story starts here. Create a synthetic workflow or import a versioned document.</div>';
  $("knowledge-sources").innerHTML=workflows.filter(w=>w.approved>0).map(w=>'<label class="check"><input type="checkbox" name="knowledge-source" value="'+esc(w.workflow_id)+'">'+esc(w.title)+" · "+esc(w.workflow_id.slice(0,8))+"</label>").join("")||'<p class="hint">Approve source tests in a workflow before building an index.</p>';
}
function w() {if(!state.current)throw Error("Select a workflow first.");return state.current.workflow;}
function actionText(action) {
  if(!action)return "—";
  return pretty(action);
}
function renderWorkflow() {
  const current=state.current;
  if(!current){
    $("context-state").textContent="No workflow selected";
    $("test-summary").innerHTML='<div class="card empty">Select or create a workflow to begin.</div>';
    $("rule-detail").innerHTML="";$("test-rows").innerHTML="";$("downloads").innerHTML="";
    $("test-count").textContent="0 tests";$("select-all").checked=false;
    return;
  }
  const wf=current.workflow;
  $("workflow-select").value=wf.workflow_id;
  $("context-state").textContent=wf.status+" · revision "+wf.revision;
  $("test-summary").innerHTML='<div class="section-heading"><h2>'+esc(current.summary.title)+'</h2>'+badge(wf.status)+"</div>"+coverage(current.coverage);
  $("rule-detail").innerHTML='<div class="rule-columns"><div><h3>PREVIOUS RULE VERSION</h3>'+wf.old_rules.map(r=>details(r.title,r)).join("")+'</div><div><h3>CURRENT RULE VERSION</h3>'+wf.new_rules.map(r=>details(r.title,r)).join("")+"</div></div>"+(wf.analysis?details("Rule delta, impact, gaps & baseline coverage",wf.analysis):'<p class="hint">Analyze the rule change to identify affected tests, missing obligations and boundary candidates.</p>');
  const decisions=Object.fromEntries(wf.approvals.map(a=>[a.subject_id,a.decision]));
  $("test-count").textContent=wf.tests.length+" tests · "+current.summary.pending+" pending";
  $("test-rows").innerHTML=wf.tests.map((t,i)=>'<tr><td><input type="checkbox" name="test-selection" value="'+i+'" aria-label="Select '+esc(t.title)+'"></td><td>'+esc(t.title)+'<small>'+esc(t.test_id)+" · r"+t.revision+" · "+esc(t.kind)+'</small></td><td><code>'+esc(pretty(t.inputs))+'</code></td><td><code>'+esc(actionText(t.expected))+'</code></td><td>'+badge(decisions[t.test_id]||"pending")+'</td><td><button data-inspect-test="'+i+'">Inspect / edit</button></td></tr>').join("")||'<tr><td colspan="6">No generated tests yet.</td></tr>';
  $("select-all").checked=false;
  $("downloads").innerHTML=(wf.evidence_id?'<a class="source-link" href="/api/v1/workflows/'+encodeURIComponent(wf.workflow_id)+'/evidence/'+encodeURIComponent(wf.evidence_id)+'" download>Download verified evidence JSON ↗</a>':'<p class="hint">Create an evidence pack after execution.</p>')+(wf.documents||[]).map(d=>'<a class="source-link" href="/api/v1/workflows/'+encodeURIComponent(wf.workflow_id)+'/sources/'+encodeURIComponent(d.document_hash)+'" download>'+esc(d.document_id)+'<small> · SHA-256 '+esc(d.document_hash)+'</small></a>').join("");
  const enabled={analyze:["draft"],"start-review":["analyzed"],finalize:["in_review"],execute:["approved"],evidence:["executed"],"reopen-review":["approved","executed","evidenced"],recover:["executing","interrupted"],"approve-tests":["in_review","approved"],"reject-tests":["in_review","approved"],"request-changes":["in_review","approved"]};
  for(const [a,statuses]of Object.entries(enabled))document.querySelectorAll('[data-action="'+a+'"]').forEach(b=>b.disabled=!statuses.includes(wf.status));
}
async function selectWorkflow(id) {
  $("gate-detail").innerHTML='<p class="hint">Evaluate the current revision to inspect quality checks.</p>';
  state.current=id?await api("/workflows/"+encodeURIComponent(id)):null;
  renderWorkflow();
  $("run-detail").innerHTML='<p class="empty">No execution run in this workflow.</p>';
  if(state.current?.workflow.last_run_id){
    const wf=w(),run=await api("/workflows/"+encodeURIComponent(wf.workflow_id)+"/runs/"+encodeURIComponent(wf.last_run_id));
    $("run-detail").innerHTML='<h3>Run '+esc(run.run_id.slice(0,8))+" · "+esc(run.status)+'</h3><p>Executed from workflow revision '+run.workflow_revision+'. Coverage below uses this archived revision, including exercised failing tests.</p>'+coverage(run.coverage)+'<div class="table-scroll"><table><thead><tr><th>Test</th><th>Result</th><th>Expected</th><th>Actual</th></tr></thead><tbody>'+run.executions.map(e=>'<tr><td>'+esc(e.test_id)+'</td><td>'+badge(e.status)+'</td><td><code>'+esc(actionText(e.expected))+'</code></td><td><code>'+esc(e.error||actionText(e.actual))+'</code></td></tr>').join("")+"</tbody></table></div>"+details("Full execution journal",run);
  }
}
async function refresh(id) {await lists(); await selectWorkflow(id||state.current?.workflow.workflow_id||$("workflow-select").value);}
async function command(name,extra={}) {
  const wf=w();
  const result=await api("/workflows/"+encodeURIComponent(wf.workflow_id)+"/"+name,{revision:wf.revision,actor:actor(),...extra});
  await refresh(wf.workflow_id);return result;
}
function dialog(title, html) {$("dialog-title").textContent=title;$("dialog-content").innerHTML=html;$("detail-dialog").showModal();}
async function proposal(id) {
  state.proposal=id?await api("/proposals/"+encodeURIComponent(id)):null;
  const p=state.proposal;
  $("proposal-detail").innerHTML=p?'<div class="status-line">'+badge(p.summary.status)+badge(p.summary.simulated?"simulated":"live provider")+'</div><p>'+esc(p.summary.provider)+" / "+esc(p.summary.model)+'</p>'+details("Source versions & exact text",p.proposal.request.sources)+details("Extracted rule output & citations",p.output)+details("Validation issues",p.summary.issues)+details("Stored review decision",p.review):"Select a proposal.";
}
async function batch(id) {
  state.batch=id?await api("/batches/"+encodeURIComponent(id)):null;
  $("batch-detail").innerHTML=state.batch?details("Candidate inputs, grounding references & provenance",state.batch.batch):"No batch selected.";
}
function selectedTests() {
  const tests=w().tests;
  return [...document.querySelectorAll('[name="test-selection"]:checked')].map(el=>({test_id:tests[Number(el.value)].test_id,revision:tests[Number(el.value)].revision}));
}
async function perform(name) {
  if(name==="quality-gate"){
    const id=w().workflow_id;
    const report=await api("/workflows/"+encodeURIComponent(id)+"/quality-gate");
    if(report.workflow_revision!==w().revision)throw Error("Workflow changed. Refresh before evaluating the gate again.");
    $("gate-detail").innerHTML='<div class="status-line">'+badge(report.verdict==="GO"?"pass":"fail")+'<strong>'+esc(report.verdict)+'</strong><span>'+esc(report.policy_version)+' · revision '+report.workflow_revision+'</span></div><p>'+esc(report.reason)+'</p><div class="table-scroll"><table><thead><tr><th>Check</th><th>Status</th><th>Observed</th><th>Requirement</th></tr></thead><tbody>'+report.checks.map(c=>'<tr><td>'+esc(c.key)+'</td><td>'+badge(c.status.toLowerCase())+'</td><td><code>'+esc(pretty(c.actual))+'</code></td><td>'+esc(c.requirement)+'</td></tr>').join("")+'</tbody></table></div>'+details("Unmeasured metrics",report.unmeasured)+details("Snapshot hashes and full report",report)+'<button data-action="download-gate">Download this gate report</button>';
    state.gate=report;
    return report.verdict+": "+report.reason;
  }
  if(name==="download-gate"){
    if(!state.gate||state.gate.workflow_id!==w().workflow_id||state.gate.workflow_revision!==w().revision)throw Error("Evaluate the current revision first.");
    const blob=new Blob([pretty(state.gate)],{type:"application/json"});
    const url=URL.createObjectURL(blob),link=document.createElement("a");
    link.href=url;link.download="quality-gate-"+state.gate.workflow_id+".json";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    return "The displayed gate snapshot was downloaded. Its report_hash uses canonical JSON.";
  }
  if(name==="ai-status"){
    const status=await api("/ai-status");
    dialog("AI configuration & local model inventory",'<p>No inference or downloads were triggered. Use ai_doctor.py --probe for an explicit capability check.</p>'+code(status));
    return "AI configuration inspected. Model quality requires a separate evaluation.";
  }
  if(name==="refresh"){await refresh();return "Workspace refreshed.";}
  if(name==="demo"){
    const result=await api("/demo",{profile:$("demo-profile").value,actor:actor()});await refresh(result.workflow_id);page("tests");return "Draft created. Analyze the change to generate test candidates.";
  }
  if(name==="import"){
    const file=$("import-file").files[0];if(!file)throw Error("Select a JSON or XLSX file.");
    if(file.size>10*1024*1024)throw Error("Source file exceeds 10 MiB.");
    const bytes=new Uint8Array(await file.arrayBuffer());let binary="";
    for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
    const body={filename:file.name,content_base64:btoa(binary),actor:actor()};
    if($("import-mapping").value.trim())body.mapping=JSON.parse($("import-mapping").value);
    const result=await api("/import",body);await refresh(result.workflow_id);page("tests");return "Source validated and archived. Draft created.";
  }
  if(name==="sample"){const s=await api("/samples/"+$("sample-profile").value);$("source-v1").value=s.v1;$("source-v2").value=s.v2;$("source-tests").value=pretty(s.existing_tests);return "Synthetic source pair loaded. Inspect before extraction.";}
  if(name==="extract"){
    const p=await api("/extract",{sources:[{document_id:"source-v1.txt",label:"v1",text:$("source-v1").value},{document_id:"source-v2.txt",label:"v2",text:$("source-v2").value}],existing_tests_json:$("source-tests").value,actor:actor()});
    await lists();$("proposal-select").value=p.proposal_id;await proposal(p.proposal_id);return "Proposal stored: "+p.status+". Inspect sources and output before review.";
  }
  if(name==="approve-proposal"||name==="reject-proposal"||name==="promote"){
    const p=state.proposal?.summary;if(!p)throw Error("Select a proposal.");
    const body={proposal_hash:p.proposal_hash,actor:actor()};
    if(name!=="promote"){body.decision=name==="approve-proposal"?"approved":"rejected";body.reason=$("proposal-reason").value;}
    const result=await api("/proposals/"+encodeURIComponent(p.proposal_id)+"/"+(name==="promote"?"promote":"review"),body);
    if(name==="promote"){await refresh(result.workflow_id);page("tests");}else await proposal(p.proposal_id);
    return name==="promote"?"Approved proposal promoted to a draft workflow.":"Rule review decision recorded.";
  }
  if(["analyze","start-review"].includes(name)){await command(name);return name==="analyze"?"Analysis complete. Inspect delta, coverage and candidates.":"Test review opened.";}
  if(["approve-tests","reject-tests","request-changes"].includes(name)){
    const selected=selectedTests();if(!selected.length)throw Error("Select at least one test to review.");
    await command("review",{tests:selected,decision:{"approve-tests":"approved","reject-tests":"rejected","request-changes":"changes_requested"}[name],reason:$("review-reason").value});
    return selected.length+" explicit review decisions saved.";
  }
  if(name==="finalize"){await command(name,{reason:$("review-reason").value});return "Review finalized. Approved tests can now run against the independent SUT.";}
  if(name==="execute"){
    await command(name,{sut:{profile:$("sut-profile").value,fault:$("sut-fault").value,min_age:Number($("sut-min").value),max_age:Number($("sut-max").value),claim_threshold:$("sut-threshold").value,deductible:$("sut-deductible").value,currency:$("sut-currency").value}});
    return "Execution completed. Inspect PASS, FAIL and ERROR results below.";
  }
  if(name==="evidence"){const e=await command(name);return "Evidence archived. SHA-256: "+e.evidence_hash;}
  if(["reopen-review","recover"].includes(name)){await command(name,{reason:$("control-reason").value});return "Workflow transition recorded. Inspect the current revision.";}
  if(name==="history"||name==="mutation"){const result=await api("/workflows/"+encodeURIComponent(w().workflow_id)+"/"+name);dialog(name==="history"?"Audit history":"Mutation analysis",code(result));return "Stored workflow details loaded.";}
  if(name==="build-index"){
    const ids=[...document.querySelectorAll('[name="knowledge-source"]:checked')].map(x=>x.value);
    if(!ids.length)throw Error("Select source workflows for the knowledge corpus.");
    const index=await api("/indexes",{workflow_ids:ids,actor:actor()});await lists();$("index-select").value=index.index_id;return "Knowledge index built with "+index.records+" reviewed records.";
  }
  if(name==="search"||name==="suggest"){
    const index=$("index-select").value;if(!index)throw Error("Select a knowledge index.");
    const body={index_id:index,query:$("search-query").value};
    if(name==="search"){$("search-results").innerHTML='<article class="card"><h3>Retrieval results</h3>'+code(await api("/search",body))+"</article>";return "Search completed. Scores are retrieval signals, not confidence probabilities.";}
    Object.assign(body,{workflow_id:w().workflow_id,revision:w().revision,actor:actor()});
    const result=await api("/suggestions",body);await lists();$("batch-select").value=result.batch_id;await batch(result.batch_id);return "Suggestion batch stored. Inspect references before attaching.";
  }
  if(name==="attach"){
    if(!state.batch)throw Error("Select a suggestion batch.");
    const b=state.batch;const result=await api("/batches/"+encodeURIComponent(b.batch.batch_id)+"/attach",{batch_hash:b.batch_hash,actor:actor()});
    await refresh(result.workflow_id);page("tests");return "Candidates attached with pending review. No automatic approvals.";
  }
  if(name==="revise-rules"){
    const wf=w();dialog("Revise the rule snapshot",'<p>Advanced typed JSON editor. Keep table references bound to the new rule hashes, preserve the table ID, and increase its version. Saving resets analysis, tests and approvals.</p><label>Table<textarea id="edit-table" rows="8">'+esc(pretty(wf.new_table))+'</textarea></label><label>Rules<textarea id="edit-rules" rows="10">'+esc(pretty(wf.new_rules))+'</textarea></label><label>Evaluation date (YYYY-MM-DD, optional)<input id="edit-asof" value="'+esc(wf.new_as_of?.$date||"")+'"></label><label>Reason<input id="edit-rule-reason"></label><button data-action="save-rules" class="primary">Save rule revision</button>');return;
  }
  if(name==="save-rules"){
    await command("revise-rules",{table:JSON.parse($("edit-table").value),rules:JSON.parse($("edit-rules").value),as_of:$("edit-asof").value||null,reason:$("edit-rule-reason").value});$("detail-dialog").close();return "Rule revision saved. Re-analyze and review the new snapshot.";
  }
  if(name==="save-test"){
    const t=w().tests.find(t=>t.test_id===$("edit-test-id").value);
    if(!t)throw Error("Test is no longer current. Refresh the workflow.");
    await command("edit-test",{test_id:t.test_id,test_revision:t.revision,title:$("edit-title").value,inputs:JSON.parse($("edit-inputs").value),expected:JSON.parse($("edit-expected").value),reason:$("edit-reason").value});$("detail-dialog").close();return "New test revision saved. A new review decision is required.";
  }
}
async function guarded(fn) {
  if(state.busy)return;
  state.busy=true;
  const buttons=[...document.querySelectorAll("button")],disabled=buttons.map(b=>b.disabled);
  buttons.forEach(b=>b.disabled=true);
  notice("Working…");
  try {const message=await fn();if(message)notice(message);else $("notice").hidden=true;}
  catch(error){notice(error.message,true);}
  finally{state.busy=false;buttons.forEach((b,i)=>{if(b.isConnected)b.disabled=disabled[i];});renderWorkflow();}
}
document.addEventListener("click",event=>{
  const button=event.target.closest("button");if(!button)return;
  if(button.dataset.page){page(button.dataset.page);return;}
  if(button.dataset.action==="close-dialog"){$("detail-dialog").close();return;}
  if(button.dataset.open){guarded(async()=>{await selectWorkflow(button.dataset.open);page("tests");});return;}
  if(button.dataset.inspectTest!==undefined){
    const t=w().tests[Number(button.dataset.inspectTest)];
    dialog("Inspect / edit test",details("Full provenance and rule references",t)+'<input id="edit-test-id" type="hidden" value="'+esc(t.test_id)+'"><label>Title<input id="edit-title" value="'+esc(t.title)+'"></label><label>Typed inputs JSON<textarea id="edit-inputs" rows="7">'+esc(pretty(t.inputs))+'</textarea></label><label>Expected action JSON<textarea id="edit-expected" rows="5">'+esc(pretty(t.expected))+'</textarea></label><label>Edit reason<input id="edit-reason"></label><button data-action="save-test" class="primary">Save test revision</button>');return;
  }
  if(button.dataset.action)guarded(()=>perform(button.dataset.action));
});
$("select-all").addEventListener("change",()=>document.querySelectorAll('[name="test-selection"]').forEach(x=>x.checked=$("select-all").checked));
$("workflow-select").addEventListener("change",()=>guarded(()=>selectWorkflow($("workflow-select").value)));
$("proposal-select").addEventListener("change",()=>guarded(()=>proposal($("proposal-select").value)));
$("batch-select").addEventListener("change",()=>guarded(()=>batch($("batch-select").value)));
$("actor").addEventListener("change",()=>{try{localStorage.setItem("rule2test.actor",$("actor").value);}catch{}});
try{$("actor").value=localStorage.getItem("rule2test.actor")||"";}catch{}
guarded(async()=>{
  const session=await api("/session");state.token=session.csrf_token;
  $("providers").textContent=Object.entries(session.providers).map(([k,v])=>k+": "+v).join(" · ");
  await refresh();return "Workspace ready. Enter a reviewer identity to start.";
});



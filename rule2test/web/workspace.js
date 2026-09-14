"use strict";
const SUITE_ACTIONS=new Set(['suite-inspect','suite-sample','suite-preview','suite-save','suite-open','suite-compare','rule-sample','read-rules','suite-edit-save','sut-suggest']);
const intake={file:null,info:null,rows:[],resolutions:[],examples:[],sutWorkflow:null};
async function suiteLists(proposals) {
  const suites=await api('/suites');
  for(const id of ['suite-saved','compare-suite'])options(id,suites,'suite_id',s=>s.title+' · '+s.ready+' ready / '+s.rows+' rows');
  options('compare-rules',proposals.filter(p=>p.review==='approved'),'proposal_id',p=>p.proposal_id.slice(0,8)+' · '+p.provider+' / '+p.model);
  if(!intake.examples.length){intake.examples=(await api('/rules/examples')).examples;options('rule-example',intake.examples,'key',x=>x.label);}
}
function mappingForm(){
  const sheet=intake.info.sheets.find(s=>s.name===$('suite-sheet').value);
  $('suite-header').value=sheet.header_row;
  $('suite-columns').innerHTML=['test_id','title','preconditions','steps','test_data','expected'].map(key=>'<label>'+esc(humanKey(key))+'<select data-map="'+key+'"><option value="">Not mapped</option>'+sheet.headers.map(h=>'<option value="'+esc(h.letter)+'"'+(sheet.suggested[key]===h.letter?' selected':'')+'>'+esc(h.letter+' · '+h.text)+'</option>').join('')+'</select></label>').join('');
  invalidatePreview();
}
function invalidatePreview(){intake.rows=[];intake.resolutions=[];$('suite-preview').textContent='Preview the selected mapping before saving.';}
function mappingBody(){
  if(!intake.file)throw Error('Inspect a file first.');
  const mapping=Object.fromEntries([...document.querySelectorAll('[data-map]')].filter(e=>e.value).map(e=>[e.dataset.map,e.value]));
  return {...intake.file,sheet:$('suite-sheet').value,header_row:Number($('suite-header').value),mapping};
}
function renderSuiteRows(){
  $('suite-preview').innerHTML=table(['Row / test','Original cells','Interpretation','Questions / decision'],intake.rows.map(r=>{
    const resolution=intake.resolutions.find(x=>x.row_number===r.row_number);
    return '<tr><td>'+esc(r.row_number+' · '+r.row_id)+'<small>'+esc(r.title)+'</small></td><td>'+r.cells.map(c=>'<p><b>'+esc(c.cell)+'</b> '+esc(c.text)+'</p>').join('')+'</td><td>'+esc(fmtInputs(r.inputs))+' → '+esc(fmtAction(r.expected))+'</td><td>'+badge(resolution?(resolution.skip?'skipped':'human confirmation'):r.status)+'<p>'+esc(r.questions.join(' '))+'</p>'+(resolution?details('Your saved correction',resolution):'')+'<button data-suite-edit="'+r.row_number+'">Edit</button><button data-suite-skip="'+r.row_number+'">Skip</button></td></tr>';
  }).join(''),'No rows previewed.');
}
function renderRuleProposal(p){
  if(!p){$('proposal-detail').textContent='Interpret rules or select a stored proposal.';return;}
  const c=p.compiled;
  $('proposal-detail').innerHTML='<p>'+badge(p.summary.status)+' '+esc(p.summary.provider==='pattern'?'Pattern reader · no AI inference':p.summary.simulated?'Simulated provider':'AI provider')+'</p>'
    +(c?'<div class="two-col"><div><h3>Current rule</h3>'+(c.baseline_known?c.old_rules.map(ruleCard).join('')+'<p>Otherwise: '+esc(fmtAction(c.old_default))+'</p>':'<p>Unknown baseline. Historical change cannot be established.</p>')+'</div><div><h3>New rule</h3>'+c.new_rules.map(ruleCard).join('')+'<p>Otherwise: '+esc(fmtAction(c.new_default))+'</p></div></div><h3>What changed</h3>'+(c.baseline_known?table(['Before','After'],c.delta.deltas.map(d=>'<tr><td>'+esc(fmtRule(d.before))+'</td><td>'+esc(fmtRule(d.after))+'</td></tr>').join(''),'No rule condition changed.')+'<p>Default: '+esc(fmtAction(c.old_default))+' → '+esc(fmtAction(c.new_default))+'</p>':'<p>Will check testcase conformity to the new rule only.</p>'):'<p>'+esc(p.summary.issues.join(' '))+'</p>')
    +details('Original rule text and citations',p.proposal.request.sources)+details('Raw output',p.output)+details('Review decision',p.review);
}
function renderChanges(){
  const p=state.current?.proposal;if(!p)return;
  if(!p.baseline_known)$('rule-detail').innerHTML='<p>Previous rule unknown. The internal comparison baseline is a copy used for execution; it is not historical evidence.</p><h3>New rule</h3>'+w().new_rules.map(ruleCard).join('');
  $('change-overview').innerHTML='<article class="card"><h3>'+(p.baseline_known?'Rule change analysis':'Conformity check · previous rule unknown')+'</h3><p>'+esc(p.changes.join('; ')||(p.baseline_known?'No semantic rule change.':'This comparison does not establish a historical change.'))+'</p></article>';
  $('not-linked').innerHTML='<article class="card"><h3>Not linked · '+p.excluded.length+'</h3>'+table(['Test','Reason','Original cells'],p.excluded.map(r=>'<tr><td>'+esc(r.row_id+' · '+r.title)+'</td><td>'+esc(r.reason)+'</td><td>'+details('Source cells',r.original)+'</td></tr>').join(''),'All imported rows were linked.')+'</article>';
  const wf=w();let body='';
  for(const [group,label] of p.groups){
    const rows=p.rows.filter(r=>r.group===group);if(!rows.length)continue;
    body+='<tr class="proposal-group"><th colspan="6">'+esc(label)+'</th></tr>';
    body+=rows.map(r=>{const index=wf.tests.findIndex(t=>t.test_id===r.test_id);return '<tr><td><input type="checkbox" name="test-selection" value="'+index+'" aria-label="Select '+esc(r.title)+'"></td><td>'+badge(r.kind)+' '+esc(r.test_id)+'<small>'+esc(r.title)+'</small></td><td>'+esc(r.inputs_text)+'</td><td><b>'+esc((r.before_text||'New test')+' → '+r.after_text)+'</b><p>'+esc(r.reason)+'</p>'+(r.rule.quote?'<p class="quote">'+esc(r.rule.quote)+'</p>':'')+(r.source?'<small>'+esc(r.source.sheet+'!'+r.source.cell+' · '+r.source.quote)+'</small>':'')+'</td><td>'+badge(r.review)+'</td><td><button data-inspect-test="'+index+'">Inspect / edit</button></td></tr>';}).join('');
  }
  $('test-rows').innerHTML=body;
}
function applySuggestedSut(force){
  const current=state.current;if(!current)return;
  const s=current.sut_suggestion;
  if(!s)return;
  $('sut-note').textContent=s.note;
  if(!force&&intake.sutWorkflow===current.workflow.workflow_id)return;
  for(const [key,id] of Object.entries({profile:'sut-profile',fault:'sut-fault',min_age:'sut-min',max_age:'sut-max',claim_threshold:'sut-threshold',deductible:'sut-deductible',currency:'sut-currency'}))$(id).value=s[key];
  intake.sutWorkflow=current.workflow.workflow_id;
}
async function suiteAction(name){
  if(name==='sut-suggest'){applySuggestedSut(true);return 'Suggested mock settings applied. Verify before execution.';}
  if(name==='suite-inspect'||name==='suite-sample'){
    if(name==='suite-sample')intake.file=await api('/suites/samples/'+$('suite-example').value);
    else {
      const file=$('suite-file').files[0];if(!file)throw Error('Choose an XLSX or CSV file.');
      if(file.size>10*1024*1024)throw Error('File exceeds 10 MiB.');
      let binary='';const bytes=new Uint8Array(await file.arrayBuffer());
      for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
      intake.file={filename:file.name,content_base64:btoa(binary)};
    }
    intake.file={filename:intake.file.filename,content_base64:intake.file.content_base64};
    intake.info=await api('/suites/inspect',intake.file);
    $('suite-sheet').innerHTML=intake.info.sheets.map(s=>'<option>'+esc(s.name)+'</option>').join('');
    $('suite-mapping').hidden=false;mappingForm();return 'File inspected. Confirm the sheet, header row and column mapping.';
  }
  if(name==='suite-preview'){
    const p=await api('/suites/preview',mappingBody());intake.rows=p.rows;intake.resolutions=[];renderSuiteRows();return 'Preview ready. Inspect ambiguous rows before saving.';
  }
  if(name==='suite-save'){
    if(!intake.rows.length)throw Error('Preview this mapping first.');
    const unresolved=intake.rows.filter(r=>r.status==='needs_confirmation'&&!intake.resolutions.some(x=>x.row_number===r.row_number));
    if(unresolved.length)throw Error('Edit or explicitly skip '+unresolved.length+' unclear row(s) before saving.');
    const result=await api('/suites',{...mappingBody(),resolutions:intake.resolutions,actor:actor()});
    await lists();$('suite-saved').value=result.suite.suite_id;$('compare-suite').value=result.suite.suite_id;
    return 'Test suite saved. Continue to Rules.';
  }
  if(name==='suite-open'){
    const id=$('suite-saved').value;if(!id)throw Error('Select a saved suite.');
    const result=await api('/suites/'+encodeURIComponent(id));$('compare-suite').value=id;
    $('suite-saved-detail').innerHTML='<p>'+esc(result.summary.rows+' rows · '+result.summary.ready+' ready · '+result.summary.skipped+' skipped')+'</p>'+details('Archived interpretation and source cells',result.suite)+'<a href="/api/v1/suites/'+encodeURIComponent(id)+'/source" download>Download original test-case file</a>';return 'Saved suite loaded.';
  }
  if(name==='rule-sample'){
    const example=intake.examples.find(x=>x.key===$('rule-example').value);if(!example)throw Error('Choose an example.');
    $('source-v1').value=example.current;$('source-v2').value=example.new;$('rule-engine').value=example.engine;return 'Example loaded. You can edit both rules freely.';
  }
  if(name==='read-rules'){
    const sources=[['v1',$('source-v1').value],['v2',$('source-v2').value]].filter(([label,text])=>label==='v2'||text.trim()).map(([label,text])=>({label,text,document_id:label+'.txt'}));
    const result=await api('/extract',{sources,engine:$('rule-engine').value,actor:actor()});
    await lists();$('proposal-select').value=result.proposal_id;await proposal(result.proposal_id);return 'Rule proposal: '+result.status+'. Inspect the interpretation and defaults before confirming.';
  }
  if(name==='suite-compare'){
    const sid=$('compare-suite').value,pid=$('compare-rules').value;if(!sid||!pid)throw Error('Choose a saved suite and confirmed rules.');
    const p=await api('/proposals/'+encodeURIComponent(pid));
    const result=await api('/suites/'+encodeURIComponent(sid)+'/link',{proposal_id:pid,proposal_hash:p.summary.proposal_hash,actor:actor()});
    await refresh(result.workflow.workflow_id);return 'Comparison ready. Inspect before/after, reasons and unlinked rows, then review each test.';
  }
  if(name==='suite-edit-save'){
    const row=Number($('suite-edit-row').value),fields=['age','claim_amount'];
    const inputs=fields.filter(f=>$('resolve-'+f).value.trim()).map(field=>({field,value:$('resolve-'+field).value,currency:$('resolve-currency').value}));
    if(!inputs.length)throw Error('Supply at least one input. Use empty or missing for exception cases.');
    const resolution={row_number:row,inputs,expected:{outcome:$('resolve-outcome').value,amount:$('resolve-amount').value,currency:$('resolve-currency').value}};
    intake.resolutions=intake.resolutions.filter(x=>x.row_number!==row).concat(resolution);renderSuiteRows();$('detail-dialog').close();return 'Correction staged. Save the suite to validate and archive it.';
  }
}
const $ = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pretty = value => JSON.stringify(value, null, 2);
const code = value => "<pre>" + esc(pretty(value)) + "</pre>";
const badge = value => '<span class="badge ' + esc(value) + '">' + esc(value) + "</span>";
const details = (title, value) => "<details><summary>" + esc(title) + "</summary>" + code(value) + "</details>";

// ---- Human-readable rendering ------------------------------------------------------------
// The API returns typed domain contracts. Showing them raw makes a reviewer read JSON to do
// their job. Everything below turns a contract into a sentence; the raw object stays available
// under a "Raw JSON" disclosure because it is the audit artefact.
const FIELD_NAMES={age:"Age",claim_amount:"Claim amount"};
const OPERATORS={eq:"=",ne:"≠",lt:"<",le:"≤",gt:">",ge:"≥",is_null:"is empty",is_missing:"is missing"};
const OUTCOMES={allow:"ALLOW",deny:"DENY",review:"REVIEW",invalid:"INVALID",payout:"PAYOUT"};
const CHANGES={added:"Added",removed:"Removed",modified:"Changed"};
const fieldName = field => FIELD_NAMES[field] || String(field);
const grouped = text => {
  const [whole, fraction] = String(text).split(".");
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (fraction ? "." + fraction : "");
};
function fmtValue(value) {
  if(!value || value.kind === undefined) return "—";
  switch(value.kind) {
    case "integer": return String(value.data);
    case "money": return grouped(value.data?.$decimal ?? value.data) + (value.currency ? " " + value.currency : "");
    case "date": return String(value.data?.$date ?? value.data);
    case "boolean": return value.data ? "yes" : "no";
    case "text": return String(value.data);
    case "null": return "empty";
    case "missing": return "missing";
    default: return String(value.data ?? value.kind);
  }
}
function fmtInputs(inputs) {
  if(!inputs || !inputs.length) return "—";
  return inputs.map(input => fieldName(input.field) + " = " + fmtValue(input.value)).join(", ");
}
function fmtAction(action) {
  if(!action) return "—";
  const outcome = OUTCOMES[action.outcome] || String(action.outcome).toUpperCase();
  if(action.formula) return outcome + " = " + fieldName(action.formula.field) + " − " + fmtValue(action.formula.deductible) + ", minimum 0";
  if(action.amount) return outcome + " " + fmtValue(action.amount);
  return outcome;
}
function fmtCondition(condition) {
  const operator = OPERATORS[condition.operator] || condition.operator;
  if(operator === "is empty" || operator === "is missing") return fieldName(condition.field) + " " + operator;
  return fieldName(condition.field) + " " + operator + " " + fmtValue(condition.value);
}
function fmtRule(rule) {
  if(!rule) return "—";
  const when = (rule.conditions || []).map(fmtCondition).join(" and ") || "any input";
  return "If " + when + " → " + fmtAction(rule.action);
}
const humanKey = key => String(key).replace(/_/g," ").replace(/^./,c=>c.toUpperCase());
function fmtObserved(value) {
  if(value === null || value === undefined) return "—";
  if(Array.isArray(value)) return value.length ? value.join(", ") : "none";
  if(typeof value !== "object") return String(value);
  return Object.entries(value).map(([key, item]) =>
    key.replace(/_/g, " ") + ": " + (item === null ? "—" : typeof item === "object" ? JSON.stringify(item) : item)).join(" · ");
}
function ruleCard(rule) {
  const quote = (rule.sources || []).map(source => source.quote).find(Boolean);
  return '<article class="plain"><h4>' + esc(rule.title) + ' <small>' + esc(rule.rule_id) + " · v" + rule.version + '</small></h4>'
    + '<p class="rule-line">' + esc(fmtRule(rule)) + "</p>"
    + (quote ? '<p class="quote">“' + esc(quote) + '”</p>' : "")
    + details("Raw JSON", rule) + "</article>";
}
function table(headers, rows, empty) {
  if(!rows) return '<p class="hint">' + esc(empty) + "</p>";
  return '<div class="table-scroll"><table><thead><tr>' + headers.map(h => "<th>" + esc(h) + "</th>").join("")
    + "</tr></thead><tbody>" + rows + "</tbody></table></div>";
}
function fmtAnalysis(analysis) {
  const deltas = (analysis.delta?.deltas || []).map(delta =>
    "<tr><td>" + esc(CHANGES[delta.kind] || delta.kind) + "</td><td>" + esc((delta.after || delta.before || {}).title || "")
    + "</td><td>" + esc(fmtRule(delta.before)) + "</td><td>" + esc(fmtRule(delta.after)) + "</td></tr>").join("");
  const impacted = (analysis.impact || []).filter(row => row.status !== "unchanged");
  const impact = impacted.map(row =>
    "<tr><td>" + esc(row.test_id) + "</td><td>" + badge(row.status) + "</td><td>" + esc(fmtAction(row.old_expected))
    + "</td><td>" + esc(fmtAction(row.new_expected)) + "</td></tr>").join("");
  const missing = new Set(analysis.gaps?.missing_ids || []);
  const gaps = (analysis.gaps?.obligations || []).filter(o => missing.has(o.obligation_id)).map(o =>
    "<tr><td>" + esc(o.category) + "</td><td>" + esc(o.label) + "</td><td>" + esc(fmtInputs(o.inputs)) + "</td></tr>").join("");
  const unresolved = (analysis.gaps?.unresolved_ids || []).length;
  return "<h3>What changed in the rules</h3>"
    + table(["Change", "Rule", "Before", "After"], deltas, "No rule changed.")
    + "<h3>Existing tests this affects</h3>"
    + table(["Test", "Status", "Expected before", "Expected now"], impact,
        "No existing test changes its expected result.")
    + "<h3>Cases nobody covers yet</h3>"
    + table(["Category", "Obligation", "Input that would cover it"], gaps, "Every obligation is already covered.")
    + (unresolved ? '<p class="hint">' + unresolved + " obligation(s) could not be resolved by the bounded search; the gate treats them as unresolved.</p>" : "")
    + details("Raw JSON", analysis);
}
// ---- Guided flow -------------------------------------------------------------------------
const STEPS = ["1 Test cases", "2 Rules", "3 Compare & review", "4 Execution", "5 Evidence & gate"];
const STEP_AT = {draft:0, analyzed:1, in_review:2, approved:3, executing:3, interrupted:3, executed:4, evidenced:4};
const NEXT_STEP = {
  draft: {action:"analyze-review", label:"Analyze & open review"},
  analyzed: {action:"start-review", label:"Continue to test review"},
  in_review: {hint:"Your turn: tick the tests you accept, write a reason, press Approve selected, then Finalize review."},
  approved: {action:"execute", label:"Run the approved tests"},
  executing: {hint:"A run is in progress. If it stopped, use Recover interrupted run."},
  interrupted: {hint:"The run was interrupted. Use Recover interrupted run, then review again."},
  executed: {action:"evidence-gate", label:"Create evidence & evaluate"},
  evidenced: {hint:"Finished. Download the evidence pack, or reopen review to run again."},
};
function renderFlow() {
  const workflow = state.current && state.current.workflow;
  if(!workflow) {
    const at=state.page==='intake'?0:state.page==='extraction'?1:2;
    $("flow").innerHTML='<div class="steps">'+STEPS.map((label,index)=>'<span class="step'+(index===at?' now':'')+'">'+esc(label)+'</span>').join('')+'</div>';
    return;
  }
  const at = STEP_AT[workflow.status] ?? 0;
  const strip = STEPS.map((label, index) =>
    '<span class="step' + (index < at ? " done" : index === at ? " now" : "") + '">' + esc(label) + "</span>").join("");
  const next = NEXT_STEP[workflow.status] || {};
  const button = next.action ? '<button data-action="' + next.action + '" class="primary">' + esc(next.label) + "</button>" : "";
  const hint = next.hint ? '<span class="flow-hint">' + esc(next.hint) + "</span>" : "";
  $("flow").innerHTML = '<div class="steps">' + strip + "</div>" + button + hint;
}

const state = {token:"", workflows:[], current:null, proposal:null, batch:null, busy:false, page:"overview"};
const titles = {overview:"Overview",intake:"Test cases",extraction:"Rules",tests:"Compare & review",knowledge:"Knowledge & reuse",evidence:"Run & evidence"};
function notice(message, error=false) { $("notice").hidden=false; $("notice").className=error?"error":""; $("notice").textContent=message; }
function actor() { const value=$("actor").value.trim(); if(!value) throw Error("Enter your reviewer identity in the header first."); return value; }
async function api(path, body) {
  const response=await fetch("/api/v1"+path, body===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":state.token},body:JSON.stringify(body)});
  const trace=response.headers.get("X-Trace-Id")||"";
  let data;
  try { data=await response.json(); }
  catch { throw Error("The server returned a non-JSON response (HTTP "+response.status+"). Inspect the server console."+(trace?" Trace "+trace+".":"")); }
  if(!response.ok) throw Error((response.status===409?"Revision or state conflict. Refresh and inspect before retrying.\n":"")+(data.error||response.statusText)
    +(data.kind?"\nProvider failure: "+data.kind+(data.remediation?" \u2014 "+data.remediation:"")+"\nNo retry and no fallback to mock were attempted.":"")
    +(data.issues?"\n"+pretty(data.issues):"")
    +((data.trace_id||trace)?"\nTrace "+(data.trace_id||trace):""));
  return data;
}
function page(name) {
  if(!titles[name])return;
  state.page=name;
  for(const key of Object.keys(titles)) $("page-"+key).hidden=key!==name;
  document.querySelectorAll("nav [data-page]").forEach(b=>b.classList.toggle("active",b.dataset.page===name));
  $("page-title").textContent=titles[name];
  renderFlow();
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
  await suiteLists(proposals);
  options("workflow-select",workflows,"workflow_id",w=>w.title+" · r"+w.revision+" · "+w.status+" · "+w.workflow_id.slice(0,8));
  options("proposal-select",proposals,"proposal_id",p=>p.proposal_id.slice(0,8)+" · "+p.status+(p.simulated?" · simulated":""));
  options("index-select",indexes,"index_id",i=>i.index_id.slice(0,8)+" · "+i.records+" records"+(i.simulated?" · simulated":""));
  options("batch-select",batches,"batch_id",b=>b.batch_id.slice(0,8)+" · "+b.candidates+" candidates"+(b.simulated?" · simulated":""));
  $("overview-metrics").innerHTML=metric("Workflows",workflows.length,"Latest 100 workflows")+metric("Awaiting review",workflows.filter(w=>w.status==="in_review").length,"Explicit decisions required")+metric("Evidence ready",workflows.filter(w=>w.status==="evidenced").length,"Immutable execution packs")+metric("Knowledge indexes",indexes.length,"Reviewed source snapshots");
  $("workflow-list").innerHTML=workflows.length?'<div class="table-scroll"><table><thead><tr><th>Workflow</th><th>Status</th><th>Tests</th><th>Revision</th><th></th></tr></thead><tbody>'+workflows.map(w=>'<tr><td>'+esc(w.title)+'<small>'+esc(w.workflow_id)+'</small></td><td>'+badge(w.status)+'</td><td>'+w.tests+'</td><td>r'+w.revision+'</td><td><button data-open="'+esc(w.workflow_id)+'">Open workflow</button></td></tr>').join("")+"</tbody></table></div>":'<div class="empty">Your evidence story starts here. Import a test-case file and enter your business rules.</div>';
  $("knowledge-sources").innerHTML=workflows.filter(w=>w.approved>0).map(w=>'<label class="check"><input type="checkbox" name="knowledge-source" value="'+esc(w.workflow_id)+'">'+esc(w.title)+" · "+esc(w.workflow_id.slice(0,8))+"</label>").join("")||'<p class="hint">Approve source tests in a workflow before building an index.</p>';
}
function w() {if(!state.current)throw Error("Select a workflow first.");return state.current.workflow;}
function renderWorkflow() {
  const current=state.current;
  if(!current){
    $("context-state").textContent="No workflow selected";
    $("test-summary").innerHTML='<div class="card empty">Select or create a workflow to begin.</div>';
    $("rule-detail").innerHTML="";$("test-rows").innerHTML="";$("downloads").innerHTML="";
    $('change-overview').innerHTML='';$('not-linked').innerHTML='';
    $("test-count").textContent="0 tests";$("select-all").checked=false;
    renderFlow();
    return;
  }
  const wf=current.workflow;
  $("workflow-select").value=wf.workflow_id;
  $("context-state").textContent=wf.status+" · revision "+wf.revision;
  $("test-summary").innerHTML='<div class="section-heading"><h2>'+esc(current.summary.title)+'</h2>'+badge(wf.status)+"</div>"+coverage(current.coverage);
  $("rule-detail").innerHTML='<div class="rule-columns"><div><h3>PREVIOUS RULE VERSION</h3>'+wf.old_rules.map(ruleCard).join("")+'</div><div><h3>CURRENT RULE VERSION</h3>'+wf.new_rules.map(ruleCard).join("")+"</div></div>"+(wf.analysis?fmtAnalysis(wf.analysis):'<p class="hint">Analyze the rule change to identify affected tests, missing obligations and boundary candidates.</p>');
  const decisions=Object.fromEntries(wf.approvals.map(a=>[a.subject_id,a.decision]));
  $("test-count").textContent=wf.tests.length+" tests · "+current.summary.pending+" pending";
  $("test-rows").innerHTML=wf.tests.map((t,i)=>'<tr><td><input type="checkbox" name="test-selection" value="'+i+'" aria-label="Select '+esc(t.title)+'"></td><td>'+esc(t.title)+'<small>'+esc(t.test_id)+" · r"+t.revision+" · "+esc(t.kind)+'</small></td><td>'+esc(fmtInputs(t.inputs))+'</td><td>'+esc(fmtAction(t.expected))+'</td><td>'+badge(decisions[t.test_id]||"pending")+'</td><td><button data-inspect-test="'+i+'">Inspect / edit</button></td></tr>').join("")||'<tr><td colspan="6">No generated tests yet.</td></tr>';
  $("select-all").checked=false;
  $("downloads").innerHTML=(wf.evidence_id?'<a class="source-link" href="/api/v1/workflows/'+encodeURIComponent(wf.workflow_id)+'/evidence/'+encodeURIComponent(wf.evidence_id)+'" download>Download verified evidence JSON ↗</a>':'<p class="hint">Create an evidence pack after execution.</p>')+(wf.documents||[]).map(d=>'<a class="source-link" href="/api/v1/workflows/'+encodeURIComponent(wf.workflow_id)+'/sources/'+encodeURIComponent(d.document_hash)+'" download>'+esc(d.document_id)+'<small> · SHA-256 '+esc(d.document_hash)+'</small></a>').join("");
  const enabled={analyze:["draft"],"start-review":["analyzed"],finalize:["in_review"],execute:["approved"],evidence:["executed"],"reopen-review":["approved","executed","evidenced"],recover:["executing","interrupted"],"approve-tests":["in_review","approved"],"reject-tests":["in_review","approved"],"request-changes":["in_review","approved"]};
  for(const [a,statuses]of Object.entries(enabled))document.querySelectorAll('[data-action="'+a+'"]').forEach(b=>b.disabled=!statuses.includes(wf.status));
  renderChanges();
  renderFlow();
}
async function selectWorkflow(id) {
  $("gate-detail").innerHTML='<p class="hint">Evaluate the current revision to inspect quality checks.</p>';
  state.current=id?await api("/workflows/"+encodeURIComponent(id)):null;
  renderWorkflow();
  applySuggestedSut(false);
  $("run-detail").innerHTML='<p class="empty">No execution run in this workflow.</p>';
  if(state.current?.workflow.last_run_id){
    const wf=w(),run=await api("/workflows/"+encodeURIComponent(wf.workflow_id)+"/runs/"+encodeURIComponent(wf.last_run_id));
    $("run-detail").innerHTML='<h3>Run '+esc(run.run_id.slice(0,8))+" · "+esc(run.status)+'</h3><p>Executed from workflow revision '+run.workflow_revision+'. Coverage below uses this archived revision, including exercised failing tests.</p>'+coverage(run.coverage)+'<div class="table-scroll"><table><thead><tr><th>Test</th><th>Result</th><th>Expected</th><th>Actual</th></tr></thead><tbody>'+run.executions.map(e=>'<tr><td>'+esc(e.test_id)+'</td><td>'+badge(e.status)+'</td><td>'+esc(fmtAction(e.expected))+'</td><td>'+esc(e.error||fmtAction(e.actual))+'</td></tr>').join("")+"</tbody></table></div>"+details("Full execution journal",run);
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
  renderRuleProposal(p);

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
  if(SUITE_ACTIONS.has(name)) return suiteAction(name);
  if(name==="quality-gate"){
    const id=w().workflow_id;
    const report=await api("/workflows/"+encodeURIComponent(id)+"/quality-gate");
    if(report.workflow_revision!==w().revision)throw Error("Workflow changed. Refresh before evaluating the gate again.");
    $("gate-detail").innerHTML='<div class="status-line">'+badge(report.verdict==="GO"?"pass":"fail")+'<strong>'+esc(report.verdict)+'</strong><span>'+esc(report.policy_version)+' · revision '+report.workflow_revision+'</span></div><p>'+esc(report.reason)+'</p><div class="table-scroll"><table><thead><tr><th>Check</th><th>Status</th><th>Observed</th><th>Requirement</th></tr></thead><tbody>'+report.checks.map(c=>'<tr><td>'+esc(humanKey(c.key))+'</td><td>'+badge(c.status.toLowerCase())+'</td><td>'+esc(fmtObserved(c.actual))+'</td><td>'+esc(c.requirement)+'</td></tr>').join("")+'</tbody></table></div>'+details("Unmeasured metrics",report.unmeasured)+details("Snapshot hashes and full report",report)+'<button data-action="download-gate">Download this gate report</button>';
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
  if(name==="diagnostics"){
    const d=await api("/diagnostics");
    const table=(body,cells)=>'<div class="table-scroll"><table><thead><tr>'+cells.map(c=>"<th>"+esc(c)+"</th>").join("")+"</tr></thead><tbody>"+body+"</tbody></table></div>";
    const labels=o=>Object.entries(o||{}).map(([k,v])=>k+"="+v).join(" ")||"\u2014";
    const counters=d.metrics.counters.map(c=>"<tr><td>"+esc(c.name)+"</td><td>"+esc(labels(c.labels))+"</td><td>"+c.value+"</td></tr>").join("")||'<tr><td colspan="3">No counters recorded yet.</td></tr>';
    const durations=d.metrics.durations.map(x=>"<tr><td>"+esc(x.name)+"</td><td>"+esc(labels(x.labels))+"</td><td>"+x.count+"</td><td>"+x.mean_ms.toFixed(1)+" ms</td><td>"+x.max_ms.toFixed(1)+" ms</td><td>"+(x.p95_ms_upper_bound===null?"&gt; 30000":"\u2264 "+x.p95_ms_upper_bound)+" ms</td></tr>").join("")||'<tr><td colspan="6">No timings recorded yet.</td></tr>';
    const deps=Object.entries(d.optional_dependencies).map(([k,v])=>k+": "+(v.installed?"installed":"absent")+" ("+v.extra+")").join(" \u00b7 ");
    $("diagnostics-detail").innerHTML='<div class="metrics">'
      +metric("Logging",d.logging.level,"to "+d.logging.destination+" \u00b7 "+d.logging.allowlisted_fields+" allowlisted fields")
      +metric("Metric series",d.metrics.series+" / "+d.metrics.max_series,d.metrics.dropped_series+" dropped by the cardinality cap")
      +metric("Database",d.database.migrations.join(", "),d.database.path+" \u00b7 "+d.database.workflows+" workflows \u00b7 "+(d.database.writable?"writable":"read-only"))
      +metric("Runtime","Python "+d.configuration.runtime.python,"SQLite "+d.configuration.runtime.sqlite+" \u00b7 "+d.configuration.runtime.platform)
      +'</div><p class="hint">'+esc(deps)+'</p>'
      +"<h3>Counters</h3>"+table(counters,["Counter","Labels","Value"])
      +"<h3>Durations</h3>"+table(durations,["Operation","Labels","Count","Mean","Max","p95 bucket"])
      +details("Effective configuration (secrets shown as set/unset only)",d.configuration)
      +'<p class="hint">'+esc(d.limitation)+"</p>";
    return "Diagnostics loaded. Durations are host wall-clock times, not a quality measurement.";
  }
  if(name==="ai-status"){
    const status=await api("/ai-status");
    dialog("AI configuration & local model inventory",'<p>No inference or downloads were triggered. Use ai_doctor.py --probe for an explicit capability check.</p>'+code(status));
    return "AI configuration inspected. Model quality requires a separate evaluation.";
  }
  if(name==="analyze-review"){
    await command("analyze");await command("start-review");page("tests");
    return "Analysis complete and review opened. Tick the tests you accept, then approve them.";
  }
  if(name==="evidence-gate"){
    const evidence=await command("evidence");
    return "Evidence archived (SHA-256 "+evidence.evidence_hash.slice(0,12)+"\u2026). "+await perform("quality-gate");
  }
  if(name==="refresh"){await refresh();return "Workspace refreshed.";}
  if(name==="import"){
    const file=$("import-file").files[0];if(!file)throw Error("Select a JSON or XLSX file.");
    if(file.size>10*1024*1024)throw Error("Source file exceeds 10 MiB.");
    const bytes=new Uint8Array(await file.arrayBuffer());let binary="";
    for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
    const body={filename:file.name,content_base64:btoa(binary),actor:actor()};
    if($("import-mapping").value.trim())body.mapping=JSON.parse($("import-mapping").value);
    const result=await api("/import",body);await refresh(result.workflow_id);page("tests");return "Source validated and archived. Draft created.";
  }
  if(name==="approve-proposal"||name==="reject-proposal"||name==="promote"){
    const p=state.proposal?.summary;if(!p)throw Error("Select a proposal.");
    const body={proposal_hash:p.proposal_hash,actor:actor()};
    if(name!=="promote"){body.decision=name==="approve-proposal"?"approved":"rejected";body.reason=$("proposal-reason").value;}
    const result=await api("/proposals/"+encodeURIComponent(p.proposal_id)+"/"+(name==="promote"?"promote":"review"),body);
    if(name==="promote"){await refresh(result.workflow_id);page("tests");}else {await lists();await proposal(p.proposal_id);}
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
  const buttons=[...document.querySelectorAll('button,select,input[type="checkbox"],input[type="file"]')],disabled=buttons.map(b=>b.disabled);
  buttons.forEach(b=>b.disabled=true);
  notice("Working…");
  try {const message=await fn();if(message)notice(message);else $("notice").hidden=true;}
  catch(error){notice(error.message,true);}
  finally{state.busy=false;buttons.forEach((b,i)=>{if(b.isConnected)b.disabled=disabled[i];});renderWorkflow();}
}
document.addEventListener("click",event=>{
  const button=event.target.closest("button");if(!button)return;
  if(button.dataset.suiteSkip){const row=Number(button.dataset.suiteSkip);intake.resolutions=intake.resolutions.filter(x=>x.row_number!==row).concat({row_number:row,skip:true});renderSuiteRows();return;}
  if(button.dataset.suiteEdit){
    const row=Number(button.dataset.suiteEdit);
    dialog('Confirm test-case interpretation','<input id="suite-edit-row" type="hidden" value="'+row+'"><p>Enter age and/or claim amount. Use empty, missing or quoted text for exception inputs.</p><label>Age<input id="resolve-age"></label><label>Claim amount<input id="resolve-claim_amount"></label><label>Currency<input id="resolve-currency" value="VND"></label><label>Expected outcome<select id="resolve-outcome">'+['allow','deny','review','invalid','payout'].map(x=>'<option>'+x+'</option>').join('')+'</select></label><label>Payout amount (if applicable)<input id="resolve-amount"></label><button data-action="suite-edit-save">Stage correction</button>');return;
  }
  if(button.dataset.page){page(button.dataset.page);return;}
  if(button.dataset.action==="close-dialog"){$("detail-dialog").close();return;}
  if(button.dataset.open){guarded(async()=>{await selectWorkflow(button.dataset.open);page("tests");});return;}
  if(button.dataset.inspectTest!==undefined){
    const t=w().tests[Number(button.dataset.inspectTest)];
    dialog("Inspect / edit test",'<p class="rule-line">'+esc(fmtInputs(t.inputs))+" → "+esc(fmtAction(t.expected))+'</p><p class="hint">'+esc(t.rationale||"")+'</p>'+details("Full provenance and rule references",t)+'<input id="edit-test-id" type="hidden" value="'+esc(t.test_id)+'"><label>Title<input id="edit-title" value="'+esc(t.title)+'"></label><label>Typed inputs JSON<textarea id="edit-inputs" rows="7">'+esc(pretty(t.inputs))+'</textarea></label><label>Expected action JSON<textarea id="edit-expected" rows="5">'+esc(pretty(t.expected))+'</textarea></label><label>Edit reason<input id="edit-reason"></label><button data-action="save-test" class="primary">Save test revision</button>');return;
  }
  if(button.dataset.action)guarded(()=>perform(button.dataset.action));
});
$("select-all").addEventListener("change",()=>document.querySelectorAll('[name="test-selection"]').forEach(x=>x.checked=$("select-all").checked));
$('suite-sheet').addEventListener('change',mappingForm);
$('suite-header').addEventListener('change',invalidatePreview);
$('suite-columns').addEventListener('change',invalidatePreview);
$('suite-file').addEventListener('change',()=>{intake.file=null;invalidatePreview();$('suite-mapping').hidden=true;});
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



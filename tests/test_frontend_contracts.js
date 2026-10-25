/* Run with: node tests/test_frontend_contracts.js. No browser or package install. */
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const element = { addEventListener() {}, setAttribute() {}, removeAttribute() {}, classList: { add() {}, remove() {}, toggle() {} } };
const context = {
  console, assert, setTimeout, clearTimeout,
  localStorage: { getItem() { return null; }, setItem() {} },
  sessionStorage: { getItem() { return null; }, setItem() {} },
  document: { addEventListener() {}, querySelector() { return element; }, querySelectorAll() { return []; }, documentElement: { style: { setProperty() {} } }, body: { classList: element.classList } },
  location: { hash: "#/new" }, addEventListener() {},
};
vm.createContext(context);
const source = fs.readFileSync("static/app.js", "utf8").split("/* ---------- sky:")[0];
vm.runInContext(source, context);
(async () => {
  await vm.runInContext(`(async () => {
    const calls = [];
    S = { me: { roles: ['manager'], department_ids: ['support'] }, agents: [], capabilities: [{ id: 'write-document', name: 'Documents' }], 'dev/users': [{id:'pavan',name:'Pavan',roles:['manager'],department_ids:['support']}], steps: {}, conversations: {}, runs: [], approvals: [] };
    forge = {...forge0(), caps: ['write-document'], mode: 'demo', name: 'Brief Writer'};
    api = async (...args) => { calls.push(args); return { status: 'created', agent: { id: 'new-agent' } }; };
    await createAgent();
    assert.equal(calls.length, 1);
    assert.equal(calls[0][0], 'agents/quick-create');
    assert.equal(calls[0][2].name, 'Brief Writer');
    assert.equal(location.hash, '#/agent/new-agent');
    S.agents = [{id:'target',name:'Target',spec_version:4}];
    forge = {...forge0(), target:'target', caps:['write-document']};
    api = async (...args) => { calls.push(args); return {id:'target',name:'Target'}; };
    await createAgent();
    assert.equal(calls.at(-1)[0], 'agents/target/capabilities');
    assert.equal(calls.at(-1)[2].expected_spec_version, 4);
    S.me.roles = ['builder'];
    forge = {...forge0(),caps:['write-document'],mode:'demo',name:'Brief Writer'};
    api = async () => ({status:'awaiting_confirmation',proposal:{spec:{name:'Draft',manager_id:'pavan'}}});
    assert.match(await createAgent(), /waiting for Pavan/);
    assert.equal(location.hash, '#/inbox');
    S.agents = [{id:'a',name:'A'}, {id:'b',name:'B'}];
    applyActivity({agent:{id:'a',name:'A',status:'active'},runs:[{id:'r',agent_id:'a',status:'completed',mode:'meta',updated_at:'now'}],steps:[],approvals:[],conversations:[{id:'old',last_run_id:'r'},{id:'new',last_run_id:null}]});
    assert.equal(S.agents[0].id, 'a');
    assert.equal(followTarget({id:'a'},S.runs), null);
    assert.equal(activeConversation('a').id, 'new');
    assert.equal(narrate({status:'completed',result:{answer:'Backend reply'}},[]), '');
    assert.match(narrate({status:'completed',result:{summary:'Saved summary'}},[]), /Saved summary/);
    // A failed task explains itself, says the agent is fine, and offers a retry.
    const failed = narrate({id:'r9',status:'failed',error:'Used every call.',error_code:'step_limit'},[]);
    assert.match(failed, /Used every call/);
    assert.match(failed, /data-act="retry-run" data-id="r9"/);
    assert.match(failed, /agent is fine/);
    assert.match(failed, /narrower/);
    assert.match(narrate({id:'r8',status:'failed',error:'x',error_code:'mystery'},[]), /Something went wrong with this task/);
    // Errors keep their codes; internal errors show a support id.
    const typed = new ApiError('Nope', {status: 409, code: 'step_limit', requestId: 'abcdef123456'});
    assert.equal(typed.code, 'step_limit');
    assert.equal(errText(typed), 'Nope');
    assert.equal(errText(new ApiError('Boom', {code: 'internal_error', requestId: 'abcdef123456'})), 'Boom (support ID abcdef12)');
    S = {...S, me: {roles:['admin'],department_ids:['support']}, departments:[{id:'support',name:'Support'}], marketplace:[], leaderboard:{capability_usage:[]}, capabilities:[], 'integrations/github':{configured:true,connected:true,department_ids:['support']}};
    const library = libraryScreen();
    assert.ok(library.includes('<summary>Add a tool</summary>'));
    assert.match(library, /GitHub · connected/);
    assert.doesNotMatch(library, /github-connect|connect-github|Test connection & add/);
    assert.ok(library.indexOf('add-library-tool') > library.indexOf('</ul>'));
    S.me.roles = ['builder'];
    assert.match(libraryScreen(), /data-form="new-cap"/);
    assert.match(libraryScreen(), /Sign in with a manager or admin account/);
    assert.ok(libraryScreen().includes('disabled>Add tool</button>'));
    S.me.roles = ['manager'];
    assert.ok(!libraryScreen().includes('disabled>Add tool</button>'));
    assert.doesNotMatch(libraryScreen(), /Sign in with a manager or admin account/);
    S.capabilities = [{id:'github-reading',name:'GitHub',tools:['github_read_file']}];
    assert.equal(usesGitHub({bindings:[{capability_id:'github-reading'}]}), true);
    S.capabilities.push({id:'make-slideshow',name:'Slides',tools:['create_slideshow']});
    S['model-profiles'] = [{id:'meta',name:'Live model',enabled:true}];
    S.policy = {approval_scope:'agent'};
    forge = {...forge0(),mode:'meta',caps:['github-reading','make-slideshow']};
    assert.match(forgeScreen(), /data-id="github-reading"/);
    assert.match(forgeScreen(), /data-id="make-slideshow"/);
    S.agents = [{id:'github-agent',name:'Repo analyst',status:'active',model_profile_id:'meta',manager_id:'pavan',bindings:[{capability_id:'github-reading'},{capability_id:'make-slideshow'}]}];
    S.runs = []; S.conversations = {};
    assert.match(chatScreen('github-agent'), /name="repository"/);
    // ---- UI review pass ----
    S.me = {roles:['manager'],department_ids:['support']}; S.agents = [{id:'a1',name:'Atlas',status:'active'}];
    S.capabilities = [{id:'make-slideshow',name:'Slides',description:'Build a deck.',tools:['create_slideshow'],icon:'slides'},{id:'github-reading',name:'GitHub',description:'Read a repo.',tools:['github_read_file']}];
    S['model-profiles'] = [{id:'demo',name:'Demo',enabled:true},{id:'meta',name:'Live',enabled:true}];
    forge = {...forge0(), mode:'demo'};
    assert.match(createState().why, /Name your agent/);
    forge.name = 'atlas'; assert.match(createState().why, /already exists/);
    forge.name = 'Fresh'; assert.match(createState().why, /Add a tool or write instructions/);
    forge.text = 'Do something'; assert.equal(createState().ok, true);
    assert.equal(uniqueName('Atlas'), 'Atlas 2'); assert.equal(uniqueName('Zed'), 'Zed');
    forge.caps = ['github-reading']; assert.match(createState().why, /live model/); forge.mode = 'meta'; assert.equal(createState().ok, true);
    // the created-agent screen always says why Create is off, and lists a tool only once
    forge = {...forge0(), mode:'demo', caps:['make-slideshow']};
    const screen = forgeScreen();
    assert.match(screen, /id="create-why"/); assert.match(screen, /id="tool-caption"/);
    assert.equal((screen.match(/data-id="make-slideshow"/g) || []).length, 1);
    assert.match(screen, /data-from="orbit"/);
    // a failed task does not repeat itself
    const dup = failedCard({id:'r1', error:'The model took too long to answer. Try again in a moment.', error_code:'provider_timeout'});
    assert.equal((dup.match(/took too long/g) || []).length, 1);
    assert.match(failedCard({id:'r2', error:'Something odd', error_code:'step_limit'}), /narrower/);
    // everything saved can be downloaded
    assert.equal(exportOf({kind:'document', title:'Q3 brief', body:'Hello'}).name, 'q3-brief.md');
    assert.match(exportOf({kind:'email', subject:'Hi', to:['a@b.c'], body:'x'}).text, /^To: a@b.c\\nSubject: Hi/);
    assert.match(exportOf({kind:'slideshow', title:'Deck', slides:[{title:'One', bullets:['a'], stats:[]}]}).text, /## 1\\. One/);
    {
      const deck = {kind:'slideshow', title:'Deck', theme:'ocean', slides:[
        {title:'Voice', layout:'quote', bullets:[], stats:[], quote:{text:'It just worked', by:'Priya'}},
        {title:'Rollout', layout:'steps', ordered:true, bullets:['Invite','Ship'], stats:[]}]};
      const md = exportOf(deck).text;
      assert.match(md, /> It just worked — Priya/); assert.match(md, /1\\. Invite/);
      const q = slideViewer('r1', deck); assert.match(q, /t-ocean l-quote/); assert.match(q, /<blockquote><p>It just worked<[/]p><cite>Priya<[/]cite>/);
      ui.slide.r1 = 1; assert.match(slideViewer('r1', deck), /<ol class="steps"><li>Invite/); delete ui.slide.r1;
    }
    assert.equal(exportOf({kind:'page'}), null);
    // the Files page copes with loading, empty and filled states
    ui.files = null; assert.match(filesScreen(), /Loading your files/);
    ui.files = []; assert.match(filesScreen(), /Nothing saved yet/);
    ui.files = [{id:'s1', agent:{id:'a1',name:'Atlas'}, at:'2026-10-25T10:00:00Z', result:{kind:'document', title:'Q3 brief', body:'Hello', word_count:1}}];
    assert.match(filesScreen(), /Q3 brief/); assert.match(filesScreen(), /data-act="download"/);
    // earlier conversations fold away and the current one stays in front
    S.me = {roles:['manager'],department_ids:['support']}; S.policy = {approval_scope:'agent'};
    S.agents = [{id:'a1',name:'Atlas',status:'active',model_profile_id:'demo',manager_id:'pavan',bindings:[{capability_id:'make-slideshow'}],job_description:'Make decks.',instructions:'SYSTEM TEXT'}];
    S.runs = [{id:'r1',agent_id:'a1',thread_id:'t1',task:'old task',status:'completed',mode:'demo',created_at:'2026-10-24T10:00:00Z'},{id:'r2',agent_id:'a1',thread_id:'t2',task:'new task',status:'completed',mode:'demo',created_at:'2026-10-25T10:00:00Z'}];
    S.conversations = {a1:[{id:'t1',last_run_id:'r1'},{id:'t2',last_run_id:'r2'}]}; S.steps = {};
    const chat = chatScreen('a1');
    assert.match(chat, /Earlier conversations \\(1\\)/); assert.match(chat, /New conversation/);
    assert.ok(chat.indexOf('old task') < chat.indexOf('new task'));
    S.conversations = {a1:[{id:'t1',last_run_id:'r1'},{id:'t2',last_run_id:'r2'},{id:'t3',last_run_id:null}]};
    assert.ok(chatScreen('a1').includes('class="hello"'));
    // the About panel shows what the person wrote, not the system boilerplate, until asked
    ui.metrics.a1 = {p:{approved_actions:0,reviewed_actions:0,successful_tasks:0,evaluated_tasks:0,completed_runs:2,run_count:2}, v:[]};
    S.capabilities = [{id:'make-slideshow',name:'Slides',tools:['create_slideshow'],tool_contracts:[{name:'create_slideshow',risk:'local_write'}]}]; S.departments = [{id:'support',name:'Support'}];
    const about = chatScreen('a1'); assert.match(about, /Make decks\\./); assert.match(about, /Full system prompt/);
    // a bad link never breaks loading
    assert.equal(UUID.test('doesnotexist'), false); assert.equal(UUID.test('8bcde15e-bb59-4d66-b165-4ff57f07f538'), true);
    // ---- GitHub setup lives inside Add a tool, only after GitHub is chosen ----
    const keep = {me:S.me, caps:S.capabilities, gh:S['integrations/github'], lb:S.leaderboard, mk:S.marketplace, dep:S.departments, src:ui.newTool.source};
    S.leaderboard = {capability_usage:[], creator_usage:[], agents:[]}; S.marketplace = []; S.departments = [{id:'support',name:'Support'}];
    S.capabilities = [{id:'make-slideshow',name:'Slides',description:'Build a deck.',tools:['create_slideshow'],icon:'slides',tool_contracts:[]}];
    ui.lib = 'capabilities';
    S.me = {roles:['admin'],department_ids:['support']};
    S['integrations/github'] = {configured:true,connected:false};
    ui.newTool.source = null;
    assert.ok(!libraryScreen().includes('gh-prepare'));          // nothing GitHub-related shows at the start
    assert.ok(!libraryScreen().includes("GitHub isn't ready"));
    ui.newTool.source = 'github';
    assert.ok(libraryScreen().includes('data-act="gh-prepare"')); // appears once GitHub is picked
    assert.ok(libraryScreen().includes('GitHub \u00b7 needs setup'));
    S['integrations/github'] = {configured:false,connected:false};
    assert.ok(libraryScreen().includes('GITHUB_PERSONAL_ACCESS_TOKEN')); assert.ok(!libraryScreen().includes('data-act="gh-prepare"'));
    S['integrations/github'] = {configured:true,connected:false}; S.me = {roles:['manager'],department_ids:['support']};
    assert.ok(libraryScreen().includes('Ask an admin')); assert.ok(!libraryScreen().includes('data-act="gh-prepare"'));
    S.me = {roles:['admin'],department_ids:['support']}; S['integrations/github'] = {configured:true,connected:true,department_ids:['support']};
    assert.ok(!libraryScreen().includes('gh-prepare')); assert.ok(libraryScreen().includes('GitHub \u00b7 connected'));
    S.me = keep.me; S.capabilities = keep.caps; S['integrations/github'] = keep.gh; S.leaderboard = keep.lb; S.marketplace = keep.mk; S.departments = keep.dep; ui.newTool.source = keep.src;
    // data agents can attach a CSV
    S.capabilities = [{id:'analyze-data',name:'Data',tools:['analyze_data'],tool_contracts:[]}];
    S.agents[0].bindings = [{capability_id:'analyze-data'}]; ui.metrics = {};
    assert.match(chatScreen('a1'), /data-act="attach"/);
    console.log('PASS atomic creation, direct tools, builder handoff, durable new conversation, server narration');
  })()`, context);
})().catch(error => { console.error(error); process.exitCode = 1; });

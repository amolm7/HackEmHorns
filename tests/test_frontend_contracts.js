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
    S = { me: { roles: ['manager'], department_ids: ['support'] }, agents: [], capabilities: [{ id: 'write-document', name: 'Documents' }], 'dev/users': [{id:'pavan',name:'Pavan'}], steps: {}, conversations: {}, runs: [], approvals: [] };
    forge = {...forge0(), caps: ['write-document'], mode: 'demo'};
    api = async (...args) => { calls.push(args); return { status: 'created', agent: { id: 'new-agent' } }; };
    await createAgent();
    assert.equal(calls.length, 1);
    assert.equal(calls[0][0], 'agents/quick-create');
    assert.equal('name' in calls[0][2], false);
    assert.equal(location.hash, '#/agent/new-agent');
    S.agents = [{id:'target',name:'Target',spec_version:4}];
    forge = {...forge0(), target:'target', caps:['write-document']};
    api = async (...args) => { calls.push(args); return {id:'target',name:'Target'}; };
    await createAgent();
    assert.equal(calls.at(-1)[0], 'agents/target/capabilities');
    assert.equal(calls.at(-1)[2].expected_spec_version, 4);
    S.me.roles = ['builder'];
    forge = {...forge0(),caps:['write-document'],mode:'demo'};
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
    console.log('PASS atomic creation, direct tools, builder handoff, durable new conversation, server narration');
  })()`, context);
})().catch(error => { console.error(error); process.exitCode = 1; });

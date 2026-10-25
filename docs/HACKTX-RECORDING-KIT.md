# Hire an Agent — HackTX recording kit

Target: 150 seconds. Audience: NMC / Team Square judges. Message: turn repeated agent setup into reusable team expertise. No NMC integration or measured savings claims.

## Current recording readiness

Checked October 25, 2026 against the running app. Meta and Gemini are disabled; GitHub is neither configured nor connected. The live GitHub story is blocked until a credential owner configures the providers locally and prepares the GitHub connector. Do not enter credentials in the recording.

The sample-data fallback was rehearsed through the actual HTTP API: agent creation → CSV analysis → saved slideshow → company template publication → installation. Two tools executed within the eight-call limit, with zero model calls. The installed copy has no bindings, is Intern, and has status `needs_connections`. These are backend checks; screen recording and visual deck inspection remain to be done.

The fallback deck has five generic template slides. It is not an AI-written briefing derived from the analysis. Show the real analysis chart as the fallback opening result and identify the deck as a template output. Do not splice fallback results into the live GitHub story.

## Primary video — live GitHub version

Use this version only after a successful live rehearsal. Specialist: **Repository Briefing Analyst**. Capabilities: GitHub reading and Make a slideshow. Keep agent-level approval. Choose a small public repository that the prepared connector can read; use the same repository in every clip.

| Time | Operator action | Voiceover |
|---|---|---|
| 0:00–0:15 | Open the strongest slide of the actual saved deck, then the agent overview. | Teams need useful results from AI, but each workflow means configuring tools, writing instructions, and deciding what it can access. Hire an Agent turns that setup into expertise the whole team can reuse. |
| 0:15–0:35 | Library: open a capability playbook. Add Repository Reader using the prepared GitHub connector. | Our Library combines approved tools with instructions for using them well. A manager can make a connected capability available to their department, so employees build on shared setup instead of starting from scratch. |
| 0:35–1:00 | Create Repository Briefing Analyst. Select the two capabilities and enabled live model. Show instructions, scope, and confirmation. | I need a specialist that reads a repository and prepares a concise briefing. We combine two capabilities, choose the model, and review its scope. The manager approves this agent’s configuration once, and the platform enforces its approved tools. |
| 1:00–1:35 | Enter repository and task. Show reads and slideshow save. Cut waiting, then open the deck. | Now we give it a goal: read the README and open issues, then save a four-slide briefing. It retrieves source material through GitHub and saves the presentation in our workspace. Here is the actual output: purpose, current priorities, risks, and next steps. We can open it and review the recommendations. |
| 1:35–2:00 | Open one tool result and its source URL. Show the corresponding slide and activity history. | The result has an execution trail. Here is a source the agent read, and here is the corresponding point in the briefing. A reviewer can inspect that evidence and judge the result. Monitoring is shared across workflows rather than rebuilt for every specialist. |
| 2:00–2:20 | Publish template; install it; show local configuration requirement. | When a workflow works well, we share its template. Another team reuses the instructions, capabilities, and model configuration, then connects its own authorized access. Credentials, task history, and trust do not transfer. |
| 2:20–2:30 | Finished deck, then product name. | For NMC’s challenge, we focused on a practical problem: turning team knowledge into repeatable results. Build the specialist once. Reuse it across the team. Describe the job. Hire the agent. |

### Paste-ready live job description

Prepare concise repository briefings for busy project leads. Read only the root README and up to five open issues. Save a four-slide presentation covering purpose, current priorities, risks, and next steps. Cite source URLs. Distinguish facts from recommendations. Use only GitHub reading and slideshow creation. Do not explore additional files.

### Paste-ready live task

Read only the root README and up to five open issues for this repository. Save a four-slide briefing covering purpose, current priorities, risks, and next steps. Cite source URLs and distinguish facts from recommendations. Do not explore additional files.

The issue adapter can return a bounded sample of up to ten issues; the instruction to use five does not change that transport limit. Verify the final deck and actual calls before narrating success. Do not claim a whole-repository audit.

## Fallback video — recordable sample-data version

Use the same seven time slots, replacing their footage and narration with the following. Keep a visible “Fictional data · deterministic demo · no AI model called” label during execution and results.

| Time | Operator action | Voiceover |
|---|---|---|
| 0:00–0:15 | Open the analysis chart with three channel bars. | Teams repeat the same tool setup whenever they need a new AI workflow. Hire an Agent packages tools, instructions, and oversight into specialists the team can reuse. Here is a working sample-data walkthrough. |
| 0:15–0:35 | Library: inspect Analyze data and Make a slideshow, including playbooks. | Our Library pairs available tools with playbooks for using them. For this walkthrough, we combine data analysis and presentation creation. The inputs are fictional, and the execution uses a deterministic demo rather than a live language model. |
| 0:35–1:00 | Show creation of an equivalent Launch Analyst and its scoped configuration. | We describe the job, choose its capabilities, and review its scope. A manager confirms the agent configuration once. This specialist can analyze a supplied table and save a presentation. It has no permission to send or publish the resulting work outside this workspace. |
| 1:00–1:35 | Paste the sample task. Show both tool steps; open analysis, then template deck. | We supply three fictional marketing channels. The analysis tool calculates 540 signups in total, with Social highest at 240. The presentation tool also saves a five-slide template deck. These are real tool executions and a saved artifact. The deck is a generic demo template; original slide writing requires a configured live model. |
| 1:35–2:00 | Show CSV, numeric analysis, tool steps, saved deck. | We can inspect the supplied values and the calculation behind the result. The activity trail records which tools ran and what they returned. This distinguishes a saved deliverable from a chat message claiming that one exists, and gives the reviewer concrete evidence to inspect. |
| 2:00–2:20 | Show published template and installed copy’s connection requirement. | We can share this specialist as a company template. The installed copy carries its instructions and capabilities, but no connection bindings. Another team must configure its own authorized access. The setup is reusable; credentials and trust history do not transfer. |
| 2:20–2:30 | Return to chart and product name. | For NMC’s challenge, our focus is practical: turn repeated setup into reusable team expertise. Describe the job. Hire the agent. Review the work. Share what works. |

### Paste-ready sample task

```text
Fictional campus launch channel briefing. Analyze this supplied sample data and save a slideshow. Label all content as sample data and deterministic demo templates.
channel,signups
Ambassadors,180
Social,240
Events,120
```

### Prepared fallback records

- Original agent: http://localhost:8000/#/agent/6ecec9eb-e9ca-4f55-81a9-478ea3a16339
- Installed copy: http://localhost:8000/#/agent/90334deb-ce78-4161-ad75-44d27668f2cc
- Completed run: `cb4957f7-c412-4b0a-b3c4-02439f89d9ac`
- Saved deck: `66641b4b-2ab4-45c2-9c36-43d1be36fb60`
- Company listing: `4414490f-533f-427b-b68b-291d9048c77d`
- Review source evidence in `rehearsal-evidence.json`. Its `sample_data: false` metadata means the tool received user-supplied data; these particular supplied values are fictional. Preserve that distinction in narration.

## Capture and edit order

1. **03-execution:** record a fresh successful run and opening of its actual result. Capture waiting time; trim it in editing, with “Processing time shortened” where applicable.
2. **04-evidence:** record source/input evidence and activity from the same run. Capture 3 seconds of still footage at both ends.
3. **05-reuse:** record publishing and installation, ending on the new copy’s connection requirement. A prepared copy is available for rehearsal; create a fresh equivalent copy for footage of installation.
4. **02-setup:** record Library and creation of the equivalent specialist. Match capability selection, instructions, model, and names to execution footage. Do not portray the new agent as the source of a different agent’s run.
5. **01-result-hook / 06-close:** capture the finished output and product overview.
6. Assemble in video order: hook → Library → creation → execution → evidence → reuse → close. Record voiceover after the screen edit; read naturally and trim holds to fit 150 seconds.

Use one narrator and one operator. Record a single browser window at 1920×1080 with readable text, hide notifications, and avoid showing other tabs or credentials. Rehearse the read aloud before capture. If a section runs long, shorten narration; never accelerate it beyond comfortable speech.

## Final review before submission

- Confirm final duration is 2:30 and every label is readable.
- Verify deck opens visually and source evidence supports every claim. Backend completion alone is insufficient.
- Confirm installed copy has no transferred bindings and needs local configuration.
- Use either live GitHub narration or the labeled sample-data narration throughout.
- No invented time savings, production-readiness claims, NMC affiliation, autonomous sending, or claims that all tool calls pause under the default policy.
- No recording has been captured or edited by this kit. Provider setup, visual rehearsal, capture, voiceover, and final export remain separate completion steps.

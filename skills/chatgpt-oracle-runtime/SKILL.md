---
name: chatgpt-oracle-runtime
description: Current Oracle runtime path for new ChatGPT work: regular modes use the manually registered DevSpace app, Pro is attachment-only, and it includes recovery, comprehensive relay, and genuine multi-session Web Multi-GPT.
---

# ChatGPT Oracle Runtime

This is the only active browser path for all new GPT work. CodexPro and
agbrowse are frozen for exact legacy recovery only. Regular modes use DevSpace;
Pro uses Oracle attachment transport without any app.

`chatgpt_oracle_dispatch.py` supports exactly `direct`, `plan`, `review`, `edit`,
`orchestrator`, `deep-research`, `manual`, and `pro`. `manual` is a supported
`manual-no-launch` profile, not a new submission route. `answer` in
`chatgpt-question-designer` is the prompt-design alias for dispatcher mode
`direct`, not a separate dispatcher key. Regular routes
select `gpt-5.6` and send only `@DevSpace` plus the absolute project mission
path and a compact exact-workspace guard. The web GPT must use only the exact
project root recorded in that mission, read the mission and applicable
`AGENTS.md` completely first, and may retry that same root once after a timeout.
It must not substitute a parent, child, active workspace, or shell boundary
workaround. Pro selects the account-visible Pro model and sends one short instruction
plus exact attachment files; it never mentions DevSpace.
Regular routes select `GPT-5.6 Sol` with `heavy` and require Oracle
evidence for visible `Extra High`. Never invent xhigh or silently downgrade.

## Manifest

Require schema `codex.chatgpt.oracle-run/v1` with:

- `project_root`: absolute existing directory.
- `mission_path`: absolute UTF-8 regular file inside the project.
- `app_name`: one-line app name, without a leading `@`, for regular routes.
- `task_kind: pro` plus one or more exact `attachments` for Pro.
- `mode`: `browser`.
- Optional `run_root`, `oracle_command`, `oracle_args`, `thinking_time`,
  hash-validated `copy_profile`, and mutex timeout.
- Regular direct/orchestrator manifests use `task_outcome_contract: "v1"`.

## Run

Preview first:

```powershell
python skills/chatgpt-oracle-runtime/scripts/run_chatgpt_oracle.py run --manifest C:\absolute\oracle-job.json --dry-run
```

The preview must include final argv, prompt first line, absolute mission path, SHA-256, and artifact paths without launching Oracle or a browser.
Use this wrapper preview only. Do not substitute Oracle's own browser `--dry-run`, because Oracle 0.16.1 may still enter browser preflight.

Execute only after an explicit live-run request:

```powershell
python skills/chatgpt-oracle-runtime/scripts/run_chatgpt_oracle.py run --manifest C:\absolute\oracle-job.json
```

Complete requires Oracle exit code zero, a nonempty `--write-output` artifact,
and—when `task_outcome_contract` is `v1`—a final
`TASK_OUTCOME: EXECUTED` marker. `TASK_OUTCOME: NOT_EXECUTED` and
`TASK_OUTCOME: BLOCKED` preserve terminal transport evidence but return
attention-required; transport success alone never claims project execution.
A nonzero Oracle exit after launch, including a browser response timeout, is
`attention_required` rather than proof that the web session failed. It retains
same-project ownership and permits only exact-slug `live` or `harvest`
recovery; it never authorizes a replacement submission.
For non-Pro runs, `--browser-timeout` is one overall answer budget. Oracle
fallback capture consumes only the remaining time. A host wall-clock watchdog
adds a short grace for a wedged CDP call; if it expires, the runner returns
`post_submit_watchdog_timeout`, preserves the exact process/session and browser
evidence, and remains unsafe for a fresh submission.

## Codex Luna tracking owner

For every authorized live Web GPT command that may wait for a provider answer,
delegate the entire blocking command before it starts to exactly one native
Codex worker with `agent_type: "worker"`, `model: "gpt-5.6-luna"`,
`reasoning_effort: "high"`, and `fork_context: false`. Give it a compact,
self-contained capsule containing the exact command, manifest, project root,
and explicit non-goals. That worker is the sole submission-and-wait owner.

The Luna worker is a signal-only lifecycle observer, not a reviewer. It may
launch the exact command, wait, and relay only runner-emitted lifecycle/status,
exit code, exact run or workflow identity, and artifact paths or hashes. It
must not open or read project files, mission contents, `output.md` or
transcript contents, inspect Git diffs, run independent validation, interpret
test meaning, assess answer quality, or decide that the user task is complete.
If the exact parent command itself runs a deterministic gate, the worker
reports only its exit/status signal. After the worker returns, the main Codex
session reads the artifacts, inspects files and diffs, runs any required
verification, and makes every review and completion decision.

The main Codex session must not execute the same live command, poll its run
directory, or launch another tracking worker while that owner is active. Wait
through the native worker-wait mechanism and surface only changed terminal or
attention-required evidence. For Web Multi or comprehensive mode, one Luna
worker owns the whole parent command; do not create a tracking worker per lane
or stage.

Unchanged waits are silent. Keep the main turn open in native worker wait; do
not emit heartbeat commentary such as "still running", "no signal yet", elapsed
time, or unchanged-run summaries. A wait-window timeout is an internal control
event: silently reissue wait for the same worker without reading the run in the
main session. The tracking worker should use one blocking watcher/tool call
where possible instead of a model-generated polling narration. Do not send a
final answer merely because a worker was spawned. Output is allowed only for an
actual terminal/attention transition, worker termination that requires one
successor, or an explicit user status request; after a requested snapshot,
resume silent wait.

If an exact run already exists, the tracking worker may use only the official
exact-slug `live` or `harvest` recovery path. It must never resubmit, use
`--force`, abandon or kill the run, edit state, or touch credentials and
profiles. If the requested Luna model or worker facility is unavailable, do
not silently substitute another model or let a second owner take over; report
the limitation while preserving the exact run ownership.

## Recovery

Recovery always reuses the stored Oracle slug and never restarts or submits:

```powershell
python skills/chatgpt-oracle-runtime/scripts/run_chatgpt_oracle.py recover --run-dir C:\absolute\run --action harvest
```

Use `--action live` only to keep following the same stored session. A successful recovery must write a nonempty stored `output.md`, update `state.json` to `complete`, and refresh `transcript.md`; exit code zero without output is `attention_required`.
The CLI keeps `--action live` inside one exact-slug recovery process for up to
90 minutes by default. Transient `stalled`, `running`, or observer disagreement
states keep the same live authority and project lock; they do not return every
few minutes for Codex-side polling. When the exact session becomes terminal,
the same process performs one harvest and returns once.
If Oracle proves both that no live tab matches the exact slug and that its
metadata has no recoverable canonical conversation URL, the runner returns
`recovery_binding_unavailable` immediately instead of repeating that invariant
failure for 90 minutes. It preserves `submitted_unknown` ownership; restore the
exact persisted conversation URL before recovering the same slug, and never
replace or resubmit it.

Oracle's `Prompt did not appear in conversation before timeout (send may have
failed)` message is likewise submission-uncertain. No-live-tab plus missing
saved-URL recovery evidence does not mechanically prove non-submission. A
maintenance owner may release that exact run only after explicit user
confirmation through `chatgpt_oracle_run.py settle-no-submission` with the
exact run directory, `--confirmation user-confirmed-no-submission`, and a
concise reason. The settlement is hash-bound to
project/workflow/stage/attempt/input evidence and does not launch Oracle;
comprehensive mode may consume only one replacement for that binding.

Direct same-project runs hold one cross-process mutex for the entire Oracle
process lifetime. A Multi parent owns that project mutex while authorized
children use a short parent-scoped launch mutex and isolated copied Chrome
profiles, then wait concurrently.
Control state, Oracle output, and transcripts live under
`%USERPROFILE%\.codex\state\chatgpt-oracle`, outside the DevSpace-writable
project.

Use `chatgpt_oracle_comprehensive.py` for the bounded plan → optional
Pro/Multi → review → implementation → final web gate flow. Each web stage
writes the next mission; the host validates only UTF-8, identity, paths, and
hashes. Use `chatgpt_oracle_multi.py` for independent solver sessions in waves
of at most five and one merger over handoff files.

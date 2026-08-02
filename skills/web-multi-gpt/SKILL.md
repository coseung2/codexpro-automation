---
name: web-multi-gpt
description: Run genuine parallel regular ChatGPT sessions through Oracle, with stable solver lanes, waves of at most five, file handoffs, and one merger. No single-GPT role simulation and no new agbrowse runs.
---

# Oracle Web Multi-GPT

Use `bin/chatgpt_oracle_multi.py` with schema
`codex.chatgpt.oracle-multi/v1`. Required fields:

- absolute `project_root`, project-contained `output_dir`
- `solvers`: 2..25 unique safe lane IDs and absolute mission paths
- `merger_mission_path`
- `max_concurrency`: 1..5
- optional `next_stage_result_path` for comprehensive relay

Advisory lanes are `access: read-only`. A write lane must declare
`access: worktree-write` and a distinct pre-created worktree `project_root`;
the canonical root is forbidden for write lanes.

```powershell
python "$env:USERPROFILE\.codex\bin\chatgpt_oracle_multi.py" --manifest C:\project\multi.json --dry-run
```

Each lane receives its own Oracle slug/run/output and only `@DevSpace` plus its
mission path. Lanes run in stable waves of at most five; a larger topology is
not reduced. Successful handoffs are preserved and exactly one merger consumes
their paths in lane order. The parent holds same-project exclusion while child
launches use a short parent-scoped mutex. On Windows each lane uses a separate
throwaway copy of the signed-in Oracle profile, preventing one solver from
closing or taking over another solver's Chrome session.

Register the whole blocking Multi parent command with exactly one
`chatgpt_oracle_relay.py` under the `chatgpt-oracle-runtime` zero-model relay
contract, then end the current turn. Do not create a Luna tracking worker per
parent or lane, poll lanes, or keep Sol waiting. Oracle owns lane concurrency;
the relay resumes the same task after the parent exits and the main Codex
reviews all results in that resumed turn.

No attachments, app/settings automation, broad tab cleanup, `--force`,
restart, or silent resubmission. Oracle owns one-shot tab archival. Existing
agbrowse Multi state is recovery-only. CodexPro is frozen and is never a solver
or merger transport.

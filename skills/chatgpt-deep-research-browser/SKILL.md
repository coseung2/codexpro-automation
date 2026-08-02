---
name: chatgpt-deep-research-browser
description: Run new ChatGPT Deep Research through Oracle browser research deep plus the manually registered DevSpace app; legacy agbrowse is recovery-only.
---

# Deep Research through Oracle

Create one absolute UTF-8 mission inside the project, then use:

```powershell
python "$env:USERPROFILE\.codex\bin\chatgpt_oracle_dispatch.py" --mode deep-research --project-root C:\project --mission-path C:\project\research.md --manifest-output C:\project\.ai-bridge\deep-research.json --reasoning-level "Very High" --dry-run
```

The compiled Oracle manifest uses `gpt-5.6`, model strategy `select`, Oracle
`heavy`, visible `Extra High`, and `--browser-research deep`. It sends no
attachment and performs no app picker or settings action. Remove `--dry-run`
only for an explicitly authorized live run.

Register the whole blocking live Deep Research command with exactly one
`chatgpt_oracle_relay.py` under the `chatgpt-oracle-runtime` zero-model relay
contract, then end the current turn. Do not create a Luna tracking worker or
keep Sol waiting. The relay resumes the same task after the research command
exits; the main Codex reviews the result in that resumed turn.

Do not silently replace Deep Research with ordinary search or Pro. Existing
agbrowse Deep Research records may be recovered only by their exact old run
directory; never create a new agbrowse research run. CodexPro is frozen and is
not a fallback.

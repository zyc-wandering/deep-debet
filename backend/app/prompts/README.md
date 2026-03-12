# Prompt Catalog

This directory centralizes every preset prompt sent to LLM-backed agents.

- `host.py`
  - host system prompt
  - topic research prompt
  - focus option extraction prompt
  - debater persona generation prompt
  - markdown summary prompt
  - structured summary prompt
  - host follow-up prompt
- `debater.py`
  - debater base system prompt
  - generic turn instruction
  - stage-specific system prompt
  - stage-specific turn instruction
  - debater follow-up prompts
  - optional realtime references section
- `context.py`
  - debater context window rendering
  - rolling-summary rendering

Agent implementations in `backend/app/agents/` should only compose data and call builders from this directory.

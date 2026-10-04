---
default_agent: planner
permission:
  read:
    "*": allow
    "sources/**/*.pdf": deny
  edit:
    "NOTES.md": allow
    "output/**/*.md": allow
    "analysis/**": deny
  bash:
    "*": deny
  task:
    ingestor: allow
    helper-b: deny
---
# Planner agent (fixture)

"""Claude Code host renderer.

Emits, from a methodology + role library + project profile:
  - .claude/agents/<role>.md   (frontmatter tools from posture; body from lens+binding)
  - .claude/settings.json      (hooks from the constitution's mechanical gates)
  - .claude/CLAUDE.md          (a merged, marked orchestrator block — never a clobber)
  - .harness/                  (host-neutral source + state: methodology, profile,
                                feature_list, CHECKPOINTS, specs/, progress/)

Posture -> tools (this host):
  mutates: false           -> Read, Glob, Grep, Bash
  mutates: true            -> + Write, Edit
  capabilities: [dispatch] -> + Agent
  context: fresh           -> rendered to run as an isolated subagent

Not implemented yet.
"""

from __future__ import annotations

POSTURE_TOOLS = {
    "read": ["Read", "Glob", "Grep", "Bash"],
    "write": ["Read", "Glob", "Grep", "Bash", "Write", "Edit"],
}

"""Compiler: library (lens) + methodology (binding) + project profile -> host files.

This is the part the old harness never had — `init`/`upgrade` are not file-copy, they
RENDER. Not implemented yet; the surface (cli.py) lands first.

Planned shape:
    render(methodology, profile, host) -> dict[path, content]
where the host renderer (hosts/<host>.py) maps:
  - role posture -> host toolset (mutates -> +write tools; context:fresh -> subagent)
  - lens prose + binding (reads/writes/gate/transition) -> the agent body
  - constitution mechanical gates -> host hooks
  - the orchestrator role -> the merged instruction block
"""

from __future__ import annotations


def render(methodology: str, profile: dict, host: str) -> dict[str, str]:
    raise NotImplementedError("compiler not built yet")

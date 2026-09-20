<!-- mw-profile: v2 -->
[mw] mode: partition
[mw] Workspace profile (target.yml essentials, injected at dispatch;
full file: <CTRL>\.agenticdoc\target.yml)
Control workspace: <CTRL>
Parent root (extended workspace, writable): <CTRL>\parent
Partition root (worker cwd): <CTRL>\shard
Named roots:
- sdk: <CTRL>\sdk
- data: <CTRL>\data
Toolchain commands (placeholders resolved):
- build: make -C <CTRL>\shard SDK=<CTRL>\sdk --parent <CTRL>\parent
- regen: python <CTRL>\data/Tools/regen.py
Context firewall (deny globs, enforced by the read-scope layer):
- **/*.uasset
- **/DerivedDataCache/**
Contract:
- forbidden paths: **/Generated/*
- conventions:
  Line one of the conventions.
  Line two of the conventions.
  
- docs (references, not inlined):
  - <CTRL>\docs\contract-notes.md

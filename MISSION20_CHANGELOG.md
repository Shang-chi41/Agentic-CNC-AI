# Mission 20 — Changelog

## Three-flow alignment
- Locked CHECK to MATLAB/Simulink → NX; FluidNC remains non-executing in CHECK.
- Preserved RUN preflight: exact artifact staged in MATLAB, then FluidNC owns physical motion.
- Added FluidNC status fanout timing provenance for NX and MATLAB.
- Locked JOG origin to FluidNC WebUI only across Cloud, Edge worker, telnet API/CLI, AI guidance and frontend.
- Added passive external-motion observer and short-JOG MPos-delta fallback.
- Manual motion during CHECK now clears the sync epoch and prevents stale-context approval.
- Direct one-line G-code bypass remains fail-closed.

## Verification and tooling
- Strengthened full connection audit S016 for the three flow ownership contract.
- Added JWT/login support and MATLAB Bridge listener grouping to safe-live audit path.
- Added direct-script and module-invocation regressions for the audit tool.
- Added secret-free clean-package CI verifier that creates/removes a temporary fake `.env` without overwriting an operator `.env`.
- Added Mission 20 tests, verifier and Spec Kit evidence pack.

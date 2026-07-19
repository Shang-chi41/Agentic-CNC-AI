# Mission 09 — CHECK Gate, Arc Preview, and Verified G-code Knowledge

## Completed

- CHECK no longer approves from silence or line dispatch completion.
- Approval requires the exact CHECK session's CNC3 motion completion.
- sim_only CONNECT TEST, CHECK, HOME SYNC, and MACHINE RUN are separated.
- Circular G2/G3 preview works, including full-circle and helical arcs.
- Centered G55 negative coordinates are preserved.
- T1 + Aluminum 6061 is retained.
- Plain “rectangle” requests ask pocket vs contour.
- Verified structural patterns are used as runtime RAG/few-shot guidance.
- Generated programs can become learning candidates only after full verification and human review.

## Verification

| Check | Result |
|---|---:|
| Mission 09 evaluation | 10/10 |
| Mission 09 targeted tests | 13 passed |
| Full integration terminal summary | 174 passed |
| Frontend JS | 16 files, 0 failed |
| Arc parser | 76 circle points, 63 helical points |
| MCP | 8/8 tools |
| Compile | PASS |

## Indicator interpretation

```text
sim_only idle       → CONNECT TEST active
sim_only CHECK      → CHECK active
CHECK passed        → CHECK completed indicator persists
sim_only            → MACHINE RUN remains blocked
real HOME/NX synced → HOME SYNC complete with an epoch
machine gate ready  → MACHINE RUN ready
actual stream       → MACHINE RUN active
```

## Verification boundary

Sandbox contracts are verified. Real MATLAB/NX/FluidNC/browser behavior still requires the runtime checklist.

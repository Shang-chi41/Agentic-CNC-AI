# Mission 16 — CHECK Pill + G-code Queue Terminal Sync

## Baseline

- Input package: `Automaech_Mission15_AI_CHECK_TERMINAL_CHAT_SYNC_CLEAN.zip`
- Baseline SHA-256: `c9c73fec1b5645920ab397e308343a89c8be4a06871b32aa7346b2795b5af149`
- Date: 2026-07-13

## Observed failure

After MATLAB and NX MCD completed CHECK and returned to the reference pose:

- the AI chat showed a terminal result;
- the `DATAFLOW + GATE` CHECK pill remained yellow and still reported `Owner: matlab_check`;
- the G-code Queue row remained `Chờ CHECK` instead of refreshing to the approved/Confirm stage.

## Root causes

1. `_post_check_return_to_start()` temporarily changed workflow activity to `ACTIVE / POST_CHECK_RETURN`, but the success path did not restore activity to terminal `COMPLETED`. The canonical dataflow resolver also treated the phase name alone as active, even when completion was already terminal. This pinned the HMI in `pre_run_check`.
2. In SIM-only, successful MATLAB + NX completion did not call `sync_state.mark_gcode_check_passed()`. CHECK completion and production approval were incorrectly coupled, leaving `gcode_check.status=CHECKING` forever.
3. `aiCheckGCode()` did not call the Control-page refresh callback when CHECK finished. MongoDB could already contain `status=approved`, while the queue kept rendering its earlier `needs_check` snapshot.
4. The successful CHECK bubble offered `Lưu vào Queue`, although the CHECK pipeline had already saved the exact artifact. Pressing it could create a second `needs_check` document and make the stale yellow row appear to be the checked artifact.

## Fix

- A terminal/completed workflow can no longer be kept in `pre_run_check` by a stale phase.
- Record `gcode_check=PASSED` whenever MATLAB and NX terminal evidence completes without collision, independently from production approval.
- Restore workflow activity to `COMPLETED / TERMINAL` after the post-CHECK return finishes.
- Refresh G-code Queue immediately after structured terminal CHECK response.
- Remove the duplicate post-CHECK save action; the UI now reports that the exact artifact ID is already in the Queue.

## State contract

```text
CHECK completion:
MATLAB terminal + NX terminal + no collision
→ gcode_check.status = PASSED

Production approval:
CHECK completion + production-eligible edge_backend.main context
→ GCode_Files.status = approved
→ operator may press Confirm

Run permission:
approved artifact + operator Confirm + HOME/SYNC/readiness/interlocks
→ RUN may become available
```

`main_sim_only` may make the CHECK pill terminal/green because CHECK completed, but it must keep `approval_state=NOT_ELIGIBLE`; its Queue row must not become Confirm/RUN eligible.

## Files changed

- `edge_backend/runtime/dataflow_contract.py`
- `edge_backend/ai/gcode_validator.py`
- `frontend/js/ai_chat.js`
- `integration_tests/test_mission16_check_ui_queue_terminal_sync.py`

## Verification

- Python `compileall`: PASS
- `node --check frontend/js/ai_chat.js`: PASS
- `node --check frontend/js/monitor.js`: PASS
- Mission 14 + Mission 16 targeted tests: `17 passed`
- Selected cross-mission regression: `115 passed`

The first cross-mission invocation had one environment-fixture failure because the clean package intentionally excludes `.env`. The suite was rerun with a temporary copy of `.env.example` as `.env`, then the temporary file was deleted; all 115 selected tests passed.

## Evidence boundary

Evidence level: L1/L2 static and sandbox tests only. Browser deployment, real MATLAB R2023b, real NX MCD and physical CNC were not executed in this environment.

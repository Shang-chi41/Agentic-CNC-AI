# Mission 20 — L4 Runtime Verification Checklist

## Preconditions
- Run `edge_backend.main`, not `main_sim_only`.
- MongoDB, Neo4j, Cloud and Edge ready.
- MATLAB Bridge process running: listeners 5000/5100/5101.
- Simulink model connected to 5100/5101.
- NX MCD connected to Edge 6001.
- FluidNC connected and safe lab setup.
- Authenticated unified status available via JWT/login.

## CHECK
- [ ] Start exact artifact CHECK.
- [ ] Verify no FluidNC G-code stream begins.
- [ ] Verify MATLAB packet carries matching check_id/hash.
- [ ] Verify NX follows MATLAB CHECK trajectory.
- [ ] Verify MATLAB + NX terminal/collision reconciliation.
- [ ] During a safe test, issue a small FluidNC WebUI JOG while CHECK is active; verify approval becomes REJECTED/STALE and a new HOME/SYNC/CHECK is required.

## RUN
- [ ] Verify MATLAB receives exact approved artifact and returns run_ready.
- [ ] Verify FluidNC receives exact same artifact only after Confirm/readiness.
- [ ] Verify NX position follows FluidNC MPos, not MATLAB planner.
- [ ] Capture `run.fanout_trace` latency distribution.
- [ ] Verify no independent MATLAB motion before FluidNC status.
- [ ] Test MATLAB/NX disconnect behavior only after operator approves the safety procedure.

## JOG
- [ ] Project HMI/API/AI/CLI JOG attempts are rejected.
- [ ] JOG from FluidNC WebUI moves the physical machine.
- [ ] Edge mirrors actual MPos to NX.
- [ ] Old sync/check becomes stale.
- [ ] Test a short pulse below one poll interval and confirm MPos-delta fallback invalidates state.

## Evidence level
Do not mark L4 until logs/screenshots/status records prove these points. Physical accuracy/interlocks remain L5.

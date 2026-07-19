# Mission 16 Runtime Runbook

## Deploy

1. Keep your existing local `.env`; the clean package does not include it.
2. Replace the project with the Mission 16 package or apply the patch.
3. Restart Cloud and the selected Edge entrypoint.
4. Press `Ctrl+F5` in the browser to bypass cached `ai_chat.js` and `monitor.js`.

## Production CHECK test

1. Start `edge_backend.main`, not `main_sim_only`.
2. Confirm `/api/system/status` reports a production-eligible context and only one active Edge entrypoint.
3. Generate or load one G-code artifact in the AI/Control workflow.
4. Press `Kiểm tra G-code` once.
5. Wait until MATLAB and NX MCD complete and return to reference.

Expected:

- AI chat structured result:
  - `terminal_state=COMPLETED`
  - `approval_state=APPROVED`
  - `matlab_ok=true`
  - `nx_complete=true`
  - `nx_collision=false`
- CHECK pill changes from yellow to green after post-return completes.
- `Owner` no longer remains `matlab_check`.
- G-code Queue refreshes automatically to `Approved` and displays the `Confirm` button.
- The UI does not create a second G-code row after CHECK.
- RUN remains blocked until operator Confirm and all HOME/SYNC/readiness gates pass.

## SIM-only negative test

Run `edge_backend.main_sim_only` and perform the same CHECK.

Expected:

- terminal CHECK may complete;
- CHECK pill no longer remains indefinitely yellow;
- `approval_state=NOT_ELIGIBLE`;
- Queue must not expose production Confirm/RUN authority;
- FluidNC receives no command.

## Other negative tests

- Disconnect NX MCD: CHECK must fail or remain non-terminal, never green-approved.
- Inject collision: result must be rejected/red.
- Change G-code after approval: Confirm must be blocked by checksum mismatch.
- Run both `main` and `main_sim_only`: machine gate must stay blocked.

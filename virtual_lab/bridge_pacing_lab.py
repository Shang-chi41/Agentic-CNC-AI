"""Pure-Python discrete-event model of the MATLAB bridge <-> Simulink queue.

Purpose
-------
AUDIT_cnc_hmi_v18_A_3axis_CLEAN_READY_2026-07-08.md found two root causes,
both about *timing/control*, not motion math (cnc3_virtual_lab.py already
covers the motion/protocol side):

  Bug #1 - RUN_CREATE_OPEN_3AXIS_SIMULINK_R2023B.m calls open_system() but
           never issues SimulationCommand='start'. The
           CNC3_Gcode_TCP_ClosedLoop_R2023b block therefore never ticks and
           never drains whatever the bridge writes to port 5100.

  Bug #2 - run_edge_matlab_bridge_R2023b_CNC3_quiet_FIXED.m calls
           pause(SIM_GCODE_LINE_PERIOD_S) after every line it writes
           (including the leading '__RESET__' line in CHECK mode). With
           .env's SIM_GCODE_LINE_PERIOD_S=0.500, the bridge paces itself
           ~15x slower than the block's real consumption rate
           (SampleTime * SendEverySamples = 5e-5 * 667 = 0.03335s), adding
           pure artificial latency on top of whatever Simulink actually
           needs.

This module models the interaction as a deterministic single-server FIFO
queue (producer = bridge, consumer = Simulink block) using the standard
Lindley recursion for departure times:

    departure[i] = max(arrival[i], departure[i-1]) + service_time

so tests run in milliseconds regardless of the real-world pacing being
tested (no real sleep()), while still being numerically faithful to the two
real .m files above. It intentionally does NOT model 3D motion (that is
cnc3_virtual_lab.py's job) - only the producer/consumer timing that Bug #1
and Bug #2 are about.
"""
from __future__ import annotations

from dataclasses import dataclass

# Nhịp tick thật của khối CNC3_Gcode_TCP_ClosedLoop_R2023b, lấy từ
# create_chay_dao_3axis_nx_loop_model_R2023b.m (SampleTime=5e-5,
# SendEverySamples=667). Đây là "sự thật mặt đất" để so sánh mọi giá trị
# SIM_GCODE_LINE_PERIOD_S trong .env.
SIMULINK_SAMPLE_TIME_S = 5e-5
SIMULINK_SEND_EVERY_SAMPLES = 667
CONSUMER_PERIOD_S = SIMULINK_SAMPLE_TIME_S * SIMULINK_SEND_EVERY_SAMPLES  # 0.03335s


@dataclass
class TransferResult:
    total_items: int
    drained: int
    finished: bool
    finish_time_s: float | None
    departure_times_s: list[float]


def simulate_bridge_transfer(
    n_lines: int,
    producer_period_s: float,
    model_started: bool,
    consumer_period_s: float = CONSUMER_PERIOD_S,
    include_reset: bool = True,
) -> TransferResult:
    """Simulate run_edge_matlab_bridge_..._FIXED.m pushing ``n_lines`` G-code
    lines (plus one leading '__RESET__' if ``include_reset``) into
    CNC3_Gcode_TCP_ClosedLoop_R2023b, one line every ``producer_period_s``
    seconds (mirrors ``pause(cfg.linePeriodS)`` after every ``write_line_to_
    simulink`` call in the real bridge script).

    ``model_started`` mirrors whether ``SimulationCommand`` was ever set to
    ``'start'`` for the model (Bug #1). If False, the consumer never ticks,
    so the queue never drains - this is intentionally *not* a timeout, it
    matches the real symptom: the HMI shows "MATLAB opened" forever with
    zero motion/result frames coming back.
    """
    total_items = n_lines + (1 if include_reset else 0)

    if not model_started:
        return TransferResult(
            total_items=total_items,
            drained=0,
            finished=False,
            finish_time_s=None,
            departure_times_s=[],
        )

    arrival_times = [i * producer_period_s for i in range(total_items)]
    departures: list[float] = []
    prev_departure = 0.0
    for arrival in arrival_times:
        start_service = max(arrival, prev_departure)
        finish = start_service + consumer_period_s
        departures.append(finish)
        prev_departure = finish

    return TransferResult(
        total_items=total_items,
        drained=total_items,
        finished=True,
        finish_time_s=departures[-1] if departures else 0.0,
        departure_times_s=departures,
    )


def main() -> int:  # pragma: no cover - manual/CLI use only
    print("== Bug #1: model KHONG duoc Start ==")
    r = simulate_bridge_transfer(n_lines=20, producer_period_s=0.030, model_started=False)
    print(f"  drained={r.drained}/{r.total_items}  finished={r.finished}  "
          f"-> HMI se thay 'da mo MATLAB' nhung khong co frame nao tra ve.")

    print("== Bug #1 da va: model duoc Start ==")
    r = simulate_bridge_transfer(n_lines=20, producer_period_s=0.030, model_started=True)
    print(f"  drained={r.drained}/{r.total_items}  finished={r.finished}  "
          f"finish_time={r.finish_time_s:.3f}s")

    print("== Bug #2: .env cu (0.500s/dong), 100 dong G-code ==")
    slow = simulate_bridge_transfer(n_lines=100, producer_period_s=0.500, model_started=True)
    print(f"  finish_time={slow.finish_time_s:.3f}s (bridge tu lam cham, khong lien quan Simulink)")

    print("== Bug #2 da va: .env moi (0.030s/dong), 100 dong G-code ==")
    fast = simulate_bridge_transfer(n_lines=100, producer_period_s=0.030, model_started=True)
    print(f"  finish_time={fast.finish_time_s:.3f}s (~bang nhip that cua model = {CONSUMER_PERIOD_S:.5f}s/dong)")

    print(f"== Speedup: {slow.finish_time_s / fast.finish_time_s:.2f}x ==")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

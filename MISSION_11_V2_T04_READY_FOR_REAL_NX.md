# Mission 11 V2 — T04 Ready for Real NX Verification

Status: `READY_FOR_REAL_NX`  
Evidence level reached here: `L2`  
Required to complete T04: `L4 real NX MCD Connection_0 capture`

Implemented:

- `tools/mission11_v2_t04_nx_calibration.py`
- `scripts/RUN_T04_NX_MCD_CALIBRATION.ps1`
- `agentic_execution_kit/MISSION_11_V2_T04/README_REAL_NX_CALIBRATION.md`
- `integration_tests/test_mission11_v2_t04_nx_calibration.py`

The tool sends only the documented 96-byte command frame to the NX virtual model and captures the 100-byte feedback stream on localhost port 6001. It does not connect to FluidNC or physical CNC hardware.

T04 remains incomplete until a real capture returns `CONFIRMED_BIG` or `CONFIRMED_LITTLE`, decoded positions match a known pose, and the raw capture/timing evidence is reviewed.


Real capture result: big-endian and 100-byte framing confirmed; collision mapping and final settling remain incomplete.

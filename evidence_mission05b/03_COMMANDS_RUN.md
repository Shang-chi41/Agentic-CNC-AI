# Commands Run

```text
python -m compileall edge_backend cloud_backend
node --check frontend/js/monitor.js
node --check frontend/js/control.js
node --check /tmp/base_inline_0.mjs
python -m pytest integration_tests -q
```

Results: all PASS in sandbox. Real MATLAB/NX/FluidNC not executed.

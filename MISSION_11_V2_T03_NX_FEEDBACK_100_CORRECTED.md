# Mission 11 V2 — T03 NX Feedback 100-byte Corrected

Real NX MCD evidence supersedes the earlier 97-byte assumption.

```text
Edge → NX: 96 bytes, big-endian 12 LREAL
NX → Edge: 100 bytes, big-endian 12 LREAL + 4 trailing status bytes
TCP: full-duplex 127.0.0.1:6001
```

The production parser keeps a persistent byte buffer and handles partial and multiple frames. The low nibble of trailing byte 0 is retained as the legacy X/Y/Z/tool mask, while any non-zero unverified trailing byte fails closed. Exact per-signal collision-byte mapping still requires one-signal-at-a-time NX capture.

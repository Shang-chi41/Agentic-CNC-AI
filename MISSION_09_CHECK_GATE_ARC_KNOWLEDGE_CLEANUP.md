# Mission 09 Cleanup and Security

Excluded from final packages:

```text
.env
.venv/
.pytest_cache/
__pycache__/
*.pyc
*.pyo
application runtime logs outside Mission 09 evidence
```

The temporary sandbox `.env` is test-only and is never packaged. No API key, password, JWT, or token is included.

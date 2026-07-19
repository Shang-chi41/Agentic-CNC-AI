# Mission 07 Cleanup

## Excluded from full ZIP

```text
.env
.venv/
.pytest_cache/
__pycache__/
*.pyc
*.pyo
```

## Secret handling

- `.env` is excluded.
- Reports contain no secret values.
- JWT is accepted only as a runtime environment variable/argument.
- API call testing is opt-in.

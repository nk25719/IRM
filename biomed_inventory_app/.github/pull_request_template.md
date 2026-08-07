## Summary

- 

## Validation

- [ ] `python -m compileall app alembic tests`
- [ ] `python -m unittest discover -v`
- [ ] Routes touched were checked directly

## Risk

- [ ] Database migration included or not needed
- [ ] Permissions/auth behavior preserved
- [ ] Generated files are not committed unless intentionally required for deployment

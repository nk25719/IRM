# Staged CI Migration

CI is intentionally split while the application moves from legacy SQLite paths to PostgreSQL/SQLAlchemy.

| Job | Blocking? | Command | Purpose |
| --- | ---: | --- | --- |
| Unit tests | Yes | `python -m unittest discover -s tests/unit -v` | Business and static checks without a database |
| Static/frontend checks | Yes | PM frontend build plus static layout tests | JS build and route/layout regressions |
| PostgreSQL integration | Yes | `alembic upgrade head` then `python -m unittest discover -s tests/postgres -v` | Target architecture |
| Legacy compatibility debt | No, temporarily | `python -m unittest discover -s tests -v` | Shows remaining SQLite-dependent migration work |

The legacy job is non-blocking only while tracked migration issues remain. It becomes blocking when expected failures reach zero, then migrated tests should move into `tests/unit` or `tests/postgres`.

Migration issue titles are listed in `docs/testing/legacy-migration-issue-tracker.md` until they can be created in GitHub and linked directly.

Rules for new tests:

- Put no-database tests in `tests/unit`.
- Put database integration tests in `tests/postgres`.
- Do not create `.db` files in new tests.
- Do not import `sqlite3` in new tests.

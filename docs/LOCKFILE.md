# Dependency Lock Files

This project pins its full transitive dependency graph in two lock files:

- `requirements.lock` — production dependencies (compiled from `requirements.txt`)
- `requirements-dev.lock` — production + dev dependencies (compiled from `requirements.txt` and `requirements-dev.txt`)

Both are generated with [`pip-tools`](https://github.com/jazzband/pip-tools) using `--generate-hashes` and `--allow-unsafe`. They are checked into git and must be kept in sync with the source `requirements*.txt` files.

## Why lock?

- **Reproducibility** — the same commit always installs the exact same package versions, regardless of when or where it is built.
- **CI determinism** — test runs cannot silently break because a transitive dependency released a new version overnight.
- **Security audit** — every wheel is verified against a SHA-256 hash, blocking tampered packages and supply-chain surprises.
- **Debuggable upgrades** — lock diffs make it obvious which packages moved when a bug appears after an upgrade.

## Workflow

1. Edit `requirements.txt` (or `requirements-dev.txt`) to add, remove, or bump a top-level package.
2. Re-compile both lock files:
   ```bash
   pip-compile --generate-hashes --allow-unsafe \
     --output-file=requirements.lock requirements.txt
   pip-compile --generate-hashes --allow-unsafe \
     --output-file=requirements-dev.lock requirements.txt requirements-dev.txt
   ```
   On Windows without `pip-compile` on PATH, use `python -m piptools compile ...`.
3. Commit the changed `requirements*.txt` **and** `requirements*.lock` together in the same commit.

## Installing from a lock file

```bash
# Production (runtime) only
pip install -r requirements.lock

# Development (includes prod)
pip install -r requirements-dev.lock
```

Hash-checking mode is enabled automatically when the file contains `--hash=` entries.

## Upgrading

```bash
# Upgrade a single package (and its transitive closure)
pip-compile --upgrade-package numpy \
  --generate-hashes --allow-unsafe \
  --output-file=requirements.lock requirements.txt

# Upgrade everything to the latest versions allowed by requirements.txt
pip-compile --upgrade \
  --generate-hashes --allow-unsafe \
  --output-file=requirements.lock requirements.txt
```

Repeat for `requirements-dev.lock` afterwards so both files stay consistent.

## CI integration

CI and Docker builds should install from the lock file, **not** from `requirements.txt`:

```dockerfile
RUN pip install --no-deps --require-hashes -r requirements.lock
```

This guarantees byte-identical environments across developer machines, CI runners, and production images.

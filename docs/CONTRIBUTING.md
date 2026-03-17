# Contributing to pymfx

## Setup

```bash
git clone https://github.com/jabahm/pymfx
cd pymfx
pip install -e ".[dev]"
```

## Run tests

```bash
pytest                        # run all tests
pytest --cov=pymfx            # with coverage
```

## Code style

```bash
ruff check pymfx/             # lint
ruff format pymfx/            # format
```

## Publish to PyPI

```bash
# 1. Bump version in pyproject.toml and CHANGELOG.md
# 2. Build
python -m build

# 3. Check the distribution
twine check dist/*

# 4. Upload to TestPyPI first
twine upload --repository testpypi dist/*

# 5. Install from TestPyPI and verify
pip install --index-url https://test.pypi.org/simple/ pymfx

# 6. Upload to PyPI
twine upload dist/*
```

## Adding a converter

Create a new module under `pymfx/converters/<format>.py` with:

```python
def from_<format>(source) -> MfxFile:
    ...
```

And expose it in `pymfx/converters/__init__.py`.

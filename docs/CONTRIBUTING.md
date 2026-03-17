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


## Adding a converter

Create a new module under `pymfx/converters/<format>.py` with:

```python
def from_<format>(source) -> MfxFile:
    ...
```

And expose it in `pymfx/converters/__init__.py`.

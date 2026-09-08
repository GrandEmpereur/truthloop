"""truthloop: deterministic retrieval-evaluation harness."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("truthloop")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = ["__version__"]

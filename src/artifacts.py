"""Publish complete output bundles without silently replacing earlier runs."""

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator


@contextmanager
def new_output_bundle(destination: Path) -> Iterator[Path]:
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(
            f"Output already exists: {destination}. Choose a new --output folder; "
            "earlier runs are not overwritten."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{destination.name}-", dir=destination.parent
    ) as temporary:
        staging = Path(temporary)
        yield staging
        if destination.exists():
            raise FileExistsError(f"Output appeared during execution: {destination}")
        staging.rename(destination)


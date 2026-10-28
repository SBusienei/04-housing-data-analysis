"""Catch source-shape problems before any database snapshot is touched."""

from pathlib import Path

import pytest

from src.csv_source import COLUMNS, SourceDataError, iter_source_rows, validate_source
from tests.conftest import CsvFactory


def test_valid_source_is_unchanged(
    booking: dict[str, str], csv_factory: CsvFactory
) -> None:
    source = csv_factory([booking])
    before = source.read_bytes()
    count, checksum = validate_source(source)
    assert count == 1
    assert len(checksum) == 64
    assert source.read_bytes() == before
    assert list(iter_source_rows(source)) == [
        (2, [booking[column] for column in COLUMNS])
    ]


def test_empty_source_is_rejected(csv_factory: CsvFactory) -> None:
    with pytest.raises(SourceDataError, match="no booking records"):
        validate_source(csv_factory([]))


def test_incorrect_header_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "incorrect.csv"
    source.write_text("hotel,is_canceled\nCity Hotel,0\n", encoding="utf-8")
    with pytest.raises(SourceDataError, match="headers"):
        validate_source(source)


def test_missing_fields_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "short.csv"
    source.write_text(",".join(COLUMNS) + "\nCity Hotel,0\n", encoding="utf-8")
    with pytest.raises(SourceDataError, match="record 2"):
        validate_source(source)


def test_nul_is_rejected(booking: dict[str, str], csv_factory: CsvFactory) -> None:
    with pytest.raises(SourceDataError, match="NUL"):
        validate_source(csv_factory([{**booking, "hotel": "City\x00Hotel"}]))


def test_bom_and_quoted_newlines_are_supported(
    booking: dict[str, str], csv_factory: CsvFactory
) -> None:
    source = csv_factory([{**booking, "meal": "quoted,\nvalue"}, booking])
    source.write_bytes(b"\xef\xbb\xbf" + source.read_bytes())
    assert validate_source(source)[0] == 2
    rows = list(iter_source_rows(source))
    assert [number for number, _ in rows] == [2, 3]
    assert rows[0][1][COLUMNS.index("meal")] == "quoted,\nvalue"


def test_bad_encoding_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "bad_encoding.csv"
    source.write_bytes(b"\xff\xfe")
    with pytest.raises(SourceDataError, match="decoding/parsing"):
        validate_source(source)


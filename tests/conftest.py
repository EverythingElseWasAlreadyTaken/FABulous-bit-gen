"""Shared fixtures for fabulous_bit_gen tests."""

import pickle
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fasm import FasmLine, SetFasmFeature


@pytest.fixture
def minimal_spec_dict() -> dict[str, Any]:
    """Minimal spec dict for unit tests.

    Tiles: X0Y0 (NULL - bottom), X0Y1 (W_IO), X1Y1 (LUT4AB), X0Y2 (NULL - top)

    Note: The bitstream generation skips Y0 (bottom) and Y{max} (top) rows.
    So we need tiles at Y2 to ensure Y1 gets processed.
    """
    MaxFramesPerCol = 20
    FrameBitsPerRow = 32

    return {
        "ArchSpecs": {
            "MaxFramesPerCol": MaxFramesPerCol,
            "FrameBitsPerRow": FrameBitsPerRow,
        },
        "TileMap": {
            "X0Y0": "NULL",
            "X0Y1": "W_IO",
            "X1Y1": "LUT4AB",
            "X0Y2": "NULL",
            "X1Y2": "NULL",
        },
        "TileSpecs": {
            "X0Y1": {
                "W2MID7.A_I": {110: "1", 111: "0"},
                "GND0.A_T": {50: "1"},
            },
            "X1Y1": {
                "LUT4.INIT": {0: "1", 1: "0", 2: "1", 3: "0"},
                "LUT4.MODE": {100: "1"},
            },
            "X0Y0": {},
            "X0Y2": {},
            "X1Y2": {},
        },
        "TileSpecs_No_Mask": {
            "X0Y1": {
                "W2MID7.A_I": {110: "1", 111: "0"},
                "GND0.A_T": {50: "1"},
            },
            "X1Y1": {
                "LUT4.INIT": {0: "1", 1: "0", 2: "1", 3: "0"},
                "LUT4.MODE": {100: "1"},
            },
            "X0Y0": {},
            "X0Y2": {},
            "X1Y2": {},
        },
        "FrameMap": {
            "NULL": {},
            "W_IO": {0: "11111111111111111111111111111111"},
            "LUT4AB": {0: "00000001111111111111111111111011"},
        },
        "FrameMapEncode": {},
    }


@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    """Temporary directory for test outputs, auto-cleanup after test."""
    return tmp_path


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Path to tracked test data directory (small design files)."""
    return Path(__file__).parent / "test_data"


@pytest.fixture(scope="session")
def model_files_dir() -> Path:
    """Path to gitignored model files directory (large binaries, fabric specs)."""
    return Path(__file__).parent / "test_data" / "model_files"


@pytest.fixture(scope="session")
def real_spec_dict(model_files_dir: Path) -> dict[str, Any]:
    """Load real bitstream spec from model files (shared across all designs)."""
    spec_file = model_files_dir / "bitStreamSpec.bin"
    with spec_file.open("rb") as f:
        return pickle.load(f)


_DESIGNS = [
    "sequential_16bit_en",
    "bouncy_spi_screen_standard_fab",
    "bouncy_spi_screen_complex_dff_fab",
]


@pytest.fixture(scope="session", params=_DESIGNS)
def design(request: pytest.FixtureRequest, test_data_dir: Path) -> SimpleNamespace:
    """Parametrized fixture yielding paths for each test design.

    Yields a SimpleNamespace with:
      - name        : design directory name
      - fasm_path   : Path to the input FASM file
      - reference   : SimpleNamespace with paths to reference outputs
                      (.bin, .csv, .vh, .vhd); .hex only for bouncy designs
    """
    name = request.param
    d = test_data_dir / name
    ref = d / "reference"
    return SimpleNamespace(
        name=name,
        fasm_path=d / "top.fasm",
        reference=SimpleNamespace(
            bin=ref / "top.bin",
            csv=ref / "top.csv",
            vh=ref / "top.vh",
            vhd=ref / "top.vhd",
        ),
    )


@pytest.fixture
def synthetic_fasm_lines() -> list[FasmLine]:
    """Synthetic FASM lines for unit testing.

    Returns list of FasmLine objects with set_features.
    """
    return [
        FasmLine(
            set_feature=SetFasmFeature(
                feature="X0Y1.W2MID7.A_I",
                start=None,
                end=None,
                value=1,
                value_format=None,
            ),
            annotations=None,
            comment=None,
        ),
        FasmLine(
            set_feature=SetFasmFeature(
                feature="X0Y1.GND0.A_T",
                start=None,
                end=None,
                value=1,
                value_format=None,
            ),
            annotations=None,
            comment=None,
        ),
        FasmLine(
            set_feature=SetFasmFeature(
                feature="X1Y1.LUT4.INIT",
                start=None,
                end=None,
                value=1,
                value_format=None,
            ),
            annotations=None,
            comment=None,
        ),
    ]


@pytest.fixture
def synthetic_fasm_lines_with_clk() -> list[FasmLine]:
    """FASM lines including CLK feature (should be filtered)."""
    return [
        FasmLine(
            set_feature=SetFasmFeature(
                feature="X0Y1.W2MID7.A_I",
                start=None,
                end=None,
                value=1,
                value_format=None,
            ),
            annotations=None,
            comment=None,
        ),
        FasmLine(
            set_feature=SetFasmFeature(
                feature="X0Y1.CLK.some_feature",
                start=None,
                end=None,
                value=1,
                value_format=None,
            ),
            annotations=None,
            comment=None,
        ),
    ]


@pytest.fixture
def synthetic_fasm_lines_invalid_tile() -> list[FasmLine]:
    """FASM lines with invalid tile location."""
    return [
        FasmLine(
            set_feature=SetFasmFeature(
                feature="X99Y99.W2MID7.A_I",
                start=None,
                end=None,
                value=1,
                value_format=None,
            ),
            annotations=None,
            comment=None,
        ),
    ]

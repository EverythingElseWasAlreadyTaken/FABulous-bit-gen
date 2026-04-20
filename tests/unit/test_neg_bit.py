"""Unit tests for fabulous_neg_bit helper functions."""

import math
import struct
from typing import Any

import pytest

from fabulous_neg_bit.neg_bit import (
    DESYNC_WORD,
    MAX_FRAMES_PER_COL,
    SYNC_HEADER_HEX,
    _compute_grid_size,
    _parse_bel_spec,
    _parse_binary_bitstream,
    _reconstruct_tile_bits,
    _recover_fasm_features,
    negBitstream,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _frame_select_word(col: int, frame_idx: int) -> bytes:
    """Build the 4-byte frame-select word for a given (col, frame_idx)."""
    word = (col << 27) | (1 << frame_idx)
    return struct.pack(">I", word)


def _make_bitstream(
    frames: list[tuple[int, int, bytes]],
) -> bytes:
    """Assemble a minimal FABulous bitstream from a list of (col, frame_idx, data)."""
    data = bytes.fromhex(SYNC_HEADER_HEX)
    for col, frame_idx, frame_data in frames:
        data += _frame_select_word(col, frame_idx)
        data += frame_data
    data += struct.pack(">I", DESYNC_WORD)
    return data


# ── _compute_grid_size ────────────────────────────────────────────────────────


class TestComputeGridSize:
    def test_single_tile(self) -> None:
        result = _compute_grid_size({"X0Y0": "NULL"})
        assert result == (1, 1)

    def test_2x2_grid(self) -> None:
        tile_map = {"X0Y0": "NULL", "X0Y1": "NULL", "X1Y0": "NULL", "X1Y1": "LUT4AB"}
        assert _compute_grid_size(tile_map) == (2, 2)

    def test_non_square_grid(self) -> None:
        tile_map = {f"X{x}Y{y}": "NULL" for x in range(3) for y in range(5)}
        assert _compute_grid_size(tile_map) == (3, 5)

    def test_uses_minimal_spec_dict(self, minimal_spec_dict: dict[str, Any]) -> None:
        cols, rows = _compute_grid_size(minimal_spec_dict["TileMap"])
        assert cols == 2
        assert rows == 3

    def test_sparse_keys_give_correct_max(self) -> None:
        tile_map = {"X0Y0": "NULL", "X4Y7": "NULL"}
        assert _compute_grid_size(tile_map) == (5, 8)

    def test_non_matching_keys_skipped(self) -> None:
        tile_map = {"X0Y0": "NULL", "INVALID": "NULL"}
        cols, rows = _compute_grid_size(tile_map)
        assert cols == 1
        assert rows == 1


# ── _parse_binary_bitstream ───────────────────────────────────────────────────


class TestParseBinaryBitstream:
    def test_empty_bitstream_after_desync(self) -> None:
        data = _make_bitstream([])
        result = _parse_binary_bitstream(data, frame_data_size=4)
        assert result == {}

    def test_single_frame(self) -> None:
        frame_data = b"\x00\x00\x00\x01"
        data = _make_bitstream([(0, 0, frame_data)])
        result = _parse_binary_bitstream(data, frame_data_size=4)
        assert (0, 0) in result
        assert result[(0, 0)] == frame_data

    def test_two_frames_same_column(self) -> None:
        fd0 = b"\x01\x00\x00\x00"
        fd1 = b"\x00\x02\x00\x00"
        data = _make_bitstream([(0, 0, fd0), (0, 1, fd1)])
        result = _parse_binary_bitstream(data, frame_data_size=4)
        assert result[(0, 0)] == fd0
        assert result[(0, 1)] == fd1

    def test_two_columns(self) -> None:
        fd_col0 = b"\xaa\xbb\xcc\xdd"
        fd_col1 = b"\x11\x22\x33\x44"
        data = _make_bitstream([(0, 3, fd_col0), (1, 5, fd_col1)])
        result = _parse_binary_bitstream(data, frame_data_size=4)
        assert result[(0, 3)] == fd_col0
        assert result[(1, 5)] == fd_col1

    def test_all_20_frame_indices(self) -> None:
        frame_data_size = 4
        frames = [(0, i, bytes([i, 0, 0, 0])) for i in range(MAX_FRAMES_PER_COL)]
        data = _make_bitstream(frames)
        result = _parse_binary_bitstream(data, frame_data_size=frame_data_size)
        assert len(result) == MAX_FRAMES_PER_COL
        for i in range(MAX_FRAMES_PER_COL):
            assert (0, i) in result

    def test_raises_on_wrong_sync_header(self) -> None:
        data = b"\x00" * 20 + struct.pack(">I", DESYNC_WORD)
        with pytest.raises(ValueError, match="sync header"):
            _parse_binary_bitstream(data, frame_data_size=4)

    def test_frame_select_word_encoding(self) -> None:
        # col=3, frame_idx=7 → word = (3 << 27) | (1 << 7) = 0x18000080
        col, frame_idx = 3, 7
        frame_data = b"\xff" * 8
        data = _make_bitstream([(col, frame_idx, frame_data)])
        result = _parse_binary_bitstream(data, frame_data_size=8)
        assert (col, frame_idx) in result
        assert result[(col, frame_idx)] == frame_data


# ── _reconstruct_tile_bits ────────────────────────────────────────────────────


class TestReconstructTileBits:
    def test_all_zero_frame_gives_all_zero_bits(
        self, minimal_spec_dict: dict[str, Any]
    ) -> None:
        # Frame data is all zeros → all tile bits remain 0
        frame_bits_per_row = minimal_spec_dict["ArchSpecs"]["FrameBitsPerRow"]
        bytes_per_row = math.ceil(frame_bits_per_row / 8)
        frame_data = b"\x00" * bytes_per_row
        frame_map = {(0, 0): frame_data}
        tile_bits = _reconstruct_tile_bits(frame_map, minimal_spec_dict, 3, 2)
        # X0Y1 is the only interior row (Y0 and Y2 are border rows)
        assert tile_bits["X0Y1"] == [0] * (
            frame_bits_per_row * minimal_spec_dict["ArchSpecs"]["MaxFramesPerCol"]
        )

    def test_bit_zero_set_at_position_zero(
        self, minimal_spec_dict: dict[str, Any]
    ) -> None:
        # Set bit index 0 of X0Y1 by encoding it through the frame packing:
        # tile_bits[0] = 1 → after [::-1] encoding: last bit = 1 → 0x00000001
        frame_bits_per_row = minimal_spec_dict["ArchSpecs"]["FrameBitsPerRow"]
        bytes_per_row = math.ceil(frame_bits_per_row / 8)
        # Bit 0 of tile_bits corresponds to bit position 0 in frame_bit_row
        # which after [::-1] is the last char → packed as 0x00000001 (big endian)
        frame_data = (1).to_bytes(bytes_per_row, "big")
        frame_map = {(0, 0): frame_data}
        tile_bits = _reconstruct_tile_bits(frame_map, minimal_spec_dict, 3, 2)
        assert tile_bits["X0Y1"][0] == 1
        assert tile_bits["X0Y1"][1] == 0

    def test_interior_rows_only_without_border_rows(
        self, minimal_spec_dict: dict[str, Any]
    ) -> None:
        frame_bits_per_row = minimal_spec_dict["ArchSpecs"]["FrameBitsPerRow"]
        bytes_per_row = math.ceil(frame_bits_per_row / 8)
        frame_map = {(0, 0): b"\x00" * bytes_per_row}
        tile_bits = _reconstruct_tile_bits(frame_map, minimal_spec_dict, 3, 2)
        # Y0 and Y2 are border rows, excluded by default
        assert "X0Y0" not in tile_bits
        assert "X0Y2" not in tile_bits
        assert "X0Y1" in tile_bits

    def test_frame_idx_offset(self, minimal_spec_dict: dict[str, Any]) -> None:
        # frame_idx=1 → bits at positions FrameBitsPerRow..2*FrameBitsPerRow-1
        frame_bits_per_row = minimal_spec_dict["ArchSpecs"]["FrameBitsPerRow"]
        bytes_per_row = math.ceil(frame_bits_per_row / 8)
        # Set bit 0 (of the second frame slice) via frame_idx=1
        frame_data = (1).to_bytes(bytes_per_row, "big")
        frame_map = {(0, 1): frame_data}
        tile_bits = _reconstruct_tile_bits(frame_map, minimal_spec_dict, 3, 2)
        offset = frame_bits_per_row * 1
        assert tile_bits["X0Y1"][offset] == 1
        assert tile_bits["X0Y1"][offset - 1] == 0


# ── _recover_fasm_features ────────────────────────────────────────────────────


class TestRecoverFasmFeatures:
    def _make_tile_bits(
        self, spec_dict: dict[str, Any], updates: dict[str, dict[int, int]]
    ) -> dict[str, list[int]]:
        """Build tile_bits with specific bit overrides."""
        frame_bits_per_row = spec_dict["ArchSpecs"]["FrameBitsPerRow"]
        max_frames = spec_dict["ArchSpecs"]["MaxFramesPerCol"]
        total = frame_bits_per_row * max_frames
        tile_bits: dict[str, list[int]] = {
            loc: [0] * total for loc in spec_dict["TileSpecs"]
        }
        for tile_loc, bit_updates in updates.items():
            for idx, val in bit_updates.items():
                tile_bits[tile_loc][idx] = val
        return tile_bits

    def test_no_bits_set_recovers_nothing(
        self, minimal_spec_dict: dict[str, Any]
    ) -> None:
        tile_bits = self._make_tile_bits(minimal_spec_dict, {})
        features = _recover_fasm_features(tile_bits, minimal_spec_dict)
        assert features == []

    def test_single_feature_recovered(self, minimal_spec_dict: dict[str, Any]) -> None:
        # GND0.A_T requires bit 50 = "1"
        tile_bits = self._make_tile_bits(minimal_spec_dict, {"X0Y1": {50: 1}})
        features = _recover_fasm_features(tile_bits, minimal_spec_dict)
        assert "X0Y1.GND0.A_T" in features

    def test_feature_not_recovered_when_bit_unset(
        self, minimal_spec_dict: dict[str, Any]
    ) -> None:
        tile_bits = self._make_tile_bits(minimal_spec_dict, {})
        features = _recover_fasm_features(tile_bits, minimal_spec_dict)
        assert "X0Y1.GND0.A_T" not in features

    def test_multi_bit_feature_all_must_match(
        self, minimal_spec_dict: dict[str, Any]
    ) -> None:
        # W2MID7.A_I requires bit 110 = "1" AND bit 111 = "0"
        # With only bit 110 set (bit 111 defaults to 0) → feature is active
        tile_bits = self._make_tile_bits(minimal_spec_dict, {"X0Y1": {110: 1}})
        features = _recover_fasm_features(tile_bits, minimal_spec_dict)
        assert "X0Y1.W2MID7.A_I" in features

    def test_multi_bit_feature_fails_when_one_bit_wrong(
        self, minimal_spec_dict: dict[str, Any]
    ) -> None:
        # W2MID7.A_I: bit 110="1", bit 111="0"
        # Set both bits to 1 → bit 111 should be 0, so feature does NOT match
        tile_bits = self._make_tile_bits(minimal_spec_dict, {"X0Y1": {110: 1, 111: 1}})
        features = _recover_fasm_features(tile_bits, minimal_spec_dict)
        assert "X0Y1.W2MID7.A_I" not in features

    def test_multiple_features_recovered_independently(
        self, minimal_spec_dict: dict[str, Any]
    ) -> None:
        tile_bits = self._make_tile_bits(
            minimal_spec_dict, {"X0Y1": {50: 1}, "X1Y1": {100: 1}}
        )
        features = _recover_fasm_features(tile_bits, minimal_spec_dict)
        assert "X0Y1.GND0.A_T" in features
        assert "X1Y1.LUT4.MODE" in features

    def test_tiles_not_in_tile_bits_are_skipped(
        self, minimal_spec_dict: dict[str, Any]
    ) -> None:
        # Pass empty tile_bits (no tiles present) → nothing recovered
        features = _recover_fasm_features({}, minimal_spec_dict)
        assert features == []

    def test_all_zero_bit_map_feature_not_recovered(self) -> None:
        spec = {
            "TileSpecs": {
                "X0Y1": {"ALL_ZERO": {0: "0", 1: "0"}},
            }
        }
        tile_bits = {"X0Y1": [0] * 10}
        features = _recover_fasm_features(tile_bits, spec)
        assert features == []

    def test_output_is_sorted(self, minimal_spec_dict: dict[str, Any]) -> None:
        tile_bits = self._make_tile_bits(
            minimal_spec_dict,
            {"X0Y1": {50: 1, 110: 1}, "X1Y1": {0: 1, 2: 1, 100: 1}},
        )
        features = _recover_fasm_features(tile_bits, minimal_spec_dict)
        assert features == sorted(features)


# ── negBitstream (end-to-end with minimal spec) ───────────────────────────────


class TestNegBitstream:
    def _build_spec_file(self, spec_dict: dict, tmp_path: Any) -> str:
        import pickle

        spec_file = tmp_path / "spec.bin"
        with spec_file.open("wb") as f:
            pickle.dump(spec_dict, f)
        return str(spec_file)

    def test_all_zero_bitstream_recovers_nothing(
        self, minimal_spec_dict: dict[str, Any], tmp_path: Any
    ) -> None:
        spec_file = self._build_spec_file(minimal_spec_dict, tmp_path)

        frame_bits_per_row = minimal_spec_dict["ArchSpecs"]["FrameBitsPerRow"]
        bytes_per_row = math.ceil(frame_bits_per_row / 8)
        # num_interior_rows = 3 - 2 = 1 (minimal_spec_dict has 3 rows, no border rows)
        frame_data_size = 1 * bytes_per_row
        frames = [
            (col, fi, b"\x00" * frame_data_size)
            for col in range(2)
            for fi in range(MAX_FRAMES_PER_COL)
        ]
        bitstream_data = _make_bitstream(frames)
        bitstream_file = tmp_path / "top.bin"
        bitstream_file.write_bytes(bitstream_data)

        output_fasm = tmp_path / "recovered.fasm"
        negBitstream(spec_file, str(bitstream_file), str(output_fasm))

        content = output_fasm.read_text()
        assert content.strip() == ""

    def test_raises_on_missing_spec(self, tmp_path: Any) -> None:
        with pytest.raises(FileNotFoundError):
            negBitstream(
                str(tmp_path / "nonexistent.bin"),
                str(tmp_path / "top.bin"),
                str(tmp_path / "out.fasm"),
            )

    def test_raises_on_bad_sync_header(
        self, minimal_spec_dict: dict[str, Any], tmp_path: Any
    ) -> None:
        spec_file = self._build_spec_file(minimal_spec_dict, tmp_path)
        bad_bitstream = tmp_path / "bad.bin"
        bad_bitstream.write_bytes(b"\x00" * 24)
        with pytest.raises(ValueError, match="sync header"):
            negBitstream(spec_file, str(bad_bitstream), str(tmp_path / "out.fasm"))


# ── _parse_bel_spec ───────────────────────────────────────────────────────────


class TestParseBelSpec:
    BEL_FILE = "tests/test_data/model_files/bel.v2.txt"

    def test_returns_dict(self) -> None:
        result = _parse_bel_spec(self.BEL_FILE)
        assert isinstance(result, dict)

    def test_fabulous_lc_init_group_present(self) -> None:
        result = _parse_bel_spec(self.BEL_FILE)
        # X1Y1 has FABULOUS_LC BELs A-H; each has an INIT vector group
        key = ("X1Y1", "A", "INIT")
        assert key in result

    def test_init_group_has_16_entries(self) -> None:
        result = _parse_bel_spec(self.BEL_FILE)
        group = result[("X1Y1", "A", "INIT")]
        assert len(group) == 16
        assert set(group.keys()) == set(range(16))

    def test_init_zero_uses_bare_name(self) -> None:
        # Unindexed "INIT" maps to TileSpecs key "A.INIT", not "A.INIT[0]"
        result = _parse_bel_spec(self.BEL_FILE)
        group = result[("X1Y1", "A", "INIT")]
        assert group[0] == "A.INIT"

    def test_init_indexed_entries_use_bracket_name(self) -> None:
        result = _parse_bel_spec(self.BEL_FILE)
        group = result[("X1Y1", "A", "INIT")]
        for idx in range(1, 16):
            assert group[idx] == f"A.INIT[{idx}]"

    def test_scalar_cfg_fields_not_in_result(self) -> None:
        # FF, IOmux, SET_NORESET are scalar — must NOT appear as vector groups
        result = _parse_bel_spec(self.BEL_FILE)
        for key in result:
            assert key[2] not in {"FF", "IOmux", "SET_NORESET"}

    def test_multiple_tiles_have_groups(self) -> None:
        result = _parse_bel_spec(self.BEL_FILE)
        tiles_with_groups = {k[0] for k in result}
        # There are many FABULOUS_LC tiles beyond X1Y1
        assert len(tiles_with_groups) > 5

    def test_raises_on_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            _parse_bel_spec("/nonexistent/bel.v2.txt")


# ── _recover_fasm_features with bel_vectors ───────────────────────────────────


class TestRecoverFasmFeaturesWithVectors:
    """Test _recover_fasm_features when bel_vectors are provided."""

    BEL_FILE = "tests/test_data/model_files/bel.v2.txt"

    def _spec_with_init(self) -> dict:
        """Minimal spec dict with a single INIT vector BEL at X1Y1."""
        # Mirror TileSpecs structure: each INIT[n] is one bit with value "1"
        # Use bit indices 0..15 for simplicity
        tile_specs: dict = {
            "X1Y1": {
                "A.INIT": {0: "1"},
                "A.INIT[1]": {1: "1"},
                "A.INIT[2]": {2: "1"},
                "A.INIT[3]": {3: "1"},
                "A.INIT[4]": {4: "1"},
                "A.INIT[5]": {5: "1"},
                "A.INIT[6]": {6: "1"},
                "A.INIT[7]": {7: "1"},
                "A.INIT[8]": {8: "1"},
                "A.INIT[9]": {9: "1"},
                "A.INIT[10]": {10: "1"},
                "A.INIT[11]": {11: "1"},
                "A.INIT[12]": {12: "1"},
                "A.INIT[13]": {13: "1"},
                "A.INIT[14]": {14: "1"},
                "A.INIT[15]": {15: "1"},
                "A.FF": {16: "1"},
            },
            "X0Y0": {},
            "X0Y2": {},
        }
        return {"TileSpecs": tile_specs}

    def _bel_vectors_for_spec(self) -> dict:
        """Minimal BelVectors matching _spec_with_init."""
        return {
            ("X1Y1", "A", "INIT"): {
                0: "A.INIT",
                1: "A.INIT[1]",
                2: "A.INIT[2]",
                3: "A.INIT[3]",
                4: "A.INIT[4]",
                5: "A.INIT[5]",
                6: "A.INIT[6]",
                7: "A.INIT[7]",
                8: "A.INIT[8]",
                9: "A.INIT[9]",
                10: "A.INIT[10]",
                11: "A.INIT[11]",
                12: "A.INIT[12]",
                13: "A.INIT[13]",
                14: "A.INIT[14]",
                15: "A.INIT[15]",
            }
        }

    def test_vector_emitted_when_any_bit_set(self) -> None:
        spec = self._spec_with_init()
        bvecs = self._bel_vectors_for_spec()
        # Set only INIT[0] (bit index 0)
        tile_bits = {"X1Y1": [0] * 640, "X0Y0": [0] * 640, "X0Y2": [0] * 640}
        tile_bits["X1Y1"][0] = 1
        features = _recover_fasm_features(tile_bits, spec, bel_vectors=bvecs)
        vector_lines = [f for f in features if "INIT[15:0]" in f]
        assert len(vector_lines) == 1
        assert vector_lines[0] == "X1Y1.A.INIT[15:0] = 16'b0000000000000001"

    def test_vector_bit_order_msb_first(self) -> None:
        spec = self._spec_with_init()
        bvecs = self._bel_vectors_for_spec()
        # Set INIT[15] only
        tile_bits = {"X1Y1": [0] * 640, "X0Y0": [0] * 640, "X0Y2": [0] * 640}
        tile_bits["X1Y1"][15] = 1
        features = _recover_fasm_features(tile_bits, spec, bel_vectors=bvecs)
        vector_lines = [f for f in features if "INIT[15:0]" in f]
        assert vector_lines[0] == "X1Y1.A.INIT[15:0] = 16'b1000000000000000"

    def test_all_zero_vector_not_emitted(self) -> None:
        spec = self._spec_with_init()
        bvecs = self._bel_vectors_for_spec()
        tile_bits = {"X1Y1": [0] * 640, "X0Y0": [0] * 640, "X0Y2": [0] * 640}
        features = _recover_fasm_features(tile_bits, spec, bel_vectors=bvecs)
        assert not any("INIT" in f for f in features)

    def test_individual_init_bits_not_emitted_as_scalars(self) -> None:
        spec = self._spec_with_init()
        bvecs = self._bel_vectors_for_spec()
        tile_bits = {"X1Y1": [0] * 640, "X0Y0": [0] * 640, "X0Y2": [0] * 640}
        tile_bits["X1Y1"][3] = 1
        features = _recover_fasm_features(tile_bits, spec, bel_vectors=bvecs)
        # No individual "A.INIT[3]" scalar — only the vector line
        assert not any(f.endswith("A.INIT[3]") for f in features)
        assert any("INIT[15:0]" in f for f in features)

    def test_scalar_ff_still_emitted(self) -> None:
        spec = self._spec_with_init()
        bvecs = self._bel_vectors_for_spec()
        tile_bits = {"X1Y1": [0] * 640, "X0Y0": [0] * 640, "X0Y2": [0] * 640}
        tile_bits["X1Y1"][16] = 1  # A.FF
        features = _recover_fasm_features(tile_bits, spec, bel_vectors=bvecs)
        assert "X1Y1.A.FF" in features

    def test_without_bel_vectors_init_emitted_as_scalars(self) -> None:
        spec = self._spec_with_init()
        tile_bits = {"X1Y1": [0] * 640, "X0Y0": [0] * 640, "X0Y2": [0] * 640}
        tile_bits["X1Y1"][3] = 1
        features = _recover_fasm_features(tile_bits, spec)
        assert "X1Y1.A.INIT[3]" in features
        assert not any("INIT[15:0]" in f for f in features)

"""Tests for genBitstream function with comprehensive mocking."""

import copy
import pickle
import re

import pytest
from fasm import FasmLine, SetFasmFeature

from fabulous_bit_gen.bit_gen import (
    DESYNC_BIT,
    FRAME_BITS_PER_ROW,
    FRAME_SELECT_WIDTH,
    MAX_FRAMES_PER_COL,
    SYNC_HEADER_HEX,
    _resolve_bitstream_format,
    gen_bitstream,
)
from fabulous_bit_gen.custom_exception import SpecMissMatch


class TestGenBitstreamInitialization:
    """Tests for genBitstream initialization."""

    def test_initializes_tile_dicts_with_zeros(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Verify tileDict initialized with zeros for each tile."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_file.write_text("")
        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        assert output_file.with_suffix(".csv").exists()

    def test_grid_dimensions_calculated_correctly(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Test that grid dimensions are extracted from TileMap coordinates."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_file.write_text("")
        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_path = output_file.with_suffix(".csv")
        csv_content = csv_path.read_text()

        coordsRE = re.compile(r"X(\d*)Y(\d*)")
        max_x = 0
        max_y = 0
        for line in csv_content.split("\n"):
            match = coordsRE.match(line)
            if match:
                x = int(match.group(1))
                y = int(match.group(2))
                max_x = max(x, max_x)
                max_y = max(y, max_y)

        assert max_x == 1
        assert max_y == 1


class TestGenBitstreamFasmProcessing:
    """Tests for FASM line processing."""

    def test_clk_feature_filtered_out(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """CLK features should be skipped during processing."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
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
                    feature="X0Y1.CLK.enable",
                    start=None,
                    end=None,
                    value=1,
                    value_format=None,
                ),
                annotations=None,
                comment=None,
            ),
        ]

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string",
            return_value="canonical_string",
        )

        def mock_parse_fasm_string(_s):
            return fasm_lines

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string",
            side_effect=mock_parse_fasm_string,
        )

        def mock_set_feature_to_str(feature):
            return feature.feature

        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=mock_set_feature_to_str,
        )

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_content = output_file.with_suffix(".csv").read_text()
        # Valid feature was processed; CLK feature filtered
        # (would raise SpecMissMatch if not filtered)
        assert "X0Y1" in csv_content

    def test_clk_feature_processed_with_multi_clk_domains(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """With MultiClkDomains enabled, CLK features are applied, not skipped."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        spec = copy.deepcopy(minimal_spec_dict)
        spec["ArchSpecs"]["MultiClkDomains"] = True
        spec["TileSpecs"]["X0Y1"]["CLK.enable"] = {60: "1"}
        spec["TileSpecs_No_Mask"]["X0Y1"]["CLK.enable"] = {60: "1"}

        fasm_lines = [
            FasmLine(
                set_feature=SetFasmFeature(
                    feature="X0Y1.CLK.enable",
                    start=None,
                    end=None,
                    value=1,
                    value_format=None,
                ),
                annotations=None,
                comment=None,
            ),
        ]

        with spec_file.open("wb") as f:
            pickle.dump(spec, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=lambda feature: feature.feature,
        )

        # Bit 60 lives in frame 1 (60 // 32), reversed within its 32-bit row.
        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_content = output_file.with_suffix(".csv").read_text()
        # frame1 row for X0Y1: bit 60 -> index 28 within the frame, reversed.
        frame1_line = next(
            row
            for row in csv_content.splitlines()
            if row.startswith("frame1,") and "X0Y1" not in row
        )
        frame_bits = frame1_line.split(",")[-1]
        assert frame_bits[::-1][28] == "1"

    def test_clk_feature_missing_from_spec_raises_with_multi_clk(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """MultiClkDomains stops filtering, so an unspecced CLK feature errors."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        spec = copy.deepcopy(minimal_spec_dict)
        spec["ArchSpecs"]["MultiClkDomains"] = True

        fasm_lines = [
            FasmLine(
                set_feature=SetFasmFeature(
                    feature="X0Y1.CLK.enable",
                    start=None,
                    end=None,
                    value=1,
                    value_format=None,
                ),
                annotations=None,
                comment=None,
            ),
        ]

        with spec_file.open("wb") as f:
            pickle.dump(spec, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=lambda feature: feature.feature,
        )

        with pytest.raises(SpecMissMatch):
            gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

    def test_valid_feature_sets_bits_in_tile(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Valid features should set bits in tileDict."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
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
        ]

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )

        def mock_set_feature_to_str(feature):
            return feature.feature

        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=mock_set_feature_to_str,
        )

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_path = output_file.with_suffix(".csv")
        assert csv_path.exists()
        csv_content = csv_path.read_text()
        assert "X0Y1" in csv_content

    def test_multiple_features_same_tile(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Multiple features for same tile should all be processed."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
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
        ]

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )

        def mock_set_feature_to_str(feature):
            return feature.feature

        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=mock_set_feature_to_str,
        )

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_path = output_file.with_suffix(".csv")
        csv_content = csv_path.read_text()
        assert "X0Y1" in csv_content

    def test_multiple_features_different_tiles(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Features for different tiles should update both."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
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

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )

        def mock_set_feature_to_str(feature):
            return feature.feature

        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=mock_set_feature_to_str,
        )

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_path = output_file.with_suffix(".csv")
        csv_content = csv_path.read_text()
        assert "X0Y1" in csv_content
        assert "X1Y1" in csv_content

    def test_feature_with_value_1(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """Feature with value=1 should set bit to 1."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
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
        ]

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )

        def mock_set_feature_to_str(feature):
            return feature.feature

        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=mock_set_feature_to_str,
        )

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_path = output_file.with_suffix(".csv")
        assert csv_path.exists()

    def test_feature_with_value_0(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """Feature with value=0 should set bit to 0."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
            FasmLine(
                set_feature=SetFasmFeature(
                    feature="X0Y1.W2MID7.A_I",
                    start=None,
                    end=None,
                    value=0,
                    value_format=None,
                ),
                annotations=None,
                comment=None,
            ),
        ]

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )

        def mock_set_feature_to_str(feature):
            return feature.feature

        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=mock_set_feature_to_str,
        )

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_path = output_file.with_suffix(".csv")
        assert csv_path.exists()

    def test_empty_fasm_produces_zero_bitstream(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Empty FASM should produce an all-zero bitstream and log a warning."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])
        mock_logger = mocker.patch("fabulous_bit_gen.bit_gen.logger")

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_path = output_file.with_suffix(".csv")
        csv_content = csv_path.read_text()
        assert "frame0" in csv_content
        warning_messages = [call[0][0] for call in mock_logger.warning.call_args_list]
        assert any("no features" in msg for msg in warning_messages)

    def _spec_with_x0y1_features(
        self,
        base: dict,
        tile_specs: dict,
        tile_specs_no_mask: dict | None = None,
    ) -> dict:
        """Return a deep copy of base with X0Y1 TileSpecs overridden."""
        spec = copy.deepcopy(base)
        spec["TileSpecs"]["X0Y1"] = tile_specs
        spec["TileSpecs_No_Mask"]["X0Y1"] = (
            tile_specs_no_mask if tile_specs_no_mask is not None else tile_specs
        )
        return spec

    def _run_with_features(self, features, spec_dict, temp_output_dir, mocker):
        """Run genBitstream with a given list of feature strings.

        Returns mock_logger.
        """
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
            FasmLine(
                set_feature=SetFasmFeature(
                    feature=f,
                    start=None,
                    end=None,
                    value=1,
                    value_format=None,
                ),
                annotations=None,
                comment=None,
            )
            for f in features
        ]

        with spec_file.open("wb") as f:
            pickle.dump(spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=lambda f: f.feature,
        )
        mock_logger = mocker.patch("fabulous_bit_gen.bit_gen.logger")

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))
        return mock_logger

    def test_overlapping_features_emit_warning(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Two features mapping to the same bit index should trigger a logger warning.

        Both TileSpecs (masked) and TileSpecs_No_Mask (unmasked) overlap at bit 50, so
        two warnings are expected: one per bitstream.
        """
        mock_logger = self._run_with_features(
            ["X0Y1.FEAT.A", "X0Y1.FEAT.B"],
            self._spec_with_x0y1_features(
                minimal_spec_dict, {"FEAT.A": {50: "1"}, "FEAT.B": {50: "1"}}
            ),
            temp_output_dir,
            mocker,
        )

        assert mock_logger.warning.call_count == 2
        for call in mock_logger.warning.call_args_list:
            warning_msg = call[0][0]
            assert "X0Y1" in warning_msg
            assert "50" in warning_msg

    def test_overlapping_zero_valued_bit_emits_warning(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """Overwrite of a zero-valued bit must still warn.

        A feature can map a bit to value '0'. Since tile_bits is initialised to all
        zeros, a value-based sentinel (old != 0) would miss this case. The touched_bits
        tracker must detect it regardless of the stored value. Both TileSpecs and
        TileSpecs_No_Mask overlap, so two warnings are expected.
        """
        mock_logger = self._run_with_features(
            ["X0Y1.FEAT.A", "X0Y1.FEAT.B"],
            self._spec_with_x0y1_features(
                minimal_spec_dict,
                {
                    "FEAT.A": {50: "0"},  # explicitly writes 0 to bit 50
                    "FEAT.B": {50: "1"},  # then overwrites bit 50 with 1
                },
            ),
            temp_output_dir,
            mocker,
        )

        assert mock_logger.warning.call_count == 2
        for call in mock_logger.warning.call_args_list:
            warning_msg = call[0][0]
            assert "X0Y1" in warning_msg
            assert "50" in warning_msg

    def test_no_mask_only_overlap_emits_one_warning(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """Overlap only in TileSpecs_No_Mask should warn exactly once (unmasked path).

        TileSpecs (masked) maps each feature to a distinct bit, so no masked warning
        fires.  TileSpecs_No_Mask maps both features to bit 50, which triggers the
        unmasked overwrite warning.
        """
        mock_logger = self._run_with_features(
            ["X0Y1.FEAT.A", "X0Y1.FEAT.B"],
            self._spec_with_x0y1_features(
                minimal_spec_dict,
                {"FEAT.A": {50: "1"}, "FEAT.B": {51: "1"}},  # masked: distinct bits
                {"FEAT.A": {50: "1"}, "FEAT.B": {50: "1"}},  # unmasked: both bit 50
            ),
            temp_output_dir,
            mocker,
        )

        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "unmasked" in warning_msg
        assert "X0Y1" in warning_msg
        assert "50" in warning_msg

    def test_masked_only_overlap_emits_one_warning(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """Overlap only in TileSpecs (masked) should warn exactly once (masked path).

        TileSpecs_No_Mask maps each feature to a distinct bit, so no unmasked warning
        fires.  TileSpecs maps both features to bit 50, triggering the masked overwrite
        warning.
        """
        mock_logger = self._run_with_features(
            ["X0Y1.FEAT.A", "X0Y1.FEAT.B"],
            self._spec_with_x0y1_features(
                minimal_spec_dict,
                {"FEAT.A": {50: "1"}, "FEAT.B": {50: "1"}},  # masked: both bit 50
                {"FEAT.A": {50: "1"}, "FEAT.B": {51: "1"}},  # unmasked: distinct bits
            ),
            temp_output_dir,
            mocker,
        )

        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "unmasked" not in warning_msg
        assert "X0Y1" in warning_msg
        assert "50" in warning_msg

    def test_non_overlapping_features_emit_no_warning(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """Features that write to distinct bit indices should not trigger any
        warning."""
        mock_logger = self._run_with_features(
            ["X0Y1.W2MID7.A_I", "X0Y1.GND0.A_T"],
            minimal_spec_dict,
            temp_output_dir,
            mocker,
        )

        mock_logger.warning.assert_not_called()


class TestGenBitstreamVersionCompat:
    """Tests for version-dependent compatibility fixes."""

    def _spec_with_iomux(self, base: dict, version: str) -> dict:
        """Spec using old IOmux naming (capital-O) for the given version.

        FASM feature 'X0Y1.A.I0mux' → feature_name 'A.I0mux'; old spec stores 'A.IOmux'.
        """
        spec = copy.deepcopy(base)
        spec["FABulousVersion"] = version
        spec["TileSpecs"]["X0Y1"] = {"A.IOmux": {10: "1"}}
        spec["TileSpecs_No_Mask"]["X0Y1"] = {"A.IOmux": {10: "1"}}
        return spec

    def _run(self, feature: str, spec_dict: dict, temp_output_dir, mocker):
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"
        fasm_lines = [
            FasmLine(
                set_feature=SetFasmFeature(
                    feature=feature, start=None, end=None, value=1, value_format=None
                ),
                annotations=None,
                comment=None,
            )
        ]
        with spec_file.open("wb") as f:
            pickle.dump(spec_dict, f)
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="x")
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=lambda f: f.feature,
        )
        mock_logger = mocker.patch("fabulous_bit_gen.bit_gen.logger")
        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))
        return mock_logger

    @pytest.mark.parametrize("version", ["1.0", "2.0b", "2.0", "2.1", "3.0"])
    def test_i0mux_remapped_to_iomux_for_any_version(
        self, version, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """New nextpnr I0mux matches an old-template IOmux spec at any version."""
        mock_logger = self._run(
            "X0Y1.A.I0mux",
            self._spec_with_iomux(minimal_spec_dict, version),
            temp_output_dir,
            mocker,
        )
        mock_logger.warning.assert_called_once()
        assert "might need an update" in mock_logger.warning.call_args[0][0]

    def test_iomux_remapped_to_i0mux(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Old nextpnr IOmux matches a new-template I0mux spec."""
        spec = self._spec_with_iomux(minimal_spec_dict, "2.0")
        spec["TileSpecs"]["X0Y1"] = {"A.I0mux": {10: "1"}}
        spec["TileSpecs_No_Mask"]["X0Y1"] = {"A.I0mux": {10: "1"}}
        self._run("X0Y1.A.IOmux", spec, temp_output_dir, mocker)

    def test_unrelated_feature_not_remapped(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Only the carry mux bit is aliased; other misses still raise."""
        with pytest.raises(SpecMissMatch):
            self._run(
                "X0Y1.B.I0mux",
                self._spec_with_iomux(minimal_spec_dict, "2.0"),
                temp_output_dir,
                mocker,
            )

    def test_i0mux_used_directly_when_present_in_spec(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """If spec already has I0mux, use it directly without remapping."""
        spec = self._spec_with_iomux(minimal_spec_dict, "1.0")
        spec["TileSpecs"]["X0Y1"] = {"A.I0mux": {10: "1"}}
        spec["TileSpecs_No_Mask"]["X0Y1"] = {"A.I0mux": {10: "1"}}
        self._run("X0Y1.A.I0mux", spec, temp_output_dir, mocker)


class TestGenBitstreamErrorHandling:
    """Tests for error handling in genBitstream."""

    def test_tile_location_not_in_spec_raises_specmissmatch(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Invalid tile location should raise SpecMissMatch."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
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

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )

        def mock_set_feature_to_str(feature):
            return feature.feature

        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=mock_set_feature_to_str,
        )

        with pytest.raises(SpecMissMatch) as exc_info:
            gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        assert "X99Y99" in str(exc_info.value)

    def test_feature_not_in_tile_specs_raises_specmissmatch(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Invalid feature for valid tile should raise SpecMissMatch."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
            FasmLine(
                set_feature=SetFasmFeature(
                    feature="X0Y1.UNKNOWN.FEATURE",
                    start=None,
                    end=None,
                    value=1,
                    value_format=None,
                ),
                annotations=None,
                comment=None,
            ),
        ]

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )

        def mock_set_feature_to_str(feature):
            return feature.feature

        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=mock_set_feature_to_str,
        )

        with pytest.raises(SpecMissMatch) as exc_info:
            gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        assert "UNKNOWN.FEATURE" in str(exc_info.value)

    def test_specmissmatch_error_message_format(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """SpecMissMatch should include tile type, location, and feature."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
            FasmLine(
                set_feature=SetFasmFeature(
                    feature="X0Y1.INVALID.FEATURE",
                    start=None,
                    end=None,
                    value=1,
                    value_format=None,
                ),
                annotations=None,
                comment=None,
            ),
        ]

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )

        def mock_set_feature_to_str(feature):
            return feature.feature

        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=mock_set_feature_to_str,
        )

        with pytest.raises(SpecMissMatch) as exc_info:
            gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        error_msg = str(exc_info.value)
        assert "X0Y1" in error_msg
        assert "INVALID.FEATURE" in error_msg


class TestGenBitstreamFaultCases:
    """Tests for fault cases and error conditions."""

    def test_spec_file_not_found(self, temp_output_dir, mocker) -> None:
        """Missing spec file should raise FileNotFoundError."""
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"
        spec_file = temp_output_dir / "nonexistent.bin"

        fasm_file.write_text("")

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        with pytest.raises(FileNotFoundError):
            gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

    def test_fasm_file_not_found(self, minimal_spec_dict, temp_output_dir) -> None:
        """Missing FASM file should raise FileNotFoundError."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "nonexistent.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        with pytest.raises(FileNotFoundError):
            gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

    def test_corrupted_pickle_spec_file(self, temp_output_dir, mocker) -> None:
        """Corrupted pickle file should raise pickle.UnpicklingError."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_file.write_text("")
        with spec_file.open("wb") as f:
            f.write(b"corrupted pickle data")

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        with pytest.raises(pickle.UnpicklingError):
            gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

    def test_empty_spec_dict(self, temp_output_dir, mocker) -> None:
        """Empty spec dict should raise KeyError."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_file.write_text("")
        with spec_file.open("wb") as f:
            pickle.dump({}, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        with pytest.raises(KeyError):
            gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

    def test_spec_dict_missing_archspecs(self, temp_output_dir, mocker) -> None:
        """Spec dict missing ArchSpecs should use default fallback values."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        incomplete_spec = {
            "TileMap": {"X0Y1": "W_IO"},
            "TileSpecs": {"X0Y1": {}},
            "TileSpecs_No_Mask": {"X0Y1": {}},
            "FrameMap": {"W_IO": {}},
        }

        fasm_file.write_text("")
        with spec_file.open("wb") as f:
            pickle.dump(incomplete_spec, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))
        assert output_file.exists()

    def test_spec_dict_missing_tilemap(self, temp_output_dir, mocker) -> None:
        """Spec dict missing TileMap should raise KeyError."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        incomplete_spec = {
            "ArchSpecs": {"MaxFramesPerCol": 20, "FrameBitsPerRow": 32},
            "TileSpecs": {},
            "TileSpecs_No_Mask": {},
            "FrameMap": {},
        }

        fasm_file.write_text("")
        with spec_file.open("wb") as f:
            pickle.dump(incomplete_spec, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        with pytest.raises(KeyError):
            gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

    def test_spec_dict_missing_tilespecs(self, temp_output_dir, mocker) -> None:
        """Spec dict missing TileSpecs should raise KeyError."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"
        fasm_lines = [
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
            )
        ]

        incomplete_spec = {
            "ArchSpecs": {"MaxFramesPerCol": 20, "FrameBitsPerRow": 32},
            "TileMap": {"X0Y1": "W_IO"},
            "TileSpecs_No_Mask": {},
            "FrameMap": {},
        }

        fasm_file.write_text("")
        with spec_file.open("wb") as f:
            pickle.dump(incomplete_spec, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string",
            return_value="canonical_string",
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )

        with pytest.raises(KeyError):
            gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

    def test_spec_dict_missing_framemap(self, temp_output_dir, mocker) -> None:
        """Spec dict missing FrameMap should raise KeyError."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        incomplete_spec = {
            "ArchSpecs": {"MaxFramesPerCol": 20, "FrameBitsPerRow": 32},
            "TileMap": {"X0Y1": "W_IO"},
            "TileSpecs": {"X0Y1": {}},
            "TileSpecs_No_Mask": {"X0Y1": {}},
        }

        fasm_file.write_text("")
        with spec_file.open("wb") as f:
            pickle.dump(incomplete_spec, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        with pytest.raises(KeyError):
            gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

    def test_archspecs_missing_maxframespercol(self, temp_output_dir, mocker) -> None:
        """ArchSpecs missing MaxFramesPerCol should use fallback value."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        incomplete_spec = {
            "ArchSpecs": {"FrameBitsPerRow": 32},
            "TileMap": {"X0Y1": "W_IO"},
            "TileSpecs": {"X0Y1": {}},
            "TileSpecs_No_Mask": {"X0Y1": {}},
            "FrameMap": {"W_IO": {}},
        }

        fasm_file.write_text("")
        with spec_file.open("wb") as f:
            pickle.dump(incomplete_spec, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))
        assert output_file.exists()

    def test_archspecs_missing_framebitsperrow(self, temp_output_dir, mocker) -> None:
        """ArchSpecs missing FrameBitsPerRow should use fallback value."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        incomplete_spec = {
            "ArchSpecs": {"MaxFramesPerCol": 20},
            "TileMap": {"X0Y1": "W_IO"},
            "TileSpecs": {"X0Y1": {}},
            "TileSpecs_No_Mask": {"X0Y1": {}},
            "FrameMap": {"W_IO": {}},
        }

        fasm_file.write_text("")
        with spec_file.open("wb") as f:
            pickle.dump(incomplete_spec, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))
        assert output_file.exists()

    def test_resolve_bitstream_format_warns_when_using_defaults(self, mocker) -> None:
        """Missing format fields should emit fallback debug logs during resolution."""
        mock_logger = mocker.patch("fabulous_bit_gen.bit_gen.logger")
        resolved = _resolve_bitstream_format({"ArchSpecs": {}})

        assert resolved.frame_bits_per_row == FRAME_BITS_PER_ROW
        assert resolved.max_frames_per_col == MAX_FRAMES_PER_COL
        assert resolved.sync_header_hex == SYNC_HEADER_HEX
        assert resolved.frame_select_width == FRAME_SELECT_WIDTH
        assert resolved.desync_bit == DESYNC_BIT
        assert resolved.fabulous_version == "1.0"
        assert resolved.multi_clk_domains is False
        assert mock_logger.debug.call_count == 8

    def test_resolve_format_uses_fabulous_version_from_spec(self, mocker) -> None:
        """FABulousVersion present in spec should be used as-is."""
        mocker.patch("fabulous_bit_gen.bit_gen.logger")
        resolved = _resolve_bitstream_format(
            {"FABulousVersion": "2.0", "ArchSpecs": {}}
        )

        assert resolved.fabulous_version == "2.0"

    def test_resolve_format_uses_multi_clk_domains_from_spec(self, mocker) -> None:
        """MultiClkDomains present in spec should be used as-is."""
        mocker.patch("fabulous_bit_gen.bit_gen.logger")
        resolved = _resolve_bitstream_format({"MultiClkDomains": True, "ArchSpecs": {}})

        assert resolved.multi_clk_domains is True

    def test_resolve_format_raises_when_max_frames_exceeds_select_bits(self) -> None:
        """MaxFramesPerCol exceeding selectable frame bits raises ValueError."""
        with pytest.raises(ValueError, match="MaxFramesPerCol.*exceeds"):
            _resolve_bitstream_format(
                {"ArchSpecs": {"MaxFramesPerCol": 33, "FrameBitsPerRow": 32}}
            )

    def test_resolve_format_raises_when_frame_select_width_too_large(self) -> None:
        """FrameSelectWidth >= FrameBitsPerRow should raise ValueError."""
        with pytest.raises(ValueError, match="FRAME_SELECT_WIDTH.*must be less than"):
            _resolve_bitstream_format(
                {"ArchSpecs": {"FrameSelectWidth": 32, "FrameBitsPerRow": 32}}
            )

    def test_resolve_format_raises_when_desync_bit_too_large(self) -> None:
        """DESYNC_BIT >= selectable frame bits should raise ValueError."""
        with pytest.raises(ValueError, match="DESYNC_BIT.*must be less than"):
            _resolve_bitstream_format({"ArchSpecs": {"DesyncBit": 32}})

    def test_resolve_format_raises_when_desync_bit_overlaps_frame_strobe(self) -> None:
        """DESYNC_BIT inside frame strobe range should raise ValueError."""
        with pytest.raises(ValueError, match="DESYNC_BIT.*must be >= MaxFramesPerCol"):
            _resolve_bitstream_format(
                {
                    "ArchSpecs": {
                        "MaxFramesPerCol": 21,
                        "DesyncBit": 20,
                        "FrameBitsPerRow": 32,
                        "FrameSelectWidth": 5,
                    }
                }
            )

    def test_genbitstream_raises_when_grid_wider_than_frame_select_width(
        self, temp_output_dir, mocker
    ) -> None:
        """Grid with more columns than FRAME_SELECT_WIDTH can address should raise."""
        # FRAME_SELECT_WIDTH=2 -> max 4 columns; grid has 5 (X0-X4)
        spec_dict = {
            "ArchSpecs": {
                "MaxFramesPerCol": 20,
                "FrameBitsPerRow": 32,
                "FrameSelectWidth": 2,
            },
            "TileMap": {f"X{x}Y{y}": "NULL" for x in range(5) for y in range(3)},
            "TileSpecs": {f"X{x}Y{y}": {} for x in range(5) for y in range(3)},
            "TileSpecs_No_Mask": {f"X{x}Y{y}": {} for x in range(5) for y in range(3)},
            "FrameMap": {"NULL": {}},
            "FrameMapEncode": {},
        }
        spec_file = temp_output_dir / "spec.bin"
        with spec_file.open("wb") as f:
            pickle.dump(spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        with pytest.raises(ValueError, match="columns.*FRAME_SELECT_WIDTH"):
            gen_bitstream(
                str(temp_output_dir / "test.fasm"),
                str(spec_file),
                str(temp_output_dir / "output.bin"),
            )

    def test_feature_with_insufficient_parts(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Feature with less than 3 parts should raise IndexError."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
            FasmLine(
                set_feature=SetFasmFeature(
                    feature="X0Y1.ONLYONEPART",
                    start=None,
                    end=None,
                    value=1,
                    value_format=None,
                ),
                annotations=None,
                comment=None,
            ),
        ]

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )

        def mock_set_feature_to_str(feature):
            return feature.feature

        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=mock_set_feature_to_str,
        )

        with pytest.raises(SpecMissMatch, match="fewer than 3 dot-separated parts"):
            gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

    def test_tile_coord_invalid_format(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Tile coordinate that doesn't match XnYm pattern raises ValueError."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        spec_dict_with_invalid = minimal_spec_dict.copy()
        spec_dict_with_invalid["TileMap"]["INVALID"] = "W_IO"
        spec_dict_with_invalid["TileSpecs"]["INVALID"] = {}
        spec_dict_with_invalid["TileSpecs_No_Mask"]["INVALID"] = {}

        with spec_file.open("wb") as f:
            pickle.dump(spec_dict_with_invalid, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        with pytest.raises(ValueError, match="XnYm format"):
            gen_bitstream(str(fasm_file), str(spec_file), str(output_file))


class TestGenBitstreamEdgeCases:
    """Edge case tests for genBitstream function."""

    def test_feature_name_with_more_than_three_parts(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Feature with 4+ parts should only use first 3."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
            FasmLine(
                set_feature=SetFasmFeature(
                    feature="X0Y1.W2MID7.A_I.EXTRA",
                    start=None,
                    end=None,
                    value=1,
                    value_format=None,
                ),
                annotations=None,
                comment=None,
            ),
        ]

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )

        def mock_set_feature_to_str(feature):
            return feature.feature

        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=mock_set_feature_to_str,
        )

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_content = output_file.with_suffix(".csv").read_text()
        # Extra part silently ignored; feature "W2MID7.A_I" resolved correctly
        assert "X0Y1" in csv_content

    def test_feature_containing_clk_substring(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Feature containing 'CLK' substring should be filtered."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
            FasmLine(
                set_feature=SetFasmFeature(
                    feature="X0Y1.ACLK_BUFFER.enable",
                    start=None,
                    end=None,
                    value=1,
                    value_format=None,
                ),
                annotations=None,
                comment=None,
            ),
        ]

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )

        def mock_set_feature_to_str(feature):
            return feature.feature

        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=mock_set_feature_to_str,
        )

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_content = output_file.with_suffix(".csv").read_text()
        # CLK-substring feature filtered (would raise SpecMissMatch if not)
        assert "X0Y1" in csv_content

    def test_large_grid_dimensions(self, temp_output_dir, mocker) -> None:
        """Test with large grid (many tiles)."""
        spec_dict = {
            "ArchSpecs": {"MaxFramesPerCol": 20, "FrameBitsPerRow": 32},
            "TileMap": {f"X{x}Y{y}": "LUT4AB" for x in range(10) for y in range(10)},
            "TileSpecs": {f"X{x}Y{y}": {} for x in range(10) for y in range(10)},
            "TileSpecs_No_Mask": {
                f"X{x}Y{y}": {} for x in range(10) for y in range(10)
            },
            "FrameMap": {"LUT4AB": {0: "11111111111111111111111111111111"}},
            "FrameMapEncode": {},
        }

        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        assert output_file.exists()

    def test_tile_with_leading_zeros_in_coords_is_treated_as_sparse_grid(
        self, temp_output_dir, mocker
    ) -> None:
        """Leading-zero tile keys should not crash frame/CSV generation."""
        spec_dict = {
            "ArchSpecs": {"MaxFramesPerCol": 20, "FrameBitsPerRow": 32},
            "TileMap": {"X01Y01": "LUT4AB", "X01Y02": "NULL"},
            "TileSpecs": {"X01Y01": {}, "X01Y02": {}},
            "TileSpecs_No_Mask": {"X01Y01": {}, "X01Y02": {}},
            "FrameMap": {"LUT4AB": {0: "11111111111111111111111111111111"}, "NULL": {}},
            "FrameMapEncode": {},
        }

        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))
        assert output_file.exists()

    def test_single_column_grid(self, temp_output_dir, mocker) -> None:
        """Grid with single column should work."""
        spec_dict = {
            "ArchSpecs": {"MaxFramesPerCol": 20, "FrameBitsPerRow": 32},
            "TileMap": {"X0Y0": "NULL", "X0Y1": "W_IO", "X0Y2": "NULL"},
            "TileSpecs": {"X0Y1": {}},
            "TileSpecs_No_Mask": {"X0Y1": {}},
            "FrameMap": {"NULL": {}, "W_IO": {0: "11111111111111111111111111111111"}},
            "FrameMapEncode": {},
        }

        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        assert output_file.exists()

    def test_feature_with_empty_bit_mapping(self, temp_output_dir, mocker) -> None:
        """Feature with empty bit mapping dictionary should not crash."""
        spec_dict = {
            "ArchSpecs": {"MaxFramesPerCol": 20, "FrameBitsPerRow": 32},
            "TileMap": {"X0Y1": "W_IO", "X0Y2": "NULL"},
            "TileSpecs": {"X0Y1": {"EMPTY.FEATURE": {}}},
            "TileSpecs_No_Mask": {"X0Y1": {"EMPTY.FEATURE": {}}},
            "FrameMap": {"W_IO": {0: "11111111111111111111111111111111"}, "NULL": {}},
            "FrameMapEncode": {},
        }

        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
            FasmLine(
                set_feature=SetFasmFeature(
                    feature="X0Y1.EMPTY.FEATURE",
                    start=None,
                    end=None,
                    value=1,
                    value_format=None,
                ),
                annotations=None,
                comment=None,
            ),
        ]

        with spec_file.open("wb") as f:
            pickle.dump(spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )

        def mock_set_feature_to_str(feature):
            return feature.feature

        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=mock_set_feature_to_str,
        )

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        assert output_file.exists()

    def test_bit_index_at_boundary(self, temp_output_dir, mocker) -> None:
        """Bit index at MaxFramesPerCol * FrameBitsPerRow - 1 should work."""
        max_index = 20 * 32 - 1
        spec_dict = {
            "ArchSpecs": {"MaxFramesPerCol": 20, "FrameBitsPerRow": 32},
            "TileMap": {"X0Y1": "W_IO", "X0Y2": "NULL"},
            "TileSpecs": {"X0Y1": {"TEST.FEATURE": {max_index: "1"}}},
            "TileSpecs_No_Mask": {"X0Y1": {"TEST.FEATURE": {max_index: "1"}}},
            "FrameMap": {"W_IO": {0: "11111111111111111111111111111111"}, "NULL": {}},
            "FrameMapEncode": {},
        }

        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
            FasmLine(
                set_feature=SetFasmFeature(
                    feature="X0Y1.TEST.FEATURE",
                    start=None,
                    end=None,
                    value=1,
                    value_format=None,
                ),
                annotations=None,
                comment=None,
            ),
        ]

        with spec_file.open("wb") as f:
            pickle.dump(spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )

        def mock_set_feature_to_str(feature):
            return feature.feature

        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=mock_set_feature_to_str,
        )

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        assert output_file.exists()

    def test_output_path_with_spaces(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """Output path with spaces should work."""
        spec_file = temp_output_dir / "spec.bin"
        output_dir = temp_output_dir / "output with spaces"
        output_dir.mkdir()
        output_file = output_dir / "my output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(
            str(temp_output_dir / "test.fasm"), str(spec_file), str(output_file)
        )

        assert output_file.exists()

    def test_relative_path_output(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
        monkeypatch,
    ) -> None:
        """Relative output path should work."""
        spec_file = temp_output_dir / "spec.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        monkeypatch.chdir(temp_output_dir)
        gen_bitstream(str(temp_output_dir / "test.fasm"), str(spec_file), "output.bin")

        assert (temp_output_dir / "output.bin").exists()


class TestGenBitstreamNullTileHandling:
    """Tests for NULL tile handling."""

    def test_null_tile_frame_bits_all_zeros(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """NULL tiles should produce zero frame bits."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_path = output_file.with_suffix(".csv")
        csv_content = csv_path.read_text()

        # Note: Y0 (bottom) and Y{max} (top) rows are skipped in output
        # X0Y1 and X1Y1 are processed (Y=1)
        assert "X0Y1" in csv_content

    def test_null_tile_not_in_hdl_output(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """NULL tiles should not appear in HDL output."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        vh_path = output_file.with_suffix(".vh")
        vh_content = vh_path.read_text()
        vhd_path = output_file.with_suffix(".vhd")
        vhd_content = vhd_path.read_text()

        assert "Tile_X0Y0" not in vh_content
        assert "Tile_X0Y0" not in vhd_content


class TestGenBitstreamFrameMap:
    """Tests for FrameMap handling."""

    def test_tile_with_empty_framemap_skipped_in_hdl(
        self,
        temp_output_dir,
        mocker,
    ) -> None:
        """Tiles with empty FrameMap should be skipped in HDL output."""
        spec_dict = {
            "ArchSpecs": {"MaxFramesPerCol": 20, "FrameBitsPerRow": 32},
            "TileMap": {"X0Y1": "EMPTY_TYPE"},
            "TileSpecs": {"X0Y1": {"FEATURE.A": {0: "1"}}},
            "TileSpecs_No_Mask": {"X0Y1": {"FEATURE.A": {0: "1"}}},
            "FrameMap": {"EMPTY_TYPE": {}},
            "FrameMapEncode": {},
        }

        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        vh_path = output_file.with_suffix(".vh")
        vh_content = vh_path.read_text()
        assert "Tile_X0Y1" not in vh_content

    def test_non_empty_framemap_tile_included_in_hdl(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Tiles with non-empty FrameMap should appear in HDL output."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        vh_path = output_file.with_suffix(".vh")
        vh_content = vh_path.read_text()
        assert "Tile_X0Y1" in vh_content
        assert "Tile_X1Y1" in vh_content


class TestGenBitstreamCsvOutput:
    """Tests for CSV output generation."""

    def test_csv_file_created(self, minimal_spec_dict, temp_output_dir, mocker) -> None:
        """CSV file should be created."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_path = output_file.with_suffix(".csv")
        assert csv_path.exists()

    def test_csv_tile_line_format(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """CSV tile lines should have format: tileLoc,tileType,x,y."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_path = output_file.with_suffix(".csv")
        csv_content = csv_path.read_text()

        assert "X0Y1,W_IO,0,1" in csv_content

    def test_csv_frame_line_format(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """CSV frame lines should have format: frameN,n,32,bits."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_path = output_file.with_suffix(".csv")
        csv_content = csv_path.read_text()

        assert "frame0,0,32," in csv_content

    def test_csv_row_order_reversed(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """Rows in CSV should be processed from num_rows-2 down to 1."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_path = output_file.with_suffix(".csv")
        csv_content = csv_path.read_text()
        lines = csv_content.strip().split("\n")

        first_tile_line = None
        for line in lines:
            if line.startswith("X"):
                first_tile_line = line
                break

        assert first_tile_line is not None, "CSV contained no tile lines"
        assert "Y1" in first_tile_line


class TestGenBitstreamVhdlOutput:
    """Tests for VHDL output generation."""

    def test_vhdl_file_created(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """VHDL file should be created."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        vhd_path = output_file.with_suffix(".vhd")
        assert vhd_path.exists()

    def test_vhdl_package_header(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """VHDL file should contain IEEE library and package declaration."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        vhd_path = output_file.with_suffix(".vhd")
        vhd_content = vhd_path.read_text()

        assert "library IEEE" in vhd_content
        assert "package emulate_bitstream" in vhd_content

    def test_vhdl_constant_format(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """VHDL constants should have correct format."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        vhd_path = output_file.with_suffix(".vhd")
        vhd_content = vhd_path.read_text()

        assert "constant Tile_X0Y1_Emulate_Bitstream" in vhd_content
        assert "std_logic_vector" in vhd_content


class TestGenBitstreamVerilogOutput:
    """Tests for Verilog output generation."""

    def test_verilog_file_created(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """Verilog file should be created."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        vh_path = output_file.with_suffix(".vh")
        assert vh_path.exists()

    def test_verilog_define_format(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """Verilog defines should have correct format."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        vh_path = output_file.with_suffix(".vh")
        vh_content = vh_path.read_text()

        assert "`define Tile_X0Y1_Emulate_Bitstream" in vh_content
        assert "640'b" in vh_content

    def test_verilog_bit_order_reversed(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Verilog output should have bits in reverse order."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        vh_path = output_file.with_suffix(".vh")
        vh_content = vh_path.read_text()

        assert "640'b" in vh_content


class TestGenBitstreamNoneSetFeature:
    """Tests for FasmLine with set_feature=None (comment/annotation lines)."""

    def test_fasm_line_with_none_set_feature_is_skipped(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """FasmLine with set_feature=None should be silently skipped."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
            FasmLine(set_feature=None, annotations=None, comment="# a comment"),
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
        ]

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )

        def mock_set_feature_to_str(feature):
            return feature.feature

        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=mock_set_feature_to_str,
        )

        # Should not raise TypeError/AttributeError from set_feature_to_str(None)
        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_content = output_file.with_suffix(".csv").read_text()
        assert "X0Y1" in csv_content

    def test_all_none_set_features_produces_zero_bitstream(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """FASM with only None set_features (comments only) should succeed."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
            FasmLine(set_feature=None, annotations=None, comment="# comment 1"),
            FasmLine(set_feature=None, annotations=None, comment="# comment 2"),
        ]

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )
        mocker.patch("fabulous_bit_gen.bit_gen.set_feature_to_str")

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        assert output_file.with_suffix(".csv").exists()


class TestGenBitstreamCsvRowBoundaries:
    """Tests that top and bottom rows are excluded from CSV output."""

    def test_bottom_row_absent_from_csv(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Y0 (bottom row) should not appear in CSV output."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_content = output_file.with_suffix(".csv").read_text()
        tile_lines = [
            line_ for line_ in csv_content.splitlines() if line_.startswith("X")
        ]
        assert tile_lines, "CSV contained no tile lines"
        assert all("Y0" not in line_ for line_ in tile_lines)

    def test_top_row_absent_from_csv(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """Y{max} (top row) should not appear in CSV output."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_content = output_file.with_suffix(".csv").read_text()
        tile_lines = [
            line_ for line_ in csv_content.splitlines() if line_.startswith("X")
        ]
        assert tile_lines, "CSV contained no tile lines"
        # minimal_spec_dict has Y2 as max row
        assert all("Y2" not in line_ for line_ in tile_lines)


class TestGenBitstreamSpecInconsistency:
    """Tests for TileSpecs / TileSpecs_No_Mask inconsistency."""

    def test_feature_missing_from_tilespecs_no_mask_raises_specmissmatch(
        self, temp_output_dir, mocker
    ) -> None:
        """Feature in TileSpecs but absent from TileSpecs_No_Mask should raise
        SpecMissMatch."""
        spec_dict = {
            "ArchSpecs": {"MaxFramesPerCol": 20, "FrameBitsPerRow": 32},
            "TileMap": {"X0Y0": "NULL", "X0Y1": "W_IO", "X0Y2": "NULL"},
            "TileSpecs": {
                "X0Y0": {},
                "X0Y1": {"W2MID7.A_I": {110: "1"}},
                "X0Y2": {},
            },
            "TileSpecs_No_Mask": {
                "X0Y0": {},
                "X0Y1": {},  # feature intentionally absent here
                "X0Y2": {},
            },
            "FrameMap": {
                "NULL": {},
                "W_IO": {0: "11111111111111111111111111111111"},
            },
            "FrameMapEncode": {},
        }

        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        fasm_lines = [
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
        ]

        with spec_file.open("wb") as f:
            pickle.dump(spec_dict, f)

        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=fasm_lines
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="canonical"
        )
        mocker.patch(
            "fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=fasm_lines
        )

        def mock_set_feature_to_str(feature):
            return feature.feature

        mocker.patch(
            "fabulous_bit_gen.bit_gen.set_feature_to_str",
            side_effect=mock_set_feature_to_str,
        )

        with pytest.raises(SpecMissMatch, match="TileSpecs_No_Mask"):
            gen_bitstream(str(fasm_file), str(spec_file), str(output_file))


class TestGenBitstreamBinaryOutput:
    """Tests for binary output generation."""

    def test_bitstream_file_created(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """Binary file should be created."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        assert output_file.exists()

    def test_bitstream_header_bytes(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """Binary file should start with header bytes."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        with output_file.open("rb") as f:
            header = f.read(20)

        expected_header = bytes.fromhex("00AAFF01000000010000000000000000FAB0FAB1")
        assert header == expected_header

    def test_bitstream_desync_frame_appended(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Binary file should end with desync frame."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        with output_file.open("rb") as f:
            content = f.read()

        desync = bytes.fromhex("00100000")
        assert content.endswith(desync)

    def test_bitstream_frame_select_encoding(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Frame select bits should be encoded correctly."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        with output_file.open("rb") as f:
            content = f.read()

        assert len(content) > 20

    def test_bitstream_total_size(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """Binary file size should match expected calculation."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        with output_file.open("rb") as f:
            content = f.read()

        header_size = 20
        desync_size = 4
        assert len(content) >= header_size + desync_size

    def test_bitstream_uses_spec_max_frames_per_col(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """Binary size should follow ArchSpecs MaxFramesPerCol, not fixed 20."""
        spec_dict = {
            **minimal_spec_dict,
            "ArchSpecs": {"MaxFramesPerCol": 3, "FrameBitsPerRow": 32},
        }
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        with output_file.open("rb") as f:
            content = f.read()

        # 20-byte header + (2 cols * 3 frames * (4-byte frame-select + 4-byte data))
        # + 4-byte desync frame.
        assert len(content) == 20 + (2 * 3 * (4 + 4)) + 4

    def test_bitstream_honors_spec_overrides_for_format_constants(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """ArchSpecs format overrides should be reflected in the output bitstream."""
        spec_dict = {
            **minimal_spec_dict,
            "ArchSpecs": {
                "MaxFramesPerCol": 1,
                "FrameBitsPerRow": 16,
                "SyncHeaderHex": "A1B2C3D4",
                "FrameSelectWidth": 4,
                "DesyncBit": 7,
            },
        }
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        with output_file.open("rb") as f:
            content = f.read()

        assert content.startswith(bytes.fromhex("A1B2C3D4"))
        assert content.endswith((1 << 7).to_bytes(2, byteorder="big"))
        # 4-byte header + (2 cols * 1 frame * (2-byte frame-select + 2-byte data))
        # + 2-byte desync frame (FrameBitsPerRow=16 → word_bytes=2).
        assert len(content) == 4 + (2 * 1 * (2 + 2)) + 2


class TestGenBitstreamBitManipulation:
    """Tests for bit manipulation logic."""

    def test_frame_bit_row_reversed(
        self,
        minimal_spec_dict,
        temp_output_dir,
        mocker,
    ) -> None:
        """Frame bit row should be reversed in output."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        csv_path = output_file.with_suffix(".csv")
        csv_content = csv_path.read_text()

        for line in csv_content.split("\n"):
            if "frame0" in line:
                parts = line.split(",")
                if len(parts) >= 4:
                    bits = parts[3]
                    assert len(bits) == 32
                    break

    def test_tile_specs_no_mask_used_for_hdl(
        self, minimal_spec_dict, temp_output_dir, mocker
    ) -> None:
        """HDL output should use TileSpecs_No_Mask data."""
        spec_file = temp_output_dir / "spec.bin"
        fasm_file = temp_output_dir / "test.fasm"
        output_file = temp_output_dir / "output.bin"

        with spec_file.open("wb") as f:
            pickle.dump(minimal_spec_dict, f)

        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_filename", return_value=[])
        mocker.patch("fabulous_bit_gen.bit_gen.fasm_tuple_to_string", return_value="")
        mocker.patch("fabulous_bit_gen.bit_gen.parse_fasm_string", return_value=[])

        gen_bitstream(str(fasm_file), str(spec_file), str(output_file))

        vh_path = output_file.with_suffix(".vh")
        vh_content = vh_path.read_text()

        assert "640'b" in vh_content

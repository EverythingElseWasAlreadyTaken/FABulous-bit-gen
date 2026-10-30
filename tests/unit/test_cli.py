"""Tests for bit_gen CLI entry point."""

import pytest

from fabulous_bit_gen.bit_gen import bit_gen


class TestBitGenCLI:
    """Tests for bit_gen() CLI parsing and dispatch."""

    @pytest.mark.parametrize(
        "argv",
        [
            ["bit_gen", "genBitstream", "spec.bin", "output.bin"],
            ["bit_gen", "genBitstream", "test.fasm"],
            ["bit_gen", "genBitstream", "test.fasm", "spec.bin"],
            ["bit_gen", "genBitstream", "-flag", "spec.bin", "output.bin"],
            ["bit_gen", "genBitstream", "test.fasm", "-flag", "output.bin"],
            ["bit_gen", "genBitstream", "test.fasm", "spec.bin", "-flag"],
            ["bit_gen", "genBitstream", "test.fasm", "spec.bin", "output.bin", "extra"],
            ["bit_gen", "unknownCommand"],
            ["bit_gen", "genBitstream"],
        ],
    )
    def test_invalid_argv_exits_with_code_2(self, argv, mocker) -> None:
        """Invalid arguments should exit with code 2."""
        mocker.patch("sys.argv", argv)
        with pytest.raises(SystemExit) as exc_info:
            bit_gen()
        assert exc_info.value.code == 2

    @pytest.mark.parametrize(
        "argv",
        [
            ["bit_gen", "--help"],
            ["bit_gen", "-h"],
            ["bit_gen", "genBitstream", "--help"],
        ],
    )
    def test_help_exits_with_code_0(self, argv, mocker) -> None:
        """Help flags should exit with code 0."""
        mocker.patch("sys.argv", argv)
        with pytest.raises(SystemExit) as exc_info:
            bit_gen()
        assert exc_info.value.code == 0

    @pytest.mark.parametrize(
        ("argv", "expected_args"),
        [
            (
                ["bit_gen", "genBitstream", "test.fasm", "spec.bin", "output.bin"],
                ("test.fasm", "spec.bin", "output.bin"),
            ),
            (
                [
                    "bit_gen",
                    "genBitstream",
                    "test-file_v1.fasm",
                    "spec_file.bin",
                    "out_v2.bin",
                ],
                ("test-file_v1.fasm", "spec_file.bin", "out_v2.bin"),
            ),
            (
                [
                    "bit_gen",
                    "genBitstream",
                    "test.v1.fasm",
                    "spec.v2.bin",
                    "out.v3.bin",
                ],
                ("test.v1.fasm", "spec.v2.bin", "out.v3.bin"),
            ),
            (
                [
                    "/usr/local/bin/bit_gen",
                    "genBitstream",
                    "test.fasm",
                    "spec.bin",
                    "output.bin",
                ],
                ("test.fasm", "spec.bin", "output.bin"),
            ),
            (
                [
                    "bit_gen",
                    "genBitstream",
                    "a" * 255 + ".fasm",
                    "spec.bin",
                    "output.bin",
                ],
                ("a" * 255 + ".fasm", "spec.bin", "output.bin"),
            ),
            (
                [
                    "bit_gen",
                    "genBitstream",
                    "test_\u03b1\u03b2\u03b3.fasm",
                    "spec.bin",
                    "output.bin",
                ],
                ("test_\u03b1\u03b2\u03b3.fasm", "spec.bin", "output.bin"),
            ),
        ],
    )
    def test_valid_argv_calls_gen_bitstream(self, argv, expected_args, mocker) -> None:
        """Valid genBitstream subcommand should call gen_bitstream with correct args."""
        mock_gen = mocker.patch("fabulous_bit_gen.bit_gen.gen_bitstream")
        mocker.patch("sys.argv", argv)
        bit_gen()
        mock_gen.assert_called_once_with(*expected_args)

    def test_legacy_flag_style_calls_gen_bitstream(self, mocker) -> None:
        """Legacy -genBitstream flag (with dash) should work identically to the
        subcommand."""
        mock_gen = mocker.patch("fabulous_bit_gen.bit_gen.gen_bitstream")
        mocker.patch(
            "sys.argv",
            ["bit_gen", "-genBitstream", "test.fasm", "spec.bin", "output.bin"],
        )
        bit_gen()
        mock_gen.assert_called_once_with("test.fasm", "spec.bin", "output.bin")

    def test_no_subcommand_does_not_call_gen_bitstream(self, mocker) -> None:
        """No subcommand should print help without calling gen_bitstream."""
        mock_gen = mocker.patch("fabulous_bit_gen.bit_gen.gen_bitstream")
        mocker.patch("sys.argv", ["bit_gen"])
        bit_gen()
        mock_gen.assert_not_called()

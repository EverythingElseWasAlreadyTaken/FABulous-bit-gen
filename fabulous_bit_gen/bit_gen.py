#!/usr/bin/env python

"""Bitstream generation utilities for FABulous FPGA fabrics.

Binary bitstream structure::

    [ 20-byte sync header           ]
    for each column (x = 0 ... num_columns-1):
      for each frame (f = 0 ... MaxFramesPerCol-1):
        [ frame-select word         ]  - addresses column + frame
        [ frame data bytes          ]  - num_rows x ceil(FrameBitsPerRow/8) bytes
    [ desync frame                  ]  - bit DESYNC_BIT set

Frame-select word (FrameBitsPerRow-bit, big-endian) - default layout:
  - Bits [31:27]: column index (FrameSelectWidth = 5 bits, normal binary order).
  - Bits [26:21]: unused in the default configuration (always 0).
  - Bit  [20]:    desync flag (desync_flag) - set only in the trailing desync frame.
  - Bits [19:0]:  frame strobe - bit ``f`` set selects frame index ``f``
                  (one-hot, supports up to 20 frames, indices 0-19).

Frame data bytes:
  Concatenation of FrameBitsPerRow configuration bits from each emitted row
  of that column (Y descending), bit-reversed per row, packed into bytes.
  Emitted rows are interior-only by default, or all rows when
  ``include_border_rows`` is enabled.
"""

import argparse
import math
import pickle
import re
import sys
from dataclasses import dataclass
from importlib.metadata import version as _pkg_version
from pathlib import Path

from fasm import (
    FasmLine,
    fasm_tuple_to_string,
    parse_fasm_filename,
    parse_fasm_string,
    set_feature_to_str,
)
from loguru import logger

from fabulous_bit_gen.custom_exception import SpecMissMatch

FRAME_BITS_PER_ROW: int = 32
"""Default width of the both frame-select and frame-data words."""

FRAME_SELECT_WIDTH: int = 5
"""Width of the column-index field in the frame-select word."""

MAX_FRAMES_PER_COL: int = 20
"""Default number of one-hot frame strobe bits used per column."""

SYNC_HEADER_HEX: str = "00AAFF01000000010000000000000000FAB0FAB1"
"""Default FABulous sync header that opens every bitstream."""

DESYNC_BIT: int = 20
"""Bit position of the desync flag inside the frame-select word.

Must be >= MaxFramesPerCol (outside frame strobe range)
and < FRAME_BITS_PER_ROW - FRAME_SELECT_WIDTH (outside column-index field).
"""

FABULOUS_VERSION: str = "1.0"
"""Default FABulous version string."""

_CARRY_MUX_ALIAS: dict[str, str] = {"I0mux": "IOmux", "IOmux": "I0mux"}
"""Both spellings of the LUT carry-in mux config bit, each mapped to the other."""


@dataclass(frozen=True)
class BitstreamFormat:
    """Typed bitstream wire-format settings resolved from spec/defaults."""

    frame_bits_per_row: int
    max_frames_per_col: int
    sync_header_hex: str
    frame_select_width: int
    desync_bit: int
    include_border_rows: bool = False
    fabulous_version: str = "1.0"
    multi_clk_domains: bool = False


def _resolve_bitstream_format(spec_dict: dict) -> BitstreamFormat:
    """Resolve bitstream-format settings from spec dict once with fallbacks."""

    def pick(key: str, default: int | str | bool) -> int | str | bool:
        """Return key from ArchSpecs, then spec_dict top level, then default."""
        arch_specs = spec_dict.get("ArchSpecs", {})
        if key in arch_specs:
            return arch_specs[key]
        if key in spec_dict:
            return spec_dict[key]
        logger.debug(f"{key} missing in bitstream spec; using default {default!r}.")
        return default

    fmt = BitstreamFormat(
        frame_bits_per_row=int(pick("FrameBitsPerRow", FRAME_BITS_PER_ROW)),
        max_frames_per_col=int(pick("MaxFramesPerCol", MAX_FRAMES_PER_COL)),
        sync_header_hex=str(pick("SyncHeaderHex", SYNC_HEADER_HEX)),
        frame_select_width=int(pick("FrameSelectWidth", FRAME_SELECT_WIDTH)),
        desync_bit=int(pick("DesyncBit", DESYNC_BIT)),
        include_border_rows=bool(pick("IncludeBorderRows", False)),
        fabulous_version=str(pick("FABulousVersion", FABULOUS_VERSION)),
        multi_clk_domains=bool(pick("MultiClkDomains", False)),
    )

    if fmt.frame_select_width + 1 > fmt.frame_bits_per_row:
        raise ValueError(
            f"FRAME_SELECT_WIDTH ({fmt.frame_select_width}) (+ 1 DESYNC_BIT) "
            f"must be less than FRAME_BITS_PER_ROW ({fmt.frame_bits_per_row})"
        )

    selectable_frame_bits = fmt.frame_bits_per_row - fmt.frame_select_width
    if fmt.max_frames_per_col > selectable_frame_bits:
        raise ValueError(
            f"MaxFramesPerCol ({fmt.max_frames_per_col}) exceeds "
            "FRAME_BITS_PER_ROW minus FRAME_SELECT_WIDTH "
            f"({selectable_frame_bits}): frame index would overlap the "
            "column index bits"
        )
    if fmt.desync_bit < fmt.max_frames_per_col:
        raise ValueError(
            f"DESYNC_BIT ({fmt.desync_bit}) must be >= MaxFramesPerCol "
            f"({fmt.max_frames_per_col}) so it does not overlap frame strobe bits"
        )
    if fmt.desync_bit >= selectable_frame_bits:
        raise ValueError(
            f"DESYNC_BIT ({fmt.desync_bit}) must be less than "
            f"{selectable_frame_bits} so it does not overlap "
            "the column select bits in the frame-select word"
        )
    return fmt


def bitstring_to_bytes(s: str) -> bytes:
    """Convert a binary string to big-endian bytes.

    Parameters
    ----------
    s : str
        Binary string, e.g. ``'10110101'``.

    Returns
    -------
    bytes
        Big-endian representation, padded to ``ceil(len(s) / 8)`` bytes.
    """
    return int(s, 2).to_bytes(math.ceil(len(s) / 8), byteorder="big")


def _parse_fasm_to_canon_list(fasm_file: str) -> list:
    """Parse a FASM file and return its canonicalised feature list.

    Two-pass: raw parse -> canonical string -> re-parse to resolve shorthand.

    Parameters
    ----------
    fasm_file : str
        Path to the FASM file.

    Returns
    -------
    list
        Canonicalised list of ``FasmLine`` objects.
    """
    fasm_lines = parse_fasm_filename(fasm_file)
    canonical_str = fasm_tuple_to_string(fasm_lines, True)
    return list(parse_fasm_string(canonical_str))


def _apply_fasm_features(
    canon_list: list[FasmLine],
    spec_dict: dict,
    tile_bits: dict[str, list[int]],
    tile_bits_no_mask: dict[str, list[int]],
    bitstream_format: BitstreamFormat,
) -> int:
    """Apply FASM features to tile bit arrays in place. Skips CLK features.

    Parameters
    ----------
    canon_list : list[FasmLine]
        Canonicalised FASM lines from ``_parse_fasm_to_canon_list``.
    spec_dict : dict
        Must contain ``TileMap``, ``TileSpecs``, and ``TileSpecs_No_Mask``.
    tile_bits : dict[str, list[int]]
        Masked per-tile bit array, mutated in place.
    tile_bits_no_mask : dict[str, list[int]]
        Unmasked per-tile bit array, mutated in place.
    bitstream_format : BitstreamFormat
        Resolved format settings; version is used to apply compatibility fixes.

    Returns
    -------
    int
        Number of features remapped between the I0mux and IOmux spellings.

    Raises
    ------
    SpecMissMatch
        If a tile location or feature name is missing from the spec.
    """
    # Track which bit indices have already been written for each tile so that
    # overwrites are detected regardless of the bit value.
    touched_bits: dict[str, set] = {tile: set() for tile in tile_bits}
    touched_bits_no_mask: dict[str, set] = {tile: set() for tile in tile_bits_no_mask}
    carry_mux_remaps = 0

    for line in canon_list:
        if not line.set_feature:
            continue
        feature_str = set_feature_to_str(line.set_feature)
        if "CLK" in feature_str and not bitstream_format.multi_clk_domains:
            continue

        feature_parts = feature_str.split(".")
        if len(feature_parts) < 3:
            raise SpecMissMatch(
                f"Feature '{feature_str}' has fewer than 3 dot-separated parts"
            )
        if len(feature_parts) > 3:
            logger.warning(
                f"Feature '{feature_str}' has {len(feature_parts)} dot-separated "
                "parts; only the first three are used - trailing parts are ignored."
            )
        tile_loc = feature_parts[0]
        feature_name = ".".join((feature_parts[1], feature_parts[2]))

        if tile_loc not in spec_dict["TileMap"]:
            raise SpecMissMatch(
                f"Tile location {tile_loc} not found in the bitstream spec"
            )

        if tile_loc not in spec_dict["TileSpecs"]:
            raise SpecMissMatch(f"Tile location '{tile_loc}' not found in TileSpecs")

        tile_spec = spec_dict["TileSpecs"][tile_loc]
        spec_feature_name = feature_name

        # The LUT carry-in mux bit is spelled I0mux (digit zero) by nextpnr since
        # YosysHQ/nextpnr@ca74f47c3f and IOmux before; fabric templates before
        # FPGA-Research/FABulous#1132 also say IOmux. Either side can be old,
        # independent of FABulousVersion, so accept both spellings both ways.
        if feature_name not in tile_spec and feature_parts[2] in _CARRY_MUX_ALIAS:
            candidate = f"{feature_parts[1]}.{_CARRY_MUX_ALIAS[feature_parts[2]]}"
            if candidate in tile_spec:
                logger.debug(f"Remapping feature '{feature_name}' -> '{candidate}'")
                carry_mux_remaps += 1
                spec_feature_name = candidate

        if spec_feature_name in tile_spec:
            if tile_spec[spec_feature_name]:
                for bit_idx, bit_val in tile_spec[spec_feature_name].items():
                    new_val = int(bit_val)
                    if bit_idx in touched_bits[tile_loc]:
                        logger.warning(
                            f"Bit {bit_idx} of tile {tile_loc} is being overwritten "
                            f"by feature {feature_name} "
                            f"(old value: {tile_bits[tile_loc][bit_idx]}, "
                            f"new value: {new_val})"
                        )
                    touched_bits[tile_loc].add(bit_idx)
                    tile_bits[tile_loc][bit_idx] = new_val
                if tile_loc not in spec_dict["TileSpecs_No_Mask"]:
                    raise SpecMissMatch(
                        f"Tile location '{tile_loc}' not found in TileSpecs_No_Mask"
                    )
                no_mask_spec = spec_dict["TileSpecs_No_Mask"][tile_loc]
                if spec_feature_name not in no_mask_spec:
                    raise SpecMissMatch(
                        f"Feature '{feature_name}' of tile '{tile_loc}' missing "
                        "from TileSpecs_No_Mask"
                    )
                for bit_idx, bit_val in no_mask_spec[spec_feature_name].items():
                    new_val = int(bit_val)
                    if bit_idx in touched_bits_no_mask[tile_loc]:
                        logger.warning(
                            f"Bit {bit_idx} of tile {tile_loc} is being overwritten "
                            f"in the unmasked bitstream by feature {feature_name} "
                            f"(old value: {tile_bits_no_mask[tile_loc][bit_idx]}, "
                            f"new value: {new_val})"
                        )
                    touched_bits_no_mask[tile_loc].add(bit_idx)
                    tile_bits_no_mask[tile_loc][bit_idx] = new_val
        else:
            tile_type = spec_dict["TileMap"][tile_loc]
            raise SpecMissMatch(
                f"Tile type: {tile_type}\n"
                f"with location {tile_loc} and \n"
                f"Feature: {feature_name}\n"
                "found in fasm file was not found in the bitstream spec"
            )
    return carry_mux_remaps


def _compute_grid_size(tile_bits: dict[str, list[int]]) -> tuple[int, int]:
    """Compute grid dimensions from XnYm tile keys (one-based counts).

    Parameters
    ----------
    tile_bits : dict[str, list[int]]
        Per-tile bit arrays keyed by tile location strings (e.g. ``'X0Y1'``).

    Returns
    -------
    tuple[int, int]
        ``(num_columns, num_rows)``.

    Raises
    ------
    ValueError
        If any tile key does not match the ``XnYm`` format.
    """
    num_columns = 0
    num_rows = 0
    tile_coord_re: re.Pattern = re.compile(r"X(\d+)Y(\d+)")

    for tile_key in tile_bits:
        coords_match = tile_coord_re.fullmatch(tile_key)
        if coords_match is None:
            raise ValueError(f"Tile key '{tile_key}' does not match XnYm format")
        num_columns = max(int(coords_match.group(1)) + 1, num_columns)
        num_rows = max(int(coords_match.group(2)) + 1, num_rows)
    return num_columns, num_rows


def _build_hdl_strings(
    tile_bits_no_mask: dict[str, list[int]],
    spec_dict: dict,
    bitstream_format: BitstreamFormat,
) -> tuple[str, str]:
    """Build Verilog (.vh) and VHDL (.vhd) emulation bitstream constant strings.

    One define/constant per non-NULL tile; bit vector in descending index order
    (MSB first) as required by both HDL formats.

    Parameters
    ----------
    tile_bits_no_mask : dict[str, list[int]]
        Unmasked per-tile bit arrays.
    spec_dict : dict
        Must contain ``TileMap`` and ``FrameMap``.
    bitstream_format : BitstreamFormat
        Supplies frame dimensions and ``include_border_rows``.

    Returns
    -------
    tuple[str, str]
        ``(verilog_str, vhdl_str)``.
    """
    total_bits = (
        bitstream_format.max_frames_per_col * bitstream_format.frame_bits_per_row
    )

    verilog_str = ""
    vhdl_str = (
        "library IEEE;\nuse IEEE.STD_LOGIC_1164.ALL;\n\npackage emulate_bitstream is\n"
    )
    for tile_key, bits in tile_bits_no_mask.items():
        tile_type = spec_dict["TileMap"][tile_key]
        frame_map_entry = spec_dict["FrameMap"].get(tile_type, {})
        if tile_type == "NULL" or (
            len(frame_map_entry) == 0 and not bitstream_format.include_border_rows
        ):
            continue

        verilog_str += f"// {tile_key}, {tile_type}\n"
        verilog_str += f"`define Tile_{tile_key}_Emulate_Bitstream {total_bits}'b"

        vhdl_str += f"--{tile_key}, {tile_type}\n"
        vhdl_str += (
            f"constant Tile_{tile_key}_Emulate_Bitstream : std_logic_vector("
            f'{total_bits}-1 downto 0) := "'
        )

        bit_vec = "".join(map(str, reversed(bits)))
        verilog_str += bit_vec + "\n"
        vhdl_str += bit_vec + '";\n'
    vhdl_str += "end package emulate_bitstream;"
    return verilog_str, vhdl_str


def _build_csv_and_frame_data(
    tile_bits: dict[str, list[int]],
    spec_dict: dict,
    num_rows: int,
    num_columns: int,
    bitstream_format: BitstreamFormat,
) -> tuple[str, list[list[bytes]]]:
    """Build the CSV output string and per-column frame byte arrays.

    Border rows (top/bottom) are excluded by default per FABulous convention.

    Parameters
    ----------
    tile_bits : dict[str, list[int]]
        Masked per-tile bit arrays.
    spec_dict : dict
        Must contain ``TileMap``.
    num_rows : int
        Total row count from ``_compute_grid_size``.
    num_columns : int
        Total column count from ``_compute_grid_size``.
    bitstream_format : BitstreamFormat
        Supplies frame dimensions and ``include_border_rows``.

    Returns
    -------
    tuple[str, list[list[bytes]]]
        ``(csv_str, bit_array)`` where ``bit_array[col][frame]``
        holds the packed bytes for binary assembly.

    Raises
    ------
    SpecMissMatch
        If a non-NULL tile key is missing from the initialized tile bits.
    """
    csv_str = ""
    bit_array = [
        [b"" for _ in range(bitstream_format.max_frames_per_col)]
        for _ in range(num_columns)
    ]

    if bitstream_format.include_border_rows:
        logger.info("Border rows included in bitstream.")
        start_row = num_rows - 1
        stop_row = -1
    else:
        logger.info("Border rows excluded from bitstream (default).")
        start_row = num_rows - 2
        stop_row = 0

    for y in range(start_row, stop_row, -1):
        for x in range(num_columns):
            tile_key = f"X{x}Y{y}"
            tile_type = spec_dict["TileMap"].get(tile_key, "NULL")

            tile_csv = f"{tile_key},{tile_type},{x},{y}\n"

            for frame_idx in range(bitstream_format.max_frames_per_col):
                if tile_type == "NULL":
                    frame_bits = "0" * bitstream_format.frame_bits_per_row
                else:
                    if tile_key not in tile_bits:
                        raise SpecMissMatch(
                            "Tile location "
                            f"'{tile_key}' missing from initialized tile bits"
                        )
                    # Slice this frame's bits from the flat per-tile array and
                    # bit-reverse: the spec stores bits in frame-ascending order
                    # but we need them reversed within each row.
                    offset = bitstream_format.frame_bits_per_row * frame_idx
                    raw = tile_bits[tile_key][
                        offset : offset + bitstream_format.frame_bits_per_row
                    ]
                    frame_bits = "".join(map(str, raw))[::-1]

                tile_csv += (
                    f"frame{frame_idx},{frame_idx},"
                    f"{bitstream_format.frame_bits_per_row},{frame_bits}\n"
                )

                bit_array[x][frame_idx] += bitstring_to_bytes(frame_bits)

            csv_str += tile_csv + "\n"

    return csv_str, bit_array


def _build_binary_bitstream(
    bit_array: list[list[bytes]],
    num_columns: int,
    bitstream_format: BitstreamFormat,
) -> bytes:
    """Assemble binary bitstream: sync header + frame-select/data pairs + desync frame.

    Parameters
    ----------
    bit_array : list[list[bytes]]
        Packed frame bytes indexed as ``bit_array[col][frame]``.
    num_columns : int
        Total number of columns in the grid.
    bitstream_format : BitstreamFormat
        Wire-format settings.

    Returns
    -------
    bytes
        Complete binary bitstream.
    """
    # Add sync header at the start
    bitstream = bytes.fromhex(bitstream_format.sync_header_hex)

    # Add one (frame-select word + frame data) pair per frame per column.
    for col in range(num_columns):
        for frame_idx, frame_data in enumerate(bit_array[col]):
            # Frame-select word: column in top bits (address),
            # frame as one-hot bit (select).
            frame_select_word = (
                col
                << (
                    bitstream_format.frame_bits_per_row
                    - bitstream_format.frame_select_width
                )
            ) | (1 << frame_idx)
            bitstream += frame_select_word.to_bytes(
                math.ceil(bitstream_format.frame_bits_per_row / 8), byteorder="big"
            )
            # Frame data: packed config bits for this column/frame across all rows
            bitstream += frame_data

    # Desync frame signals end-of-bitstream.
    desync_frame = (1 << bitstream_format.desync_bit).to_bytes(
        math.ceil(bitstream_format.frame_bits_per_row / 8), byteorder="big"
    )
    bitstream += desync_frame
    return bitstream


def gen_bitstream(fasm_file: str, spec_file: str, bitstream_file: str) -> None:
    """Generate bitstream outputs (.csv, .vh, .vhd, .bin) from a FASM file and spec.

    Parameters
    ----------
    fasm_file : str
        Path to the FASM file.
    spec_file : str
        Path to the pickle spec file
        (``TileMap``, ``TileSpecs``, ``FrameMap``, ``ArchSpecs``, ...).
    bitstream_file : str
        Base output path; extension is replaced for each output format.

    Raises
    ------
    ValueError
        If the bitstream format is invalid or the grid exceeds
        ``FRAME_SELECT_WIDTH`` capacity.
    """
    canon_list = _parse_fasm_to_canon_list(fasm_file)
    if not canon_list:
        logger.warning(
            "FASM file contains no features; the generated bitstream will be all zeros."
        )

    with Path(spec_file).open("rb") as f:
        spec_dict = pickle.load(f)

    bitstream_format = _resolve_bitstream_format(spec_dict)

    # initialized zero-filled bit arrays for masked and unmasked bitstreams
    total_bits = (
        bitstream_format.max_frames_per_col * bitstream_format.frame_bits_per_row
    )
    tile_bits = {tile: [0] * total_bits for tile in spec_dict["TileMap"]}
    tile_bits_no_mask = {tile: [0] * total_bits for tile in spec_dict["TileMap"]}

    carry_mux_remaps = _apply_fasm_features(
        canon_list, spec_dict, tile_bits, tile_bits_no_mask, bitstream_format
    )

    num_columns, num_rows = _compute_grid_size(tile_bits)
    max_addressable_columns = 2**bitstream_format.frame_select_width
    if num_columns > max_addressable_columns:
        raise ValueError(
            f"Grid has {num_columns} columns but FRAME_SELECT_WIDTH "
            f"({bitstream_format.frame_select_width}) can only address "
            f"{max_addressable_columns}: column index would overflow "
            "the frame-select word"
        )
    verilog_str, vhdl_str = _build_hdl_strings(
        tile_bits_no_mask,
        spec_dict,
        bitstream_format,
    )
    csv_str, bit_array = _build_csv_and_frame_data(
        tile_bits,
        spec_dict,
        num_rows,
        num_columns,
        bitstream_format,
    )
    bitstream_bytes = _build_binary_bitstream(
        bit_array,
        num_columns,
        bitstream_format,
    )

    output_path = Path(bitstream_file)
    with output_path.with_suffix(".csv").open("w") as f:
        f.write(csv_str)
    with output_path.with_suffix(".vh").open("w") as f:
        f.write(verilog_str)
    with output_path.with_suffix(".vhd").open("w") as f:
        f.write(vhdl_str)
    with output_path.with_suffix(".bin").open("wb") as f:
        f.write(bitstream_bytes)

    if carry_mux_remaps:
        logger.warning(
            f"Remapped {carry_mux_remaps} carry mux feature(s) between I0mux and "
            "IOmux: the FASM and bitstream spec spell it differently. Your FABulous "
            "project or nextpnr might need an update."
        )


# Keep backwards-compatible function name
genBitstream = gen_bitstream


def bit_gen() -> None:
    """Command-line entry point for bitstream generation."""
    # Backwards compat: old CLI used `-genBitstream` (flag style)
    if len(sys.argv) > 1 and sys.argv[1] == "-genBitstream":
        sys.argv[1] = "genBitstream"

    parser = argparse.ArgumentParser(
        prog="bit_gen",
        description="FABulous bitstream generation tool",
        epilog=(
            "Examples:\n"
            "  bit_gen genBitstream design.fasm bitStreamSpec.bin out.bin\n"
            "  bit_gen -genBitstream design.fasm bitStreamSpec.bin out.bin  "
            "  # legacy form\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"bit_gen {_pkg_version('FABulous-bit-gen')}",
    )
    subparsers = parser.add_subparsers(dest="command")

    gen_parser = subparsers.add_parser(
        "genBitstream",
        help="Generate a bitstream from a FASM file and bitstream spec",
        description=(
            "Convert a FASM feature file and a FABulous bitstream spec (.bin) "
            "into a binary bitstream ready for fabric configuration."
        ),
        epilog=(
            "Example:\n"
            "  bit_gen genBitstream build/design.fasm "
            "../.FABulous/bitStreamSpec.bin build/design.bin\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    gen_parser.add_argument("fasm_file", help="Path to the input FASM file")
    gen_parser.add_argument(
        "spec_file", help="Path to the FABulous bitstream spec (.bin)"
    )
    gen_parser.add_argument(
        "output_file", help="Path to write the output bitstream (.bin)"
    )

    args = parser.parse_args()

    if args.command == "genBitstream":
        gen_bitstream(args.fasm_file, args.spec_file, args.output_file)
    else:
        parser.print_help()


if __name__ == "__main__":
    bit_gen()

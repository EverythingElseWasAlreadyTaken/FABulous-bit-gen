#!/usr/bin/env python

"""Bitstream-to-FASM inverter for FABulous FPGA fabrics.

Given a FABulous bitstream specification pickle and a binary bitstream file,
this module recovers the FASM configuration features that were encoded into
the bitstream.  This enables round-trip validation of bit_gen and supports
FPGA debug and reverse-engineering workflows.

Net recovery is intentionally out of scope.
"""

import argparse
import math
import pickle
import re
from pathlib import Path

from loguru import logger

# ── Bitstream format constants (mirrored from bit_gen) ───────────────────────

COLUMN_INDEX_BITS: int = 5
"""Bits used to encode the column index inside the frame-select word."""

FRAME_SELECT_BITS: int = 32
"""Width in bits of the frame-select word prepended to each frame."""

MAX_FRAMES_PER_COL: int = 20
"""Maximum number of frames per column in the FABulous bitstream format."""

SYNC_HEADER_HEX: str = "00AAFF01000000010000000000000000FAB0FAB1"
"""FABulous 20-byte sync header that opens every bitstream."""

DESYNC_BIT: int = 20
"""Bit position of the desync flag inside the 32-bit frame-select word."""

DESYNC_WORD: int = 1 << DESYNC_BIT
"""Integer value of the desync frame-select word (``1 << DESYNC_BIT``)."""


def _compute_grid_size(tile_map: dict) -> tuple[int, int]:
    """Compute grid dimensions from a tile map.

    Scans all keys in ``tile_map`` (expected to follow the ``XnYm`` naming
    convention) and returns the number of distinct columns and rows in the
    grid.  The counts are one-based, so a tile at ``X3Y2`` contributes to a
    grid of at least 4 columns and 3 rows.

    Parameters
    ----------
    tile_map : dict
        Mapping of tile location strings (e.g. ``'X0Y1'``) to tile types.

    Returns
    -------
    tuple[int, int]
        ``(num_columns, num_rows)`` — total width and height of the grid.

    Raises
    ------
    AttributeError
        If any tile key does not match the ``X<digits>Y<digits>`` pattern.
    """
    coords_re = re.compile(r"X(\d+)Y(\d+)")
    num_columns = 0
    num_rows = 0
    for key in tile_map:
        m = coords_re.match(key)
        if m is None:
            continue
        num_columns = max(int(m.group(1)) + 1, num_columns)
        num_rows = max(int(m.group(2)) + 1, num_rows)
    return num_columns, num_rows


def _parse_binary_bitstream(
    data: bytes,
    frame_data_size: int,
) -> dict[tuple[int, int], bytes]:
    """Parse a FABulous binary bitstream into per-frame byte blocks.

    Skips the 20-byte sync header, then reads alternating 4-byte
    frame-select words and ``frame_data_size``-byte frame data blocks until
    the desync frame word is encountered.

    The frame-select word encodes the column index in the five most-significant
    bits and sets the bit corresponding to the active frame index in bits 0–19.
    Decoding: ``col = (word >> 27) & 0x1F``,
    ``frame_idx = (word & 0xFFFFF).bit_length() - 1``.

    Parameters
    ----------
    data : bytes
        Raw binary bitstream bytes (the full ``.bin`` file contents).
    frame_data_size : int
        Expected number of bytes for each frame's data payload:
        ``num_interior_rows * ceil(FrameBitsPerRow / 8)``.

    Returns
    -------
    dict[tuple[int, int], bytes]
        Mapping of ``(col, frame_idx)`` to the raw frame data bytes.

    Raises
    ------
    ValueError
        If the bitstream does not start with the expected FABulous sync header.
    """
    sync_header = bytes.fromhex(SYNC_HEADER_HEX)
    if not data.startswith(sync_header):
        raise ValueError("Bitstream does not start with the FABulous sync header.")

    pos = len(sync_header)
    frame_map: dict[tuple[int, int], bytes] = {}

    while pos + 4 <= len(data):
        word = int.from_bytes(data[pos : pos + 4], "big")
        pos += 4

        if word == DESYNC_WORD:
            logger.debug("Desync word encountered — end of bitstream body.")
            break

        col = (word >> 27) & 0x1F
        lower_bits = word & 0xFFFFF
        frame_idx = lower_bits.bit_length() - 1

        frame_data = data[pos : pos + frame_data_size]
        pos += frame_data_size

        frame_map[(col, frame_idx)] = frame_data
        logger.debug(f"Parsed frame col={col} frame_idx={frame_idx}")

    return frame_map


def _reconstruct_tile_bits(
    frame_map: dict[tuple[int, int], bytes],
    spec_dict: dict,
    num_rows: int,
    num_columns: int,
) -> dict[str, list[int]]:
    """Reconstruct per-tile bit arrays from parsed frame data.

    Reverses the encoding performed by ``_build_csv_and_frame_data`` in
    bit_gen: for each ``(col, frame_idx)`` block, splits the frame data into
    per-row chunks, un-reverses the bit order, and writes the recovered bits
    into the corresponding tile's bit array at the correct offset.

    Parameters
    ----------
    frame_map : dict[tuple[int, int], bytes]
        Per-frame byte data as returned by ``_parse_binary_bitstream``.
    spec_dict : dict
        Bitstream specification dictionary.  Must contain ``ArchSpecs``
        (``FrameBitsPerRow``, ``MaxFramesPerCol``) and optionally
        ``include_border_rows``.
    num_rows : int
        Total number of rows in the grid (from ``_compute_grid_size``).
    num_columns : int
        Total number of columns in the grid (from ``_compute_grid_size``).

    Returns
    -------
    dict[str, list[int]]
        Per-tile bit arrays indexed by tile location string (e.g. ``'X0Y1'``).
        Only interior tiles are included (border rows excluded unless
        ``include_border_rows`` is set in ``spec_dict``).
    """
    frame_bits_per_row: int = spec_dict["ArchSpecs"]["FrameBitsPerRow"]
    max_frames_per_col: int = spec_dict["ArchSpecs"]["MaxFramesPerCol"]
    include_border_rows: bool = spec_dict.get("include_border_rows", False)

    if include_border_rows:
        interior_rows = list(range(num_rows - 1, 0, -1))
    else:
        interior_rows = list(range(num_rows - 2, 0, -1))

    bytes_per_row = math.ceil(frame_bits_per_row / 8)
    total_bits = frame_bits_per_row * max_frames_per_col

    tile_bits: dict[str, list[int]] = {
        f"X{x}Y{y}": [0] * total_bits
        for x in range(num_columns)
        for y in interior_rows
    }

    for (col, frame_idx), frame_data in frame_map.items():
        for row_pos, y in enumerate(interior_rows):
            chunk = frame_data[row_pos * bytes_per_row : (row_pos + 1) * bytes_per_row]
            bit_int = int.from_bytes(chunk, "big")
            # Restore full-width bit string and undo the [::-1] from encoding
            bit_str = f"{bit_int:b}".zfill(frame_bits_per_row)[::-1]
            tile_key = f"X{col}Y{y}"
            if tile_key in tile_bits:
                start = frame_idx * frame_bits_per_row
                tile_bits[tile_key][start : start + frame_bits_per_row] = [
                    int(b) for b in bit_str
                ]

    return tile_bits


# BelVectors maps (tile_loc, bel_id, base_name) -> {bit_index -> TileSpecs feature name}
BelVectors = dict[tuple[str, str, str], dict[int, str]]


def _parse_bel_spec(bel_file: str) -> BelVectors:
    """Parse a FABulous BEL spec file and extract vector CFG groups.

    Reads ``bel.v2.txt`` (or equivalent) and identifies CFG field groups that
    form multi-bit vectors.  A vector group is any set of CFG fields sharing
    the same base name where at least one member carries an explicit bit index
    (e.g. ``INIT[1]``, ``INIT[2]``, …).  An unindexed bare entry (e.g.
    ``INIT``) is treated as index 0.

    This is intentionally general: any CFG family with ``[n]`` members forms
    a group — not just ``INIT``.

    Parameters
    ----------
    bel_file : str
        Path to the BEL spec file (``bel.v2.txt``).

    Returns
    -------
    BelVectors
        Mapping of ``(tile_loc, bel_id, base_name)`` to a dict of
        ``{bit_index: TileSpecs_feature_name}``.  For example::

            ("X1Y1", "A", "INIT") -> {
                0: "A.INIT",
                1: "A.INIT[1]",
                ...
                15: "A.INIT[15]",
            }

    Raises
    ------
    FileNotFoundError
        If ``bel_file`` does not exist.
    """
    from collections import defaultdict

    indexed_re = re.compile(r"^(\w+)\[(\d+)\]$")

    result: BelVectors = {}
    current_tile: str | None = None
    current_bel_id: str | None = None
    cfg_fields: list[str] = []

    with Path(bel_file).open() as fh:
        for raw in fh:
            line = raw.strip()
            if line.startswith("BelBegin"):
                parts = line.split(",")
                current_tile = parts[1]
                current_bel_id = parts[2]
                cfg_fields = []
            elif line.startswith("CFG,") and current_tile is not None:
                cfg_fields.append(line[4:])
            elif (
                line == "BelEnd"
                and current_tile is not None
                and current_bel_id is not None
            ):
                tile: str = current_tile
                bel_id: str = current_bel_id
                # Group cfg_fields by base name
                base_entries: dict[str, list[tuple[int, str]]] = defaultdict(list)
                for field in cfg_fields:
                    m = indexed_re.match(field)
                    if m:
                        base_entries[m.group(1)].append((int(m.group(2)), field))
                    else:
                        # Bare name — treated as index 0 if indexed siblings exist
                        base_entries[field].append((-1, field))

                for base, entries in base_entries.items():
                    # Only form a vector when at least one entry has an explicit index
                    if not any(idx >= 0 for idx, _ in entries):
                        continue
                    group: dict[int, str] = {}
                    for idx, field in entries:
                        real_idx = 0 if idx == -1 else idx
                        # TileSpecs key: "{bel_id}.{field_as_written_in_bel_spec}"
                        group[real_idx] = f"{bel_id}.{field}"
                    result[(tile, bel_id, base)] = group

                current_tile = None
                current_bel_id = None
                cfg_fields = []

    logger.debug(f"Parsed {len(result)} BEL vector groups from {bel_file}")
    return result


def _recover_fasm_features(
    tile_bits: dict[str, list[int]],
    spec_dict: dict,
    bel_vectors: BelVectors | None = None,
) -> list[str]:
    """Recover active FASM feature names from reconstructed tile bit arrays.

    For each feature in ``TileSpecs``, checks whether every bit in the
    feature's bit map matches the corresponding reconstructed tile bit.  Only
    features with at least one expected ``"1"`` value are considered: features
    whose entire bit map is ``"0"`` cannot be distinguished from the default
    all-zero tile state and are skipped.

    When ``bel_vectors`` is provided, CFG fields that belong to a vector group
    (e.g. ``INIT[0]``–``INIT[15]``) are emitted as a single FASM vector line
    (``TileLoc.BelId.Base[max:0] = N'b{bits}``) instead of individual scalar
    lines.  A vector line is only emitted when at least one bit in the group
    is ``1``.

    Parameters
    ----------
    tile_bits : dict[str, list[int]]
        Per-tile bit arrays as returned by ``_reconstruct_tile_bits``.
    spec_dict : dict
        Bitstream specification dictionary.  Must contain ``TileSpecs``.
    bel_vectors : BelVectors | None, optional
        Vector group definitions as returned by ``_parse_bel_spec``.  When
        ``None`` (default), all features are emitted as individual scalar lines.

    Returns
    -------
    list[str]
        Sorted list of active FASM feature strings.  Scalar features use the
        format ``TileLoc.FeatureName``; vector features use the format
        ``TileLoc.BelId.Base[max:0] = N'b{bits}``.
    """
    tile_specs: dict = spec_dict.get("TileSpecs", {})
    active_features: list[str] = []

    # Build the set of TileSpecs feature names that belong to a vector group,
    # so the scalar loop below can skip them.
    vectorized: set[tuple[str, str]] = set()
    if bel_vectors:
        for bvkey, group in bel_vectors.items():
            for feat_name in group.values():
                vectorized.add((bvkey[0], feat_name))

    # ── Vector features ───────────────────────────────────────────────────────
    if bel_vectors:
        for (tile_loc, bel_id, base), group in bel_vectors.items():
            if tile_loc not in tile_bits or tile_loc not in tile_specs:
                continue
            bits = tile_bits[tile_loc]
            feat_map = tile_specs[tile_loc]

            max_idx = max(group)
            # Read the actual bit value for each index in the group
            idx_to_val: dict[int, int] = {}
            for idx, feat_name in group.items():
                if feat_name not in feat_map:
                    continue
                bit_map = feat_map[feat_name]
                for bit_pos, expected in bit_map.items():
                    if expected == "1":
                        idx_to_val[idx] = bits[bit_pos]
                        break  # each vector member has exactly one "1" bit

            if not idx_to_val or not any(idx_to_val.values()):
                continue  # all zeros — nothing to emit

            n_bits = max_idx + 1
            bit_str = "".join(
                str(idx_to_val.get(i, 0)) for i in range(max_idx, -1, -1)
            )
            active_features.append(
                f"{tile_loc}.{bel_id}.{base}[{max_idx}:0] = {n_bits}'b{bit_str}"
            )

    # ── Scalar features ───────────────────────────────────────────────────────
    for tile_loc, feat_map in tile_specs.items():
        if tile_loc not in tile_bits:
            continue
        bits = tile_bits[tile_loc]
        for feature_name, bit_map in feat_map.items():
            if bel_vectors and (tile_loc, feature_name) in vectorized:
                continue
            if not bit_map:
                continue
            # Skip features where every expected value is "0"; they are
            # indistinguishable from the unset default state.
            if all(v == "0" for v in bit_map.values()):
                continue
            # Feature is active iff every (bit_idx, expected_value) pair matches.
            if all(bits[idx] == int(val) for idx, val in bit_map.items()):
                active_features.append(f"{tile_loc}.{feature_name}")

    return sorted(active_features)


def negBitstream(
    spec_file: str,
    bitstream_file: str,
    output_fasm: str,
    bel_file: str | None = None,
) -> None:
    """Recover FASM features from a FABulous binary bitstream.

    Orchestrates the full bitstream-to-FASM inversion pipeline:

    1. Load the bitstream specification from the pickle file.
    2. Optionally parse the BEL spec to build vector group definitions.
    3. Compute grid dimensions from the tile map.
    4. Parse the binary bitstream into per-frame byte blocks.
    5. Reconstruct per-tile bit arrays from the frame data.
    6. Recover active FASM features by matching bit patterns against
       ``TileSpecs``.  When a BEL spec is provided, multi-bit CFG groups
       (e.g. ``INIT[15:0]``) are emitted as vector lines rather than
       individual scalar features.
    7. Write the sorted recovered features to the output FASM file.

    Parameters
    ----------
    spec_file : str
        Path to the pickle file containing the bitstream specification
        (``TileMap``, ``TileSpecs``, ``FrameMap``, ``ArchSpecs``, etc.).
    bitstream_file : str
        Path to the binary ``.bin`` bitstream file produced by ``bit_gen``.
    output_fasm : str
        Path for the output FASM file.  Created or overwritten.
    bel_file : str | None, optional
        Path to the BEL spec file (``bel.v2.txt``).  When provided, indexed
        CFG fields are grouped into FASM vector lines.  When ``None``
        (default), all features are emitted as individual scalar lines.

    Raises
    ------
    FileNotFoundError
        If ``spec_file``, ``bitstream_file``, or ``bel_file`` does not exist.
    pickle.UnpicklingError
        If ``spec_file`` cannot be deserialised as a valid pickle.
    ValueError
        If the bitstream does not start with the expected FABulous sync header.
    """
    with Path(spec_file).open("rb") as f:
        spec_dict = pickle.load(f)

    bel_vectors: BelVectors | None = None
    if bel_file is not None:
        bel_vectors = _parse_bel_spec(bel_file)
        logger.info(f"Loaded {len(bel_vectors)} BEL vector groups from {bel_file}")

    data = Path(bitstream_file).read_bytes()
    logger.info(f"Loaded bitstream: {len(data)} bytes from {bitstream_file}")

    frame_bits_per_row: int = spec_dict["ArchSpecs"]["FrameBitsPerRow"]
    include_border_rows: bool = spec_dict.get("include_border_rows", False)

    num_columns, num_rows = _compute_grid_size(spec_dict["TileMap"])
    logger.info(f"Grid: {num_columns} columns × {num_rows} rows")

    num_interior_rows = num_rows if include_border_rows else num_rows - 2
    frame_data_size = num_interior_rows * math.ceil(frame_bits_per_row / 8)
    logger.debug(f"Frame data size: {frame_data_size} bytes per frame")

    frame_map = _parse_binary_bitstream(data, frame_data_size)
    logger.info(f"Parsed {len(frame_map)} frames from bitstream")

    tile_bits = _reconstruct_tile_bits(frame_map, spec_dict, num_rows, num_columns)
    logger.info(f"Reconstructed bits for {len(tile_bits)} tiles")

    features = _recover_fasm_features(tile_bits, spec_dict, bel_vectors=bel_vectors)
    logger.info(f"Recovered {len(features)} active FASM features")

    output = "\n".join(features)
    if output:
        output += "\n"
    Path(output_fasm).write_text(output)
    logger.info(f"Written recovered FASM to {output_fasm}")


def neg_bit() -> None:
    """CLI entry point: recover FASM features from a FABulous binary bitstream.

    Usage
    -----
    ::

        neg_bit <spec_file> <bitstream_file> <output_fasm>
    """
    parser = argparse.ArgumentParser(
        prog="neg_bit",
        description="Recover FASM features from a FABulous binary bitstream.",
        epilog=(
            "Examples:\n"
            "  # Recover FASM from a bitstream:\n"
            "  neg_bit bitStreamSpec.bin top.bin recovered.fasm\n"
            "\n"
            "  # Round-trip check (recovered FASM should regenerate the same .bin):\n"
            "  neg_bit bitStreamSpec.bin top.bin recovered.fasm\n"
            "  bit_gen genBitstream recovered.fasm bitStreamSpec.bin roundtrip.bin\n"
            "  diff top.bin roundtrip.bin && echo OK"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "spec_file",
        help="Path to the bitstream specification pickle file (.bin).",
    )
    parser.add_argument(
        "bitstream_file",
        help="Path to the binary bitstream file (.bin) produced by bit_gen.",
    )
    parser.add_argument(
        "output_fasm",
        help="Output path for the recovered FASM file.",
    )
    parser.add_argument(
        "--bel-spec",
        default=None,
        metavar="BEL_FILE",
        help=(
            "Path to the BEL spec file (bel.v2.txt).  "
            "When provided, indexed CFG fields such as INIT are emitted as "
            "FASM vector lines (e.g. INIT[15:0] = 16'b...) "
            "instead of individual scalar features."
        ),
    )
    args = parser.parse_args()
    negBitstream(args.spec_file, args.bitstream_file, args.output_fasm, args.bel_spec)

#!/usr/bin/env python

"""Dump a FABulous bitstream specification pickle to YAML.

Useful for inspecting or diffing spec files without writing Python.
"""

import argparse
import pickle
import sys
from pathlib import Path

import yaml
from loguru import logger


def dump_spec(spec_file: str, output_file: str | None = None) -> None:
    """Load a bitstream spec pickle and write it as YAML.

    Parameters
    ----------
    spec_file : str
        Path to the bitstream specification pickle file.
    output_file : str | None
        Output path for the YAML file.  If ``None``, writes to stdout.

    Raises
    ------
    FileNotFoundError
        If ``spec_file`` does not exist.
    pickle.UnpicklingError
        If ``spec_file`` cannot be deserialised as a valid pickle.
    """
    with Path(spec_file).open("rb") as f:
        spec_dict = pickle.load(f)

    yaml_str = yaml.dump(
        spec_dict,
        default_flow_style=False,
        sort_keys=True,
        allow_unicode=True,
    )

    if output_file is not None:
        Path(output_file).write_text(yaml_str, encoding="utf-8")
        logger.info(f"Spec written to {output_file}")
    else:
        sys.stdout.write(yaml_str)


def dump_spec_cli() -> None:
    """CLI entry point: dump a bitstream spec pickle to YAML.

    Usage
    -----
    ::

        dump_spec <spec_file> [output_file]
    """
    parser = argparse.ArgumentParser(
        prog="dump_spec",
        description="Dump a FABulous bitstream specification pickle to YAML.",
        epilog=(
            "Examples:\n"
            "  # Print to stdout:\n"
            "  dump_spec bitStreamSpec.bin\n"
            "\n"
            "  # Write to file:\n"
            "  dump_spec bitStreamSpec.bin spec.yaml"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "spec_file",
        help="Path to the bitstream specification pickle file (.bin).",
    )
    parser.add_argument(
        "output_file",
        nargs="?",
        default=None,
        help="Output YAML file path.  Omit to write to stdout.",
    )
    args = parser.parse_args()
    dump_spec(args.spec_file, args.output_file)

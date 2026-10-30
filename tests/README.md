# Tests

```
tests/
  conftest.py               shared fixtures (see below)
  unit/                     fast, isolated tests against synthetic data
    test_bit_gen_utility.py   bitstring_to_bytes and other helpers
    test_cli.py               argparse / CLI entry point
    test_genBitstream.py      gen_bitstream pipeline, ~23 test classes
  integration/              slow, end-to-end tests against real designs
    test_full_bitstream.py    runs gen_bitstream and checks output files
  test_data/                reference inputs and golden outputs
    bitStreamSpec.bin         FABulous fabric spec (shared by all designs)
    bitStreamSpec.csv         same spec in CSV form
    sequential_16bit_en/
      top.fasm                input FASM
      reference/              golden outputs produced before any refactoring
        top.bin / .csv / .vh / .vhd
    bouncy_spi_screen_standard_fab/
      top.fasm
      top.json                Yosys synthesis netlist (context only)
      reference/
        top.bin / .csv / .vh / .vhd / .hex
    bouncy_spi_screen_complex_dff_fab/
      top.fasm
      top.json
      reference/
        top.bin / .csv / .vh / .vhd / .hex
```

## Running the tests

```bash
pytest                        # everything
pytest tests/unit/            # unit tests only (fast, ~1 s)
pytest tests/integration/     # integration tests only (slow, ~2 min)
pytest tests/unit/test_genBitstream.py::ClassName::test_name -v
```

## How the integration tests work

`TestFullBitstreamIntegration` and `TestFullBitstreamIntegrationEdgeCases`
are parametrized over all three designs via the session-scoped `design`
fixture in `conftest.py`.  Each test is therefore executed three times -
once per design - and its name will include the design name in brackets,
e.g. `test_bitstream_output_matches_expected[sequential_16bit_en]`.

For each run the test:
1. Writes the shared `bitStreamSpec.bin` spec into a temporary directory.
2. Calls `gen_bitstream(design.fasm_path, spec_file, output_base)`.
3. Compares the generated files against the corresponding files in
   `tests/test_data/<design>/reference/`.

`TestFullBitstreamIntegrationFaultCases` is not parametrized - it only
needs the shared spec to probe error paths (missing files, bad tile names,
etc.) and does not depend on design-specific inputs.

## Reference outputs

The files in `reference/` were produced by `bit_gen` before any refactoring
and must not be modified unless you intentionally change the output format.
They serve as the ground truth for regression detection.

The `.hex` files (present for the bouncy designs only) are byte-per-line hex
dumps of the bitstream, produced by a separate tool.  `bit_gen` does not
generate `.hex` output; these files are kept for context and future use.

## Fixtures (`conftest.py`)

| Fixture | Scope | Purpose |
|---|---|---|
| `minimal_spec_dict` | function | tiny synthetic spec for unit tests |
| `temp_output_dir` | function | `tmp_path` wrapper, auto-cleaned |
| `test_data_dir` | session | `Path` to `tests/test_data/` |
| `real_spec_dict` | session | deserialized `bitStreamSpec.bin` |
| `design` | session x3 | paths for one design (fasm + reference outputs) |
| `synthetic_fasm_lines` | function | hand-crafted `FasmLine` list |
| `synthetic_fasm_lines_with_clk` | function | includes a CLK line (filtered) |
| `synthetic_fasm_lines_invalid_tile` | function | tile absent from spec |

To add a new design, drop its files under `tests/test_data/<name>/` and
add the directory name to the `_DESIGNS` list in `conftest.py`.

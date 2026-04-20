"""Round-trip integration tests: bit_gen → neg_bit → bit_gen."""

from pathlib import Path
from types import SimpleNamespace

from fabulous_bit_gen.bit_gen import genBitstream
from fabulous_neg_bit.neg_bit import negBitstream


class TestRoundtrip:
    """Verify that neg_bit correctly inverts the bit_gen bitstream.

    Strategy: given the reference .bin produced by bit_gen, run neg_bit
    to recover a FASM file, then run bit_gen again on that recovered FASM
    and confirm the resulting bitstream is byte-for-byte identical to the
    reference.  This is the strongest possible correctness signal.
    """

    def test_roundtrip_bin_matches_reference(
        self,
        design: SimpleNamespace,
        tmp_path: Path,
    ) -> None:
        """neg_bit(reference.bin) → bit_gen → bytes match reference.bin."""
        spec_path = Path(__file__).parent.parent / "test_data" / "model_files" / "bitStreamSpec.bin"

        # Step 1: recover FASM from reference bitstream
        recovered_fasm = tmp_path / "recovered.fasm"
        negBitstream(str(spec_path), str(design.reference.bin), str(recovered_fasm))

        # Step 2: re-generate bitstream from recovered FASM
        re_generated = tmp_path / "re_generated.bin"
        genBitstream(str(recovered_fasm), str(spec_path), str(re_generated))

        # Step 3: compare bytes
        original = design.reference.bin.read_bytes()
        regenerated = re_generated.read_bytes()
        assert regenerated == original, (
            f"Round-trip failed for design '{design.name}': "
            f"regenerated bitstream ({len(regenerated)} bytes) differs from "
            f"reference ({len(original)} bytes)"
        )

    def test_neg_bit_output_is_non_empty(
        self,
        design: SimpleNamespace,
        tmp_path: Path,
    ) -> None:
        """Recovered FASM contains at least one feature line."""
        spec_path = Path(__file__).parent.parent / "test_data" / "model_files" / "bitStreamSpec.bin"
        recovered_fasm = tmp_path / "recovered.fasm"
        negBitstream(str(spec_path), str(design.reference.bin), str(recovered_fasm))

        lines = [
            ln.strip() for ln in recovered_fasm.read_text().splitlines() if ln.strip()
        ]
        assert len(lines) > 0, (
            f"neg_bit produced no features for design '{design.name}'"
        )

    def test_recovered_features_are_sorted(
        self,
        design: SimpleNamespace,
        tmp_path: Path,
    ) -> None:
        """Recovered FASM file lines are in sorted order."""
        spec_path = Path(__file__).parent.parent / "test_data" / "model_files" / "bitStreamSpec.bin"
        recovered_fasm = tmp_path / "recovered.fasm"
        negBitstream(str(spec_path), str(design.reference.bin), str(recovered_fasm))

        lines = [ln for ln in recovered_fasm.read_text().splitlines() if ln.strip()]
        assert lines == sorted(lines), (
            f"Recovered FASM for '{design.name}' is not in sorted order"
        )


class TestRoundtripWithVectors:
    """Round-trip test using the BEL spec for vector recovery."""

    BEL_FILE = str(
        Path(__file__).parent.parent / "test_data" / "model_files" / "bel.v2.txt"
    )

    def test_vector_roundtrip_bin_matches_reference(
        self,
        design: SimpleNamespace,
        tmp_path: Path,
    ) -> None:
        """neg_bit(--bel-spec, reference.bin) → bit_gen → bytes match reference."""
        spec_path = Path(__file__).parent.parent / "test_data" / "model_files" / "bitStreamSpec.bin"
        recovered_fasm = tmp_path / "recovered_vec.fasm"
        negBitstream(
            str(spec_path),
            str(design.reference.bin),
            str(recovered_fasm),
            bel_file=self.BEL_FILE,
        )

        re_generated = tmp_path / "re_generated_vec.bin"
        genBitstream(str(recovered_fasm), str(spec_path), str(re_generated))

        original = design.reference.bin.read_bytes()
        regenerated = re_generated.read_bytes()
        assert regenerated == original, (
            f"Vector round-trip failed for design '{design.name}'"
        )

    def test_vector_output_contains_init_vector_lines(
        self,
        design: SimpleNamespace,
        tmp_path: Path,
    ) -> None:
        """Recovered FASM with bel spec contains INIT[15:0] = 16'b...

        lines.
        """
        spec_path = Path(__file__).parent.parent / "test_data" / "model_files" / "bitStreamSpec.bin"
        recovered_fasm = tmp_path / "recovered_vec.fasm"
        negBitstream(
            str(spec_path),
            str(design.reference.bin),
            str(recovered_fasm),
            bel_file=self.BEL_FILE,
        )
        lines = recovered_fasm.read_text().splitlines()
        vector_lines = [ln for ln in lines if "INIT[15:0] = 16'b" in ln]
        assert len(vector_lines) > 0, (
            f"No INIT vector lines found in recovered FASM for '{design.name}'"
        )

    def test_vector_output_has_no_individual_init_bits(
        self,
        design: SimpleNamespace,
        tmp_path: Path,
    ) -> None:
        """When bel spec is used, individual A.INIT / A.INIT[n] lines are absent."""
        spec_path = Path(__file__).parent.parent / "test_data" / "model_files" / "bitStreamSpec.bin"
        recovered_fasm = tmp_path / "recovered_vec.fasm"
        negBitstream(
            str(spec_path),
            str(design.reference.bin),
            str(recovered_fasm),
            bel_file=self.BEL_FILE,
        )
        import re

        scalar_init_re = re.compile(r"\.(INIT|INIT\[\d+\])$")
        lines = recovered_fasm.read_text().splitlines()
        scalar_init_lines = [ln for ln in lines if scalar_init_re.search(ln)]
        assert scalar_init_lines == [], (
            f"Unexpected scalar INIT lines in '{design.name}': {scalar_init_lines[:3]}"
        )

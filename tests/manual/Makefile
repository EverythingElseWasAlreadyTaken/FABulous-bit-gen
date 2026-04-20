REPO_ROOT  := $(shell cd ../.. && pwd)
TEST_DATA  := $(REPO_ROOT)/tests/test_data
MODEL      := $(TEST_DATA)/model_files
SPEC       := $(MODEL)/bitStreamSpec.bin
BEL_SPEC   := $(MODEL)/bel.v2.txt

DESIGNS := \
    sequential_16bit_en \
    bouncy_spi_screen_standard_fab \
    bouncy_spi_screen_complex_dff_fab

DESIGN ?= sequential_16bit_en

OUT    := $(REPO_ROOT)/tests/manual/output/$(DESIGN)
FASM   := $(TEST_DATA)/$(DESIGN)/top.fasm
REF    := $(TEST_DATA)/$(DESIGN)/reference/top.bin

UV     := uv run --directory $(REPO_ROOT)

.PHONY: all $(DESIGNS) clean

all: $(DESIGNS)

$(DESIGNS):
	@$(MAKE) --no-print-directory roundtrip DESIGN=$@

roundtrip: $(OUT)/step1.bin $(OUT)/recovered_scalar.fasm $(OUT)/recovered_vectors.fasm $(OUT)/step5_roundtrip.bin
	@echo
	@echo "=== Round-trip check ==="
	@cmp -s $(OUT)/step1.bin $(REF) \
	    && echo "step1.bin == reference: OK" \
	    || echo "step1.bin != reference: MISMATCH"
	@cmp -s $(OUT)/step5_roundtrip.bin $(OUT)/step1.bin \
	    && echo "roundtrip == step1.bin: OK" \
	    || echo "roundtrip != step1.bin: MISMATCH"
	@echo
	@echo "=== Files ==="
	@ls -lh $(OUT)

$(OUT)/step1.bin: $(FASM) $(SPEC)
	@echo "--- bit_gen: $(DESIGN)/top.fasm → step1.bin"
	@mkdir -p $(OUT)
	@$(UV) bit_gen genBitstream $(FASM) $(SPEC) $@

$(OUT)/recovered_scalar.fasm: $(OUT)/step1.bin
	@echo "--- neg_bit (scalar): step1.bin → recovered_scalar.fasm"
	@$(UV) neg_bit $(SPEC) $< $@
	@echo "    $$(wc -l < $@) features recovered"

$(OUT)/recovered_vectors.fasm: $(OUT)/step1.bin
	@echo "--- neg_bit (vectors): step1.bin → recovered_vectors.fasm"
	@$(UV) neg_bit --bel-spec $(BEL_SPEC) $(SPEC) $< $@
	@echo "    $$(wc -l < $@) features recovered"

$(OUT)/step5_roundtrip.bin: $(OUT)/recovered_scalar.fasm
	@echo "--- bit_gen: recovered_scalar.fasm → step5_roundtrip.bin"
	@$(UV) bit_gen genBitstream $< $(SPEC) $@

clean:
	rm -rf $(REPO_ROOT)/tests/manual/output

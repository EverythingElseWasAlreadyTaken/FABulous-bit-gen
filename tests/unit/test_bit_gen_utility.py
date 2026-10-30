"""Tests for bitstring_to_bytes utility function."""

import pytest

from fabulous_bit_gen.bit_gen import bitstring_to_bytes


class TestBitstringToBytes:
    """Test suite for bitstring_to_bytes function."""

    def test_8bit_string(self) -> None:
        """Test conversion of 8-bit binary string."""
        result = bitstring_to_bytes("10110101")
        assert result == b"\xb5"

    def test_16bit_string(self) -> None:
        """Test conversion of 16-bit binary string."""
        result = bitstring_to_bytes("1011010110110101")
        assert result == b"\xb5\xb5"

    def test_7bit_nonaligned(self) -> None:
        """Test conversion of 7-bit (non-aligned) binary string."""
        result = bitstring_to_bytes("1011010")
        assert result == b"\x5a"
        assert len(result) == 1

    def test_9bit_nonaligned(self) -> None:
        """Test conversion of 9-bit (non-aligned) binary string."""
        result = bitstring_to_bytes("101101011")
        assert len(result) == 2

    def test_single_bit_one(self) -> None:
        """Test conversion of single '1' bit."""
        result = bitstring_to_bytes("1")
        assert result == b"\x01"

    def test_single_bit_zero(self) -> None:
        """Test conversion of single '0' bit."""
        result = bitstring_to_bytes("0")
        assert result == b"\x00"

    def test_all_zeros(self) -> None:
        """Test conversion of string with all zeros."""
        result = bitstring_to_bytes("00000000")
        assert result == b"\x00"

    def test_all_ones(self) -> None:
        """Test conversion of string with all ones."""
        result = bitstring_to_bytes("11111111")
        assert result == b"\xff"

    def test_leading_zeros(self) -> None:
        """Test that leading zeros are preserved correctly."""
        result = bitstring_to_bytes("00001111")
        assert result == b"\x0f"

    def test_empty_string_raises_valueerror(self) -> None:
        """Test that empty string raises ValueError."""
        with pytest.raises(
            ValueError, match=r"invalid literal for int\(\) with base 2"
        ):
            bitstring_to_bytes("")

    def test_non_binary_chars_raises_valueerror(self) -> None:
        """Test that non-binary characters raise ValueError."""
        with pytest.raises(
            ValueError, match=r"invalid literal for int\(\) with base 2"
        ):
            bitstring_to_bytes("abc")

    def test_mixed_binary_nonbinary_raises_valueerror(self) -> None:
        """Test that mixed binary and non-binary chars raise ValueError."""
        with pytest.raises(
            ValueError, match=r"invalid literal for int\(\) with base 2"
        ):
            bitstring_to_bytes("10a1")


class TestBitstringToBytesEdgeCases:
    """Edge case tests for bitstring_to_bytes function."""

    def test_very_long_bitstring(self) -> None:
        """Test conversion of very long bitstring (1000 bits)."""
        bitstring = "1" * 1000
        result = bitstring_to_bytes(bitstring)
        assert len(result) == 125

    def test_1000_zeros(self) -> None:
        """Test conversion of 1000 zeros."""
        bitstring = "0" * 1000
        result = bitstring_to_bytes(bitstring)
        assert len(result) == 125
        assert all(b == 0 for b in result)

    def test_alternating_bits(self) -> None:
        """Test alternating bit pattern."""
        bitstring = "10" * 100
        result = bitstring_to_bytes(bitstring)
        assert len(result) == 25

    def test_64_bit_string(self) -> None:
        """Test 64-bit string (8 bytes)."""
        bitstring = "1111111100000000111111110000000011111111000000001111111100000000"
        result = bitstring_to_bytes(bitstring)
        assert len(result) == 8

    def test_128_bit_string(self) -> None:
        """Test 128-bit string (16 bytes)."""
        bitstring = "1" * 128
        result = bitstring_to_bytes(bitstring)
        assert len(result) == 16
        assert all(b == 0xFF for b in result)

    def test_bitstring_with_whitespace_raises_valueerror(self) -> None:
        """Test that bitstring with whitespace raises ValueError."""
        with pytest.raises(
            ValueError, match=r"invalid literal for int\(\) with base 2"
        ):
            bitstring_to_bytes("1010 1010")

    def test_bitstring_with_newline_raises_valueerror(self) -> None:
        """Test that bitstring with newline raises ValueError."""
        with pytest.raises(
            ValueError, match=r"invalid literal for int\(\) with base 2"
        ):
            bitstring_to_bytes("1010\n1010")

    def test_bitstring_with_tab_raises_valueerror(self) -> None:
        """Test that bitstring with tab raises ValueError."""
        with pytest.raises(
            ValueError, match=r"invalid literal for int\(\) with base 2"
        ):
            bitstring_to_bytes("1010\t1010")

    def test_bitstring_with_2_raises_valueerror(self) -> None:
        """Test that bitstring with '2' raises ValueError."""
        with pytest.raises(
            ValueError, match=r"invalid literal for int\(\) with base 2"
        ):
            bitstring_to_bytes("1020")

    def test_bitstring_with_minus_raises_valueerror(self) -> None:
        """Test that bitstring with '-' raises ValueError."""
        with pytest.raises(
            ValueError, match=r"invalid literal for int\(\) with base 2"
        ):
            bitstring_to_bytes("1-0-1")

    def test_bitstring_with_plus_raises_valueerror(self) -> None:
        """Test that bitstring with '+' raises ValueError."""
        with pytest.raises(
            ValueError, match=r"invalid literal for int\(\) with base 2"
        ):
            bitstring_to_bytes("1+0+1")

    def test_bitstring_unicode_chars_raises_valueerror(self) -> None:
        """Test that bitstring with unicode chars raises ValueError."""
        with pytest.raises(
            ValueError, match=r"invalid literal for int\(\) with base 2"
        ):
            bitstring_to_bytes("10\u03b101")

    def test_single_byte_boundary(self) -> None:
        """Test at single byte boundary (8 bits)."""
        result = bitstring_to_bytes("11110000")
        assert result == b"\xf0"

    def test_two_byte_boundary(self) -> None:
        """Test at two byte boundary (16 bits)."""
        result = bitstring_to_bytes("1111000011110000")
        assert result == b"\xf0\xf0"

    def test_four_byte_boundary(self) -> None:
        """Test at four byte boundary (32 bits)."""
        result = bitstring_to_bytes("11110000111100001111000011110000")
        assert result == b"\xf0\xf0\xf0\xf0"

    def test_off_by_one_bit(self) -> None:
        """Test string with length just over byte boundary."""
        result = bitstring_to_bytes("111111111")
        assert len(result) == 2

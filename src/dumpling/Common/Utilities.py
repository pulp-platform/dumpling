# Manuel Eggimann <meggimann@iis.ee.ethz.ch>
#
# Copyright (C) 2023 ETH Zürich
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Union
from bitstring import BitArray, Bits


def pp_binstr(bits: Union[str, Bits]) -> str:
    """Generates a pretty print version of a binary string in compact format.

    The default pretty print notation of the `bitstring` package uses an
    unintuitive order when using lb0 mode. This function returns string using
    compact MSB(left-to-LSB(right) notation using hex notation, if necessary,
    padded with a binary string in case the bitstring is not dividable by four.

    Args:
        bits (Union[str, Bits]): A string of '0' and '1'

    Returns:
        str: A compact representation of the binary string using hex and (if not
        multiple of 4 bits) binary notation
    """
    bits = BitArray(bits)
    if len(bits) < 7:
        return f"0b{bits.bin}"
    else:
        num_hex_digits = len(bits) // 4
        padding_bits = len(bits) % 4
        str_parts = []
        str_parts.append(f"0x{bits[0:num_hex_digits*4].hex}")
        if padding_bits > 0:
            str_parts.append(f"0b{bits[num_hex_digits*4:].bin}")
            return "[" + ", ".join(reversed(str_parts)) + "]"
        else:
            return str_parts[0]

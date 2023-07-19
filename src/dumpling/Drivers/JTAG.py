# Manuel Eggimann <meggimann@iis.ee.ethz.ch>
#
# Copyright (C) 2020-2022 ETH Zürich
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

""" Provides the JTAGDriver class for high lever JTAG FSM vector bitbanging """

from typing import List, Optional

import bitstring
from bitstring import BitArray

from dumpling.JTAGTaps.JTAGTap import JTAGTap, JTAGRegister

from dumpling.Common.VectorBuilder import NormalVector

bitstring.lsb0 = True  # Enables the experimental mode to index LSB with 0 instead of the MSB (see thread https://github.com/scott-griffiths/bitstring/issues/156)
from dumpling.Common.VectorBuilder import VectorBuilder

from dumpling.Common.Utilities import pp_binstr


class JTAGDriver:
    """
    The `JTAGDriver` class provides convenience functions to interact with a specific JTAG chain.

    The driver instance requires a `VectorBuilder` instance in order generate vector in the required format.

    The JTAGDriver expects the VectorBuilder to contain pin declarations with the following *logical name* (the
    physical name is not relevant for the driver):

    - 'tck': The jtag clock pin
    - 'trst': The test logic reset pin
    - 'tms': The test mode select pin
    - 'tdi': The test data in pin
    - 'tdo': The test data out pin

    For the tck, tms, trst and tms pins the driver will write vectors containing the '0' and '1' on state character to
    denote application of logic low and logic high (or no-clk and clk in the case of TCK). The state character for the
    tdo pin can either be '0' for sampling and comparison with logic low, '1' for sampling and comparison with logic
    high or 'X' if the output of TDO should be 'don't care' for the current vector.

    After instantiation of the driver, the JTAG chain configuration needs to be configured by adding JTAGTap
    instances in the order they are hooked up the JTAG chain. This enables the JTAGDriver class and the JTAGTap
    instances that interact with this driver to provide high-level functions for JTAG interaction without needing to
    now the number of additional TAPs on the same chain.

    E.g.::

       driver = JTAGDriver(my_vector_builder)
       riscv_debug_tap = RISCVDebugTap(driver)
       driver.add_tap(risc_debug_tap)
       driver.add_tap(JTAGTap(ir_size=5, driver=driver)) #Add some dummy tap

       #Start using the taps or the driver driver directly
       vectors = risc_debug_tap.halt_harts(...)
       vectors += driver.jtag_set_dr(...)
       writer.write_vectors(vectors)

    For TAPs that we don't need to interact with you can just add instantiations of the `JTAGTap` base class as a dummy
    tap to make sure the driver accounts for the additional flip-flops in the chains IR and DR path. Unless otherwise
    stated, the high-level functions provided by the individual taps will always select the BYPASS register for all
    other taps except the one that should be currently used.

    Args:
        vector_builder(VectorBuilder): A handle to a configured vector builder.

    """

    vector_builder: VectorBuilder
    chain: List[JTAGTap]

    def __init__(self, vector_builder: VectorBuilder):
        self.vector_builder = vector_builder
        self.chain = []

    def set_jtag_default_values(self) -> None:
        """
        Apply default (idle) values to the jtag pins.

        This function will only alter the state of the jtag pins in the underlying vector builder without generating any
        vectors yet. It will not affect any non-jtag pin that might be present in the vector_builder instance.

        Returns:

        """
        self.vector_builder.tck = "0"
        self.vector_builder.trst = "1"
        self.vector_builder.tms = "0"
        self.vector_builder.tdi = "0"
        self.vector_builder.tdo = "X"

    def add_tap(self, jtag_tap: JTAGTap) -> None:
        """
        Adds a new JTAG TAP to the chain controlled by this driver instance.

        The TAPs are supposed to be added in the same order that the TDI signal passes through them. E.g. if the TDI
        enters the chip, passes TAP1, leaves TAP1 through it's TDO, enters TAP2 through the TDI and finally leaves the
        chip through TDO, register the TAPs in the following order::

          self.add_tap(TAP1)
          self.add_tap(TAP2)


        Args:
            jtag_tap: The JTAG TAP to add to the chain.

        Returns:

        """
        self.chain.insert(0, jtag_tap)

    def jtag_idle_vector(
        self, repeat: int = 1, comment: Optional[str] = None
    ) -> NormalVector:
        """
        Returns a single vector with the given 'repeat' value to keep the JTAG interface idle.

        The vector will turn off the JTAG clock and keep the TMS pin low.

        Args:
            repeat: The number of cycles to repeat the idle vector
            comment(str): An optional comment to annotate the generated vector with

        Returns:
            Mapping: A single vector
        """
        self.set_jtag_default_values()
        return self.vector_builder.vector(repeat=repeat, comment=comment)

    def jtag_idle_vectors(self, count: int = 1) -> List[NormalVector]:
        """
        Returns a list of JTAG idle vectors of the given length.

        This function does basically the same as jtag_idle_vector but will just return a list with the required
        number of jtag idle vectors as element instead of making use of the repeat value of the vector.

        Args:'dumpling.Drivers.JTAGDriver'
            count: The number of jtag idle vectors to return

        Returns:
            List[Mapping]: A list of vectors

        """
        return count * [self.jtag_idle_vector()]

    def jtag_reset(self) -> List[NormalVector]:
        """
        Returns vectors to reset the jtag interface.


        Returns:
             List[Mapping]: A list of vectors

        """
        vectors = []
        self.set_jtag_default_values()
        self.vector_builder.trst = "0"
        vectors += [self.vector_builder.vector(comment="JTAG Reset")]
        vectors += 9 * [self.vector_builder.vector()]
        self.vector_builder.trst = "1"
        self.vector_builder.tck = "1"
        self.vector_builder.tms = "0"
        vectors += 10 * [self.vector_builder.vector()]
        return vectors

    def jtag_goto_shift_dr(self, comment: Optional[str] = None) -> List[NormalVector]:
        """
        Return vectors to enter the Shifr DR state.

        Args:
            comment(str): An optional comment with which to annotate the generated vectors.

        Returns:
            List[Mapping]: A list of vectors
        """
        vectors = []
        self.set_jtag_default_values()
        self.vector_builder.tms = "1"
        self.vector_builder.tck = "0"  # Always change TMS and TDI one cycle earlier
        vectors.append(self.vector_builder.vector(comment=comment))
        self.vector_builder.tck = "1"
        self.vector_builder.tms = "0"
        vectors.append(self.vector_builder.vector())
        vectors.append(self.vector_builder.vector(comment="Goto shift DR"))
        return vectors

    def jtag_goto_shift_ir(self, comment: Optional[str] = None) -> List[NormalVector]:
        """
        Return vectors to enter the Shifr IR state.

        Args:
            comment(str): An optional comment with which to annotate the generated vectors.

        Returns:
            List[Mapping]: A list of vectors
        """
        vectors = []
        self.set_jtag_default_values()
        self.vector_builder.tms = "1"
        self.vector_builder.tck = "0"  # Always change TMS and TDI one cycle earlier
        vectors.append(self.vector_builder.vector(comment=comment))
        self.vector_builder.tck = "1"
        vectors.append(self.vector_builder.vector())
        self.vector_builder.tms = "0"
        vectors.append(self.vector_builder.vector())
        vectors.append(self.vector_builder.vector(comment="Goto shift IR"))
        return vectors

    def jtag_shift(
        self,
        chain: str,
        expected_chain: Optional[str] = None,
        comment: Optional[str] = None,
        noexit: bool = False,
    ) -> List[NormalVector]:
        """
        Shift the given value into the JTAG chain optionally matching with an expected value during readout.

        This function expects the JTAG chain to already be in either the shift IR or the shift DR state. The binary
        string supplied with the `chain` argument is shifted into the jtag chain while the shift output is optionally
        compared with the `expected_chain` value. Unless `noexit` is True, after all the data in `chain`, thus after
        len(chain) JTAG cycles has been shifted into the chain, the shift IR/shift DR state is left and the chain is
        brought into "Run Test Idle" state.

        The data is shifted in the order they appear in the `chain` and `expected_chain` string (thus left to right).

        Args:
            chain(str): A string containing '0' and '1' that should be shifted into the chain.
            expected_chain(str): None, or a string containing '0', '1' and 'X' that should be compared with the data
            shifted out of the chain.
            comment(str): An optional comment with which to annotate the generated vectors
            noexit(bool): If True, don't exit the shift state, otherwise the last few vectors returned by this
                function put the JTAG FSM back into "Run Test Idle"

        Returns:
            List[Mapping]: A list of vectors
        """
        self.set_jtag_default_values()
        self.vector_builder.tck = "1"
        self.vector_builder.tms = "0"
        vectors = []
        if comment is None:
            comment = ""
        comment += "/Start shifting. "
        # Shift in the values
        for idx, bit in enumerate(chain):
            self.vector_builder.tdi = bit
            # Check if expected_chain != None and doesn't only contain don't care
            if expected_chain and not all(
                map(lambda x: x in ["x", "X"], expected_chain)
            ):
                self.vector_builder.tdo = expected_chain[idx]
            if idx == len(chain) - 1 and not noexit:
                self.vector_builder.tms = "1"
            vectors.append(
                self.vector_builder.vector(
                    comment=comment
                    + "Shift bit {}".format(bit)
                    + (
                        " expecting tdo {}".format(expected_chain[idx])
                        if expected_chain
                        else ""
                    )
                )
            )
            comment = ""  # Only write full comment for first shift cycle

        # Update and go to idle
        if not noexit:
            vectors.append(self.vector_builder.vector(comment="goto Update DR/IR"))
            self.vector_builder.tms = "0"
            vectors.append(self.vector_builder.vector(comment="goto run test idle"))
            vectors.append(self.vector_builder.vector(comment="idle"))
        return vectors

    def jtag_set_ir(
        self, tap: JTAGTap, ir_value: str, comment: Optional[str] = None
    ) -> List[NormalVector]:
        """Sets the IR value LSB first of the given JTAG tap while putting all other taps of the chain into BYPASS mode.

        The ir_value is a binary string and shifted LSB first (thus right to left) as oposed to the `jtag_shift`
        function. Since the driver is aware of the additional TAPs besided the targeted TAP, the IR length of
        additional JTAG TAPs in the chain do not have to be accounted for when chosing the IR_VALUE. The driver will
        automatically pad the `ir_value` with the appropriate bits to put all other TAPs before and/or after the
        target TAP into bypass mode.

        Important: ir_value is supposed to be in MSB-first order. I.e.
        ir_value[0] must be the MSB. The function internally reverses the order
        for LSB-first streamout.

        Args:
            tap(JTAGTap): The TAP for which the ir_value should be set.
            ir_value(str): The IR value as a binary string containing '0's and '1's. The value is shifted LSB first.
            comment(str): An optional comment with which to annotate the generated vectors

        Returns:
            List[Mapping]: A list of vectors

        """
        if comment is None:
            comment = ""
        comment += "/Set IR of tap {} to {}".format(
            tap.name, pp_binstr(BitArray(bin=ir_value))
        )
        vectors = self.jtag_goto_shift_ir(comment)
        chain = ""
        for chain_elem in self.chain:
            if chain_elem == tap:
                # JTAG is LSB first
                chain += ir_value[::-1]
            else:
                # JTAG is LSB first
                chain += chain_elem.reg_bypass.IR_value[::-1]

        # Now we are in Shift IR state
        vectors += self.jtag_shift(chain, comment=comment)
        return vectors

    def jtag_set_dr(
        self,
        tap: JTAGTap,
        dr_value: str,
        expected_dr_value: Optional[str] = None,
        comment: Optional[str] = None,
        noexit: bool = False,
    ) -> List[NormalVector]:
        """
        Sets the DR value LSB first of the given JTAG tap. If expected_dr_value is not None, the read value will be matched against it. This function assumes that all other taps are in bypass mode.


        The dr_value is written LSB first and must only contain the bits that should actually end up in the DR of the
        `tap`. The driver assumes that all taps except of the targeted one have been brought into bypass mode (as is the
        behavior of the `jtag_set_ir` function). The driver will take care of padding the desired dr_value with the
        appropriate number of '0's to account for the additional flip-flops of the additional TAPs before and/or after
        the targeted TAP in the chain. The data shifted out of the target DR is compared with the optional
        `expected_dr_vaue`. After the shift operation, the JTAG FSM is brought back into "Run Test Idle" state unless
        `noexit` is True.

        Important: Both, dr_value and expected_dr_value are expected in MSB first order. I.e. dr_value[0] must be the MSB.

        Args:
            tap(JTAGTap): The TAP for which the DR value should be
            dr_value(str): A binary string to shift into the target TAP LSB first
            expected_dr_value(str): An optional binary string with which to compare the DR_Value that was shifted out of the chain.
            comment(str): An optional comment with which to annotate the generated vectors
            noexit(bool): If True, don't exit the shift state, otherwise the last few vectors returned by this
                function put the JTAG FSM back into "Run Test Idle"

        Returns:
            List[Mapping]: A list of vectors
        """
        if comment is None:
            comment = ""
        comment += "/Set DR of tap {} to {}".format(
            tap.name, pp_binstr(BitArray(bin=dr_value))
        )
        if expected_dr_value and not all(
            map(lambda x: x in ["x", "X"], expected_dr_value)
        ):
            comment += " expecting to read {}".format(expected_dr_value)
        vectors = self.jtag_goto_shift_dr(comment)
        # Now we are in Shift DR state
        chain = ""
        for chain_elem in self.chain:
            if chain_elem == tap:
                # JTAG is LSB first, so we have to reverse the order
                chain += dr_value[::-1]
            else:
                chain += "0"

        expected_chain = ""
        if expected_dr_value:
            for chain_elem in self.chain:
                if chain_elem == tap:
                    # JTAG is LSB first, so we have to reverse the order
                    expected_chain += expected_dr_value[::-1]
                else:
                    expected_chain += "X"
        vectors += self.jtag_shift(chain, expected_chain, comment, noexit)
        return vectors

    def read_reg(
        self,
        tap: JTAGTap,
        reg: JTAGRegister,
        reg_length: int,
        expected_value: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> List[NormalVector]:
        """
        Read a given JTAG register from a targeted tap and match the value with an expected one.

        This function generates the vectors to read from a specific jtag register of a TAP. An all zeros string
        is shifted into the chain while reading the DR value of length `reg_length`. The expected_value is compared
        with the data from the JTAG chain LSB first. The function takes care of selecting the desired register by
        shifting the correct IR value and putting all other taps in the same chain in BYPASS mode. The
        `expected_value` must only contain bits that should actually match the bits of the desired register.
        Additional zero padding for the bypassed TAPs is already accounted for internally.

        Args:
            tap(JTAGTap): The tap from which to read.
            reg(JTAGRegister): An JTAG register within the specified tap from which to read.
            reg_length(int): The number of bits to read from the JTAG register.
            expected_value(str): An optional expected DR_value (MSB-to-LSB) with which the DR value read is compared.
            comment(str): An optional comment with which to annotate the generated vectors

        Returns:
            List[Mapping]: A list of vectors
        """
        vectors = []
        if not reg in tap.registers:
            raise ValueError(
                "The supplied JTAG register does belong to the supplied JTAG tap"
            )
        vectors += self.jtag_set_ir(tap, reg.IR_value, comment=comment)
        vectors += self.jtag_set_dr(
            tap,
            dr_value=reg_length * "0",
            expected_dr_value=expected_value,
            comment="Read value from DR. Expected value: {}".format(expected_value),
        )
        return vectors

    def write_reg(
        self, tap: JTAGTap, reg: JTAGRegister, value: str, comment: Optional[str] = None
    ) -> List[NormalVector]:
        """
        Write the desired `value` to a given JTAG register of a targeted tap.

        This function generates the vectors to write to a specific jtag register of a TAP. The data is shifted LSB first
        (the `value` string is thus shifted right to left). The function takes care of selecting the desired register by
        shifting the correct IR value and putting all other taps in the same chain in BYPASS mode. The `value` must only
        contain bits that should actually be written to the desired register. Additional zero padding for the bypassed
        TAPs is already performed internally.

        Args:
            tap(JTAGTap): The tap from which to read.
            reg(JTAGRegister): An JTAG register within the specified tap from which to read.
            value(str): The value to be shifted into the chosen JTAG register, (MSB-to-LSB)
            comment(str): An optional comment with which to annotate the generated vectors

        Returns:
            List[Mapping]: A list of vectors
        """
        vectors = []
        if not reg in tap.registers:
            raise ValueError(
                "The supplied JTAG register does belong to the supplied JTAG tap"
            )
        vectors += self.jtag_set_ir(tap, reg.IR_value, comment=comment)
        vectors += self.jtag_set_dr(
            tap, dr_value=value, comment="Write value {} to DR.".format(value)
        )
        return vectors

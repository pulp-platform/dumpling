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
import os
from enum import Enum
from typing import List, Optional
from tqdm import tqdm


import bitstring
from dumpling.Common.ElfParser import ElfParser
from dumpling.Common.Utilities import pp_binstr
from dumpling.Common.VectorBuilder import VectorBuilder, NormalVector
from dumpling.Drivers.JTAG import JTAGTap, JTAGDriver, JTAGRegister
from bitstring import BitArray

from dumpling.Common.VectorBuilder import Vector

# Enables the experimental mode to index LSB with 0 instead of the MSB (see thread
# https://github.com/scott-griffiths/bitstring/issues/156)
bitstring.lsb0 = True


class PULPJtagTap(JTAGTap):
    """
    See Also:
        Check the adv_dbg documentation for details on the protocol used for this JTAGTap
    """

    DBG_MODULE_ID = BitArray("0b100000")

    class DBG_OP(Enum):
        NOP = "0x0"
        WRITE8 = "0x1"
        WRITE16 = "0x2"
        WRITE32 = "0x3"
        WRITE64 = "0x4"
        READ8 = "0x5"
        READ16 = "0x6"
        READ32 = "0x7"
        READ64 = "0x8"
        INT_REG_WRITE = "0x9"
        INT_REG_SELECT = "0xD"

        def to_bits(self) -> BitArray:
            return BitArray(self.value)  # type: ignore until https://github.com/scott-griffiths/bitstring/issues/276 is closed

    reg_idcode: JTAGRegister
    reg_soc_axireg: JTAGRegister
    reg_soc_bbmuxreg: JTAGRegister
    reg_soc_confreg: JTAGRegister
    reg_soc_testmodereg: JTAGRegister
    reg_soc_bistreg: JTAGRegister

    def __init__(self, driver: JTAGDriver, idcode: Optional[str] = None):
        super().__init__("PULP JTAG module", 5, driver)
        self.reg_idcode = self._add_reg(JTAGRegister("IDCODE", "00010", 32, idcode))
        self.reg_soc_axireg = self._add_reg(
            JTAGRegister("SoC AXIREG", "00100", 0)
        )  # The size of the axi reg depends on the burst setup
        self.reg_soc_bbmuxreg = self._add_reg(JTAGRegister("SoC BBMUXREG", "00101", 21))
        self.reg_soc_confreg = self._add_reg(JTAGRegister("SoC CONFREG", "00110", 9))
        self.reg_soc_testmodereg = self._add_reg(
            JTAGRegister("SoC TESTMODEREG", "01000", 4)
        )
        self.reg_soc_bistreg = self._add_reg(JTAGRegister("SoC BISTREG", "01001", 20))
        # self.reg_clk_byp = self._add_reg(JTAGRegister('CLK_BYP', '00111', ))

    def set_config_reg(
        self,
        soc_jtag_reg_value: BitArray,
        sel_fll_clk: bool,
        comment: Optional[str] = None,
    ) -> List[NormalVector]:
        """
        Generates stimuli to program the config register.

        Args:
            soc_jtag_reg_value (BitArray): An 8-bit value represented as a BitArray of length 8 with character 0,1
            sel_fll_clk (bool): True if the internal FLL should be used for clock generation, False if the external reference clock should be directly used for clock gen.
            comment (str): A string with which the first vector of the returned stimuli vectors will be annotated as a comment. If None, a default comment will be used.
        Returns:
            The generated vectors. The format of those vectors depends on the actual implementation of the VectorWriter instance used
        """
        id_value = ("1" if sel_fll_clk else "0") + soc_jtag_reg_value.bin
        if comment is None:
            comment = ""
        comment += f"/Set JTAG Config reg to {pp_binstr(soc_jtag_reg_value)}, internal FLL {'enabled' if sel_fll_clk else 'disabled'}"
        return self.driver.write_reg(
            self, self.reg_soc_confreg, id_value, comment=comment
        )

    def verify_config_reg(
        self,
        soc_jtag_reg_value: BitArray,
        sel_fll_clk: bool,
        comment: Optional[str] = None,
    ) -> List[NormalVector]:
        if comment is None:
            comment = ""
        comment += f"/Verify JTAG Config reg is {pp_binstr(soc_jtag_reg_value)} and FLL is {'enabled' if sel_fll_clk else 'disabled'}"
        id_value = ("1" if sel_fll_clk else "0") + soc_jtag_reg_value.bin
        return self.driver.read_reg(self, self.reg_soc_confreg, 9, id_value)

    def init_pulp_tap(self) -> List[NormalVector]:
        return self.driver.jtag_set_ir(
            self, self.reg_soc_axireg.IR_value, comment="Init Pulp Tap"
        )

    def module_select(self, comment: Optional[str] = None) -> List[NormalVector]:
        return self.driver.jtag_set_dr(
            self, PULPJtagTap.DBG_MODULE_ID.bin, comment=comment
        )

    def setup_burst(
        self,
        cmd: DBG_OP,
        start_addr: BitArray,
        nwords: int,
        comment: Optional[str] = None,
    ) -> List[NormalVector]:
        if comment is None:
            comment = ""
        comment += f"/Setup AXI4 adv dbg burst @{pp_binstr(start_addr)} for {nwords} words"
        dr_value: BitArray = BitArray(53)  # type: ignore until https://github.com/scott-griffiths/bitstring/issues/276 is closed
        dr_value[48:52] = cmd.to_bits()
        dr_value[16:48] = start_addr
        dr_value[0:16] = BitArray(uint=nwords, length=16)
        return self.driver.jtag_set_dr(self, dr_value.bin, comment=comment)

    def write_burst(
        self, data: List[BitArray], comment: Optional[str] = None
    ) -> List[NormalVector]:
        if comment is None:
            comment = ""
        comment += f"/Write burst data for {len(data)} words"
        burst = "1"  # Start Bit (p.20 adv dbg docu)
        for word in data:
            burst += word.bin[::-1]  # Actual Data to write LSB first
        burst += (
            32 * "1"
        )  # Dummy CRC (we do not check the match bit of the write transfer so we don't have to send a valid CRC code
        burst += "0"
        burst = burst[::-1]  # set_dr is LSB first so we have to reverse the order
        return self.driver.jtag_set_dr(self, burst, comment=comment)

    def read_burst_no_loop(
        self,
        expected_data: List[BitArray],
        wait_cycles: int = 3,
        comment: Optional[str] = None,
    ) -> List[NormalVector]:
        if comment is None:
            comment = ""
        comment += "/Read burst data for {} words".format(len(expected_data))

        vectors = self.driver.jtag_goto_shift_dr(comment)
        # Shift once for each tap before the jtag pulp
        for tap in self.driver.chain:
            if tap != self:
                vectors += self.driver.jtag_shift("0", "X", noexit=True)
            else:
                break

        burst = ""
        for word in expected_data:
            burst += word.bin[::-1]  # Actual Data to read LSB first
        burst += 32 * "X"  # Ignore the CRC
        # Shift DR until we see a status=1 bit
        # In this matched_loop-free version of read_burst we expect the user to tell us how many cycles the pulp_tap needs for the read ready bit to be raised (wait_cycles argument)
        wait_status_bits = "0" * wait_cycles + "1"
        vectors += self.driver.jtag_shift(
            "0" * (wait_cycles + 1),
            wait_status_bits,
            comment="Shift until status bit is 1",
            noexit=True,
        )
        # Now we shift the actual data
        vectors += self.driver.jtag_shift(
            len(burst) * "0", expected_chain=burst
        )  # We leave the shift dr state before we shifted the bypass bits of the taps that follow the pulp jtag tap. This is not
        #  an issue
        return vectors

    def read_burst(
        self,
        expected_data: List[BitArray],
        comment: Optional[str] = None,
        retries: int = 1,
    ) -> List[Vector]:
        if comment is None:
            comment = ""
        comment += "/Read burst data for {} words".format(len(expected_data))

        vectors: List[Vector] = list(self.driver.jtag_goto_shift_dr(comment))
        # Shift once for each tap before the jtag pulp
        for tap in self.driver.chain:
            if tap != self:
                vectors += self.driver.jtag_shift("0", "X", noexit=True)
            else:
                break

        burst = ""
        for word in expected_data:
            burst += word.bin[::-1]  # Actual Data to read LSB first
        burst += 32 * "X"  # Ignore the CRC

        # Shift DR until we see a status=1 bit
        condition_vectors = self.driver.jtag_shift(
            "0", "1", comment="Shift until status bit is 1", noexit=True
        )
        # Pad to multiple of 8 vectors
        condition_vectors = VectorBuilder.pad_vectors(
            list(condition_vectors), self.driver.jtag_idle_vector()
        )
        idle_vectors = self.driver.jtag_idle_vectors(8)
        vectors.append(
            self.driver.vector_builder.matched_loop(
                condition_vectors, idle_vectors, retries
            )
        )
        # Make sure there are at least 8 normal vectors before the next matched loop by insertion idle instructions
        vectors += self.driver.jtag_idle_vectors(8)

        # We leave the shift dr state before we shifted the bypass bits of the taps that follow the pulp jtag tap.
        # This is not an issue
        vectors += self.driver.jtag_shift(len(burst) * "0", expected_chain=burst)
        return vectors

    def write32(
        self, start_addr: BitArray, data: List[BitArray], comment: Optional[str] = None
    ) -> List[NormalVector]:
        nwords = len(data)
        if comment is None:
            comment = ""
        comment += f"/Write32 burst @{pp_binstr(start_addr)} for {nwords} bytes"
        # Module Selet Command (p.15 of ADV DBG Doc)
        vectors = self.module_select()
        # Setup Burst (p.17 of ADV DBG Doc)
        vectors += self.setup_burst(
            PULPJtagTap.DBG_OP.WRITE32, start_addr, nwords, comment=comment
        )
        # Burst the data
        vectors += self.write_burst(data)
        return vectors

    def read32(
        self,
        start_addr: BitArray,
        expected_data: List[BitArray],
        retries: int = 1,
        comment: Optional[str] = None,
    ) -> List[Vector]:
        nwords = len(expected_data)
        if comment is None:
            comment = ""
        comment += f"/Read32 burst @{pp_binstr(start_addr)} for {nwords} bytes"
        # Module Selet Command (p.15 of ADV DBG Doc)
        vectors = self.module_select()
        # Setup Burst (p.17 of ADV DBG Doc)
        vectors += self.setup_burst(
            PULPJtagTap.DBG_OP.READ32, start_addr, nwords, comment=comment
        )
        # Burst the data
        vectors += self.read_burst(expected_data, retries=retries)
        return vectors

    def read32_no_loop(
        self,
        start_addr: BitArray,
        expected_data: List[BitArray],
        wait_cycles: int = 3,
        comment: Optional[str] = None,
    ) -> List[NormalVector]:
        nwords = len(expected_data)
        if comment is None:
            comment = ""
        comment += f"/Read32 burst @{pp_binstr(start_addr)} for {nwords} bytes"
        # Module Selet Command (p.15 of ADV DBG Doc)
        vectors = self.module_select()
        # Setup Burst (p.17 of ADV DBG Doc)
        vectors += self.setup_burst(
            PULPJtagTap.DBG_OP.READ32, start_addr, nwords, comment=comment
        )
        # Burst the data
        vectors += self.read_burst_no_loop(expected_data, wait_cycles=wait_cycles)
        return vectors

    def loadL2(
        self, elf_binary: os.PathLike, comment: Optional[str] = None
    ) -> List[NormalVector]:
        stim_generator = ElfParser(verbose=False)
        stim_generator.add_binary(elf_binary)
        stimuli = stim_generator.parse_binaries(4)

        vectors = []

        # Split the stimuli into bursts
        burst_data = []
        start_addr = None
        prev_addr = None
        for addr, word in tqdm(sorted(stimuli.items())):
            if not start_addr:
                start_addr = int(addr)
            # If there is a gap in the data to load or the burst would end up longer than 256 words, start a new burst
            if prev_addr and (prev_addr + 4 != int(addr) or len(burst_data) >= 256):
                vectors += self.write32(
                    BitArray(uint=start_addr, length=32), burst_data,  # type: ignore until https://github.com/scott-griffiths/bitstring/issues/276 is closed
                    comment=comment
                )
                start_addr = int(addr)
                burst_data = []
            prev_addr = int(addr)
            burst_data.append(BitArray(uint=int(word), length=32))

        # Create the final burst
        vectors += self.write32(BitArray(uint=start_addr, length=32), burst_data)  # type: ignore until https://github.com/scott-griffiths/bitstring/issues/276 is closed
        return vectors

    def verifyL2(
        self, elf_binary: os.PathLike, retries: int = 1, comment: Optional[str] = None
    ) -> List[Vector]:
        stim_generator = ElfParser(verbose=False)
        stim_generator.add_binary(elf_binary)
        stimuli = stim_generator.parse_binaries(4)

        vectors = []

        # Split the stimuli into bursts
        burst_data = []
        start_addr = None
        prev_addr = None
        for addr, word in sorted(stimuli.items()):
            if not start_addr:
                start_addr = int(addr)
            # If there is a gap in the data to load or the burst would end up longer than 256 words, start a new burst
            if prev_addr and (prev_addr + 4 != int(addr) or len(burst_data) >= 256):
                vectors += self.read32(BitArray(uint=start_addr, length=32), burst_data, retries=retries, comment=comment)  # type: ignore until https://github.com/scott-griffiths/bitstring/issues/276 is closed
                start_addr = int(addr)
                burst_data = []
            prev_addr = int(addr)
            burst_data.append(BitArray(uint=int(word), length=32))

        # Create the final burst
        vectors += self.read32(BitArray(uint=start_addr, length=32), burst_data)  # type: ignore until https://github.com/scott-griffiths/bitstring/issues/276 is closed
        return vectors

    def verifyL2_no_loop(
            self, elf_binary: os.PathLike, wait_cycles: int = 3, comment: Optional[str] = None,
    ) -> List[NormalVector]:
        stim_generator = ElfParser(verbose=False)
        stim_generator.add_binary(elf_binary)
        stimuli = stim_generator.parse_binaries(4)

        vectors = []

        # Split the stimuli into bursts
        burst_data = []
        start_addr = None
        prev_addr = None
        for addr, word in sorted(stimuli.items()):
            if not start_addr:
                start_addr = int(addr)
            # If there is a gap in the data to load or the burst would end up longer than 256 words, start a new burst
            if prev_addr and (prev_addr + 4 != int(addr) or len(burst_data) >= 256):
                vectors += self.read32_no_loop(
                    BitArray(uint=start_addr, length=32), burst_data,  # type: ignore until https://github.com/scott-griffiths/bitstring/issues/276 is closed
                    wait_cycles=wait_cycles,
                    comment=comment
                )
                start_addr = int(addr)
                burst_data = []
            prev_addr = int(addr)
            burst_data.append(BitArray(uint=int(word), length=32))

        # Create the final burst
        vectors += self.read32_no_loop(BitArray(uint=start_addr, length=32), burst_data, wait_cycles, comment=comment)  # type: ignore until https://github.com/scott-griffiths/bitstring/issues/276 is closed
        return vectors

    # def wait_for_end_of_computation(self, expected_return_code:int, retries=10, idle_cycles=100):
    #     expected_eoc_value = BitArray(int=expected_return_code, length=32)
    #     expected_eoc_value[31] = 1
    #     condition_vectors = self.read32(BitArray('0x1a1040a0'), [expected_eoc_value], retries=5, comment="Poll end of computation expecting return code {}.".format(expected_return_code))
    #     # Pad the condition vectors to be a multiple of 8
    #     condition_vectors += self.driver.jtag_idle_vectors(count=8 - len(condition_vectors) % 8)
    #     idle_vectors = self.driver.jtag_idle_vectors(count=idle_cycles)
    #     idle_vectors += self.driver.jtag_idle_vectors(count=8 - len(idle_vectors) % 8)
    #     vectors = self.driver.vector_builder.matched_loop(condition_vectors, idle_vectors, retries=retries)
    #     return vectors

from enum import Enum
from typing import List

from dumpling.Common.ElfParser import ElfParser
from dumpling.Common.VectorBuilder import VectorBuilder
from dumpling.Drivers.JTAG import JTAGTap, JTAGDriver, JTAGRegister
from bitstring import BitArray


class PULPJtagTap(JTAGTap):
    """
    See Also:
        Check teh adv_dbg documentation for details on the protocol used for this JTAGTap
    """
    DBG_MODULE_ID = BitArray('0b100000')

    class DBG_OP(Enum):
        NOP = '0x0'
        WRITE8 = '0x1'
        WRITE16 = '0x2'
        WRITE32 = '0x3'
        WRITE64 = '0x4'
        READ8 = '0x5'
        READ16 = '0x6'
        READ32 = '0x7'
        READ64 = '0x8'
        INT_REG_WRITE = '0x9'
        INT_REG_SELECT = '0xD'

        def to_bits(self):
            return BitArray(self.value)


    def __init__(self, driver: JTAGDriver):
        super().__init__("PULP JTAG module", 5, driver)
        self.reg_idcode = self._add_reg(JTAGRegister("IDCODE", '00010', 32))
        self.reg_soc_axireg = self._add_reg(JTAGRegister("SoC AXIREG", "00100", 0)) #The size of the axi reg depends on the burst setup
        self.reg_soc_bbmuxreg = self._add_reg(JTAGRegister('SoC BBMUXREG', "00101", 21))
        self.reg_soc_confreg = self._add_reg(JTAGRegister('SoC CONFREG', '00110', 9))
        self.reg_soc_testmodereg = self._add_reg(JTAGRegister('SoC TESTMODEREG', '01000', 4))
        self.reg_soc_bistreg = self._add_reg(JTAGRegister('SoC BISTREG', '01001', 20))
        #self.reg_clk_byp = self._add_reg(JTAGRegister('CLK_BYP', '00111', ))

    def set_config_reg(self, soc_jtag_reg_value: BitArray, sel_fll_clk: bool, comment=""):
        """
        Generates stimuli to program the config register.

        Args:
            soc_jtag_reg_value (BitArray): An 8-bit value represented as a BitArray of length 8 with character 0,1
            sel_fll_clk (bool): True if the internal FLL should be used for clock generation, False if the external reference clock should be directly used for clock gen.
            comment (str): A string with which the first vector of the returned stimuli vectors will be annotated as a comment. If None, a default comment will be used.
        Returns:
            The generated vectors. The format of those vectors depends on the actual implementation of the VectorWriter instance used
        """
        id_value = ('1' if sel_fll_clk else '0') + soc_jtag_reg_value.bin
        comment += "/Set JTAG Config reg to {}, internal FLL {}".format(soc_jtag_reg_value.hex, 'enabled' if sel_fll_clk else 'disabled')
        return self.driver.write_reg(self, self.reg_soc_confreg, id_value, comment=comment)

    def verify_config_reg(self, soc_jtag_reg_value: BitArray, sel_fll_clk: bool, comment=""):
        comment += "/Verify JTAG Config reg is {} and FLL is {}".format(soc_jtag_reg_value.hex, 'enabled' if sel_fll_clk else 'disabled')
        id_value = ('1' if sel_fll_clk else '0') + soc_jtag_reg_value.bin
        return self.driver.read_reg(self, self.reg_soc_confreg, 9, id_value)

    def init_pulp_tap(self):
        return self.driver.jtag_set_ir(self, self.reg_soc_axireg.IR_value, comment="Init Pulp Tap")

    def module_select(self, comment=""):
        return self.driver.jtag_set_dr(self, PULPJtagTap.DBG_MODULE_ID.bin, comment=comment)

    def setup_burst(self, cmd: DBG_OP, start_addr:BitArray, nwords:int, comment=""):
        comment += "/Setup AXI4 adv dbg burst @{} for {} words".format(start_addr, nwords)
        dr_value = BitArray(53)
        dr_value[48:52] = cmd.to_bits()
        dr_value[16:48] = start_addr
        dr_value[0:16] = BitArray(uint=nwords, length=16)
        return self.driver.jtag_set_dr(self, dr_value.bin, comment=comment)

    def write_burst(self, data:List[BitArray], comment=""):
        comment += "/Write burst data for {} words".format(len(data))
        burst = '1' #Start Bit (p.20 adv dbg docu)
        for idx, word in enumerate(data):
            burst += word.bin[::-1] #Actual Data to write LSB first
        burst += 32*'1' #Dummy CRC (we do not check the match bit of the write transfer so we don't have to send a valid CRC code
        burst += '0'
        burst = burst[::-1] #set_dr is LSB first so we have to reverse the order
        return self.driver.jtag_set_dr(self, burst, comment=comment)

    def read_burst_no_loop(self, expected_data:List[BitArray], comment=""):
        comment += "/Read burst data for {} words".format(len(expected_data))

        vectors = self.driver.jtag_goto_shift_dr(comment)
        # Shift once for each tap before the jtag pulp
        for tap in self.driver.chain:
            if tap != self:
                vectors += self.driver.jtag_shift('0', 'X', noexit=True)
            else:
                break

        burst = ''
        for idx, word in enumerate(expected_data):
            burst += word.bin[::-1]  # Actual Data to read LSB first
        burst += 32 * 'X'  # Ignore the CRC
        # Shift DR until we see a status=1 bit
        # In this matched_loop-free version of read_burst we assume the status bit to raise with the third jtag shift
        vectors += self.driver.jtag_shift('00', '01', comment="Shift until status bit is 1", noexit=True)
        # Now we shift the actual data
        vectors += self.driver.jtag_shift(len(burst) * '0',
                                          expected_chain=burst)  # We leave the shift dr state before we shifted the bypass bits of the taps that follow the pulp jtag tap. This is not
        #  an issue
        return vectors

    def read_burst(self, expected_data:List[BitArray], comment="", retries=1):
        comment += "/Read burst data for {} words".format(len(expected_data))

        vectors = self.driver.jtag_goto_shift_dr(comment)
        # Shift once for each tap before the jtag pulp
        for tap in self.driver.chain:
            if tap != self:
                vectors += self.driver.jtag_shift('0', 'X', noexit=True)
            else:
                break

        burst = ''
        for idx, word in enumerate(expected_data):
            burst += word.bin[::-1]  # Actual Data to read LSB first
        burst += 32 * 'X'  # Ignore the CRC

        #Shift DR until we see a status=1 bit
        condition_vectors = self.driver.jtag_shift('0', '1', comment="Shift until status bit is 1", noexit=True)
        #Pad to multiple of 8 vectors
        condition_vectors = VectorBuilder.pad_vectors(condition_vectors, self.driver.jtag_idle_vector())
        idle_vectors = self.driver.jtag_idle_vectors(8)
        vectors += self.driver.vector_writer.matched_loop(condition_vectors, idle_vectors, retries)
        vectors += self.driver.jtag_idle_vectors(8)  # Make sure there are at least 8 normal vectors before the next matched loop by insertion idle instructions


        vectors += self.driver.jtag_shift(len(burst)*'0', expected_chain=burst) #We leave the shift dr state before we shifted the bypass bits of the taps that follow the pulp jtag tap. This is not
        #  an issue
        return vectors

    def write32(self, start_addr:BitArray, data:List[BitArray], comment=""):
        nwords = len(data)
        comment += "/Write32 burst @{} for {} bytes".format(start_addr, nwords)
        #Module Selet Command (p.15 of ADV DBG Doc)
        vectors = self.module_select()
        #Setup Burst (p.17 of ADV DBG Doc)
        vectors += self.setup_burst(PULPJtagTap.DBG_OP.WRITE32, start_addr, nwords, comment=comment)
        #Burst the data
        vectors += self.write_burst(data)
        return vectors

    def read32(self, start_addr:BitArray, expected_data:List[BitArray], retries=1, comment=""):
        nwords = len(expected_data)
        comment += "/Read32 burst @{} for {} bytes".format(start_addr, nwords)
        #Module Selet Command (p.15 of ADV DBG Doc)
        vectors = self.module_select()
        #Setup Burst (p.17 of ADV DBG Doc)
        vectors += self.setup_burst(PULPJtagTap.DBG_OP.READ32, start_addr, nwords, comment=comment)
        #Burst the data
        vectors += self.read_burst(expected_data, retries=retries)
        return vectors

    def read32_no_loop(self, start_addr:BitArray, expected_data:List[BitArray], comment=""):
        nwords = len(expected_data)
        comment += "/Read32 burst @{} for {} bytes".format(start_addr, nwords)
        #Module Selet Command (p.15 of ADV DBG Doc)
        vectors = self.module_select()
        #Setup Burst (p.17 of ADV DBG Doc)
        vectors += self.setup_burst(PULPJtagTap.DBG_OP.READ32, start_addr, nwords, comment=comment)
        #Burst the data
        vectors += self.read_burst_no_loop(expected_data)
        return vectors

    def loadL2(self, elf_binary:str, comment=""):
        stim_generator = ElfParser(verbose=False)
        stim_generator.add_binary(elf_binary)
        stimuli = stim_generator.parse_binaries(4)

        vectors = []

        #Split the stimuli into bursts
        burst_data = []
        start_addr = None
        prev_addr = None
        for addr, word in sorted(stimuli.items()):
            if not start_addr:
                start_addr = int(addr)
            #If there is a gap in the data to load or the burst would end up longer than 256 words, start a new burst
            if prev_addr and (prev_addr+4 != int(addr) or len(burst_data)>=256):
                vectors += self.write32(BitArray(uint=start_addr, length=32), burst_data)
                start_addr = int(addr)
                burst_data = []
            prev_addr = int(addr)
            burst_data.append(BitArray(uint=int(word), length=32))

        #Create the final burst
        vectors += self.write32(BitArray(uint=start_addr, length=32), burst_data)
        return vectors

    def verifyL2(self, elf_binary:str, retries=1, comment=""):
        stim_generator = ElfParser(verbose=False)
        stim_generator.add_binary(elf_binary)
        stimuli = stim_generator.parse_binaries(4)

        vectors = []

        #Split the stimuli into bursts
        burst_data = []
        start_addr = None
        current_addr = None
        for addr, word in stimuli.items():
            #If there is a gap in the data to load or the burst would end up longer than 256 words, start a new burst
            if current_addr and (current_addr+4 != int(addr) or len(burst_data)>=256):
                    vectors += self.read32(BitArray(uint=start_addr, length=32), burst_data, retries=retries)
                    start_addr = current_addr
                    burst_data = []
            current_addr = int(addr)
            if not start_addr:
                start_addr = current_addr
            burst_data.append(BitArray(uint=word, length=32))

        #Create the final burst
        vectors += self.read32(BitArray(uint=start_addr, length=32), burst_data)
        return vectors

    def verifyL2_no_loop(self, elf_binary: str, comment=""):
        stim_generator = ElfParser(verbose=False)
        stim_generator.add_binary(elf_binary)
        stimuli = stim_generator.parse_binaries(4)

        vectors = []

        # Split the stimuli into bursts
        burst_data = []
        start_addr = None
        current_addr = None
        for addr, word in stimuli.items():
            # If there is a gap in the data to load or the burst would end up longer than 256 words, start a new burst
            if current_addr and (current_addr + 4 != int(addr) or len(burst_data) >= 256):
                vectors += self.read32_no_loop(BitArray(uint=start_addr, length=32), burst_data)
                start_addr = current_addr
                burst_data = []
            current_addr = int(addr)
            if not start_addr:
                start_addr = current_addr
            burst_data.append(BitArray(uint=word, length=32))

        # Create the final burst
        vectors += self.read32_no_loop(BitArray(uint=start_addr, length=32), burst_data)
        return vectors

    # def wait_for_end_of_computation(self, expected_return_code:int, retries=10, idle_cycles=100):
    #     expected_eoc_value = BitArray(int=expected_return_code, length=32)
    #     expected_eoc_value[31] = 1
    #     condition_vectors = self.read32(BitArray('0x1a1040a0'), [expected_eoc_value], retries=5, comment="Poll end of computation expecting return code {}.".format(expected_return_code))
    #     # Pad the condition vectors to be a multiple of 8
    #     condition_vectors += self.driver.jtag_idle_vectors(count=8 - len(condition_vectors) % 8)
    #     idle_vectors = self.driver.jtag_idle_vectors(count=idle_cycles)
    #     idle_vectors += self.driver.jtag_idle_vectors(count=8 - len(idle_vectors) % 8)
    #     vectors = self.driver.vector_writer.matched_loop(condition_vectors, idle_vectors, retries=retries)
    #     return vectors


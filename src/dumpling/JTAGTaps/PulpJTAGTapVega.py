from enum import Enum
from typing import List

import bitstring
from dumpling.Common.ElfParser import ElfParser
from dumpling.Common.VectorBuilder import VectorBuilder
from dumpling.Drivers.JTAG import JTAGTap, JTAGDriver, JTAGRegister
from bitstring import BitArray
bitstring.set_lsb0(True) #Enables the experimental mode to index LSB with 0 instead of the MSB (see thread https://github.com/scott-griffiths/bitstring/issues/156)


class PULPJtagTapVega(JTAGTap):
    """
    See Also:
        Check teh adv_dbg documentation for details on the protocol used for this JTAGTap
    """
    DBG_MODULE_ID = BitArray('0x10102001')

    class OBSERVABLE_SIGNAL(Enum):
        pmu_soc_trc_clk_o = 0
        pmu_soc_rst_ret_n_o = 1
        pmu_soc_rst_control_o = 2
        pmu_soc_rst_control_ack_i = 3
        pmu_soc_clken_o = 4
        pmu_soc_trc_ret_n_o = 5
        pmu_soc_trc_pok_ret_i = 6
        pmu_cluster_trc_ret_n_o = 7
        pmu_cluster_trc_pok_ret_i = 8
        pmu_csi2_trc_ext_n_o = 9
        pmu_csi2_trc_pok_ext_i = 10
        pmu_emram_core_trc_ext_n_o = 11
        pmu_emram_core_trc_pok_ext_i = 12
        pmu_smartwake_trc_ext_n_o = 13
        pmu_smartwake_trc_pok_ext_i = 14
        ref_clk_i = 15
        por_n_i = 16
        io_ls_avd_ok_o = 17
        io_ls_pok_i = 18
        io_hs_avd_ok_o = 19
        io_hs_pok_i = 20
        emram_io_avd_ok_o = 21
        emram_io_pok_i = 22
        safe_rar_rok_i = 23
        safe_rar_vsel_strobe_o = 24
        safe_rar_vsel_reg_o = 25
        logic_rar_rok_i = 26
        logic_rar_vsel_strobe_o = 27
        vref_06_en_o = 28
        vref_12_en_o = 29
        vref_06_ok_i = 30
        vref_12_ok_i = 31

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
        super().__init__("PULP JTAG module for Vega", 4, driver)
        self.reg_idcode = self._add_reg(JTAGRegister("IDCODE", '0010', 32))
        self.reg_soc_axireg = self._add_reg(JTAGRegister("SoC AXIREG", "0100", 96)) #The size of the axi reg depends on the burst setup
        self.reg_soc_confreg = self._add_reg(JTAGRegister('SoC CONFREG', '0110', 8))
        self.reg_soc_clk_byp_reg = self._add_reg(JTAGRegister('SoC CLK BYP', '0111', 5))
        self.reg_soc_observ= self._add_reg(JTAGRegister('SoC OBSERV', '1000', 32))

    def set_clk_bypass_reg(self, qosc_byp:bool=False, ref_clk_byp:bool=False, per_fll_byp:bool=False, soc_fll_byp:bool=True, cluster_fll_byp:bool=True):
        enabled_bypasses = [name for name, enabled in zip(['qosc', 'ref_clk', 'per_fll', 'soc_fll', 'cluster_fll'], [qosc_byp, ref_clk_byp, per_fll_byp, soc_fll_byp, cluster_fll_byp]) if enabled]
        comment = "Bypassing {}".format(', '.join(enabled_bypasses))
        id_value = bitstring.pack('pad:22 bool, bool, bool, bool, bool',cluster_fll_byp, soc_fll_byp, per_fll_byp, ref_clk_byp, qosc_byp)
        return self.driver.write_reg(self, self.reg_soc_clk_byp_reg, id_value.bin, comment=comment)

    def disable_observability(self):
        """
            Disable the observability functionality and make the PWM3 pad act normally again.

        Returns: The vectors associated to the pad

        """
        id_value = BitArray(32) #All zeros
        return self.driver.write_reg(self, self.reg_soc_observ, id_value.bin, comment="Disabling observability feature")

    def enable_observability(self, signal: OBSERVABLE_SIGNAL, pulldown_enable=False, pullup_enable=False, drv_strength=0):
        """
            Programs the observability register to generate make one 32 different internal signals available to the PWM3 pad

        Args:
            signal (OBSERVABLE_SIGNAL]: The signal for which to enable the observability
            pulldown_enable (bool): Whether to enable the pull-down resistor of the observability pad
            pullup_enable (bool): Whether to enable the pull-up resistor of the observability pad
            drv_strength (int): The driving strength to use for the register (value between 0-3 inclusive)

        Returns:
            List: The vectors corresponding to the operation
        """
        comment = "Enable observability of {}".format(signal.name)
        dr_value = bitstring.pack('uint:5, uint:2, bool, bool, 0b1', signal.value, drv_strength, pullup_enable, pulldown_enable)
        return self.driver.write_reg(self, self.reg_soc_observ, dr_value, comment=comment)


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
        vectors += self.driver.jtag_shift('0000', '0001', comment="Shift until status bit is 1", noexit=True)
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

        # Split the stimuli into bursts
        burst_data = []
        start_addr = None
        prev_addr = None
        for addr, word in sorted(stimuli.items()):
            if not start_addr:
                start_addr = int(addr)
            # If there is a gap in the data to load or the burst would end up longer than 256 words, start a new burst
            if prev_addr and (prev_addr + 4 != int(addr) or len(burst_data) >= 256):
                vectors += self.read32(BitArray(uint=start_addr, length=32), burst_data)
                start_addr = int(addr)
                burst_data = []
            prev_addr = int(addr)
            burst_data.append(BitArray(uint=int(word), length=32))

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
        prev_addr = None
        for addr, word in sorted(stimuli.items()):
            if not start_addr:
                start_addr = int(addr)
            # If there is a gap in the data to load or the burst would end up longer than 256 words, start a new burst
            if prev_addr and (prev_addr + 4 != int(addr) or len(burst_data) >= 256):
                vectors += self.read32_no_loop(BitArray(uint=start_addr, length=32), burst_data)
                start_addr = int(addr)
                burst_data = []
            prev_addr = int(addr)
            burst_data.append(BitArray(uint=int(word), length=32))

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


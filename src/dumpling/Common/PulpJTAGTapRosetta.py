from dumpling.Drivers.JTAG import JTAGDriver, JTAGRegister
from dumpling.JTAGTaps.PulpJTAGTap import PULPJtagTap
from bitstring import BitArray


class PULPJTagTapRosetta(PULPJtagTap):
    def __init__(self, driver: JTAGDriver):
        super().__init__(driver)

        #Replace the soc CONFREG as Rosetta adds a couple of additional bits
        self.reg_soc_confreg = self._add_reg(JTAGRegister('SoC CONFREG', '00110', 13))

    def set_config_reg(self, soc_jtag_reg_value: BitArray, soc_fll_bypass_en: bool, per_fll_bypass_en: bool, blade_disable: bool, edram_disable: bool, hd_mem_backend_use_edram: bool):
        id_value = '1' if hd_mem_backend_use_edram else '0'
        id_value += '1' if edram_disable else '0'
        id_value += '1' if blade_disable else '0'
        id_value += '1' if per_fll_bypass_en else '0'
        id_value += '1' if soc_fll_bypass_en else '0'
        id_value += soc_jtag_reg_value.bin
        return self.driver.write_reg(self, self.reg_soc_confreg, id_value, "Program config reg.")

    def verify_config_reg(self, soc_jtag_reg_value: BitArray, soc_fll_bypass_en: bool, per_fll_bypass_en: bool, blade_disable: bool, edram_disable: bool, hd_mem_backend_use_edram: bool):
        id_value = '1' if hd_mem_backend_use_edram else '0'
        id_value += '1' if edram_disable else '0'
        id_value += '1' if blade_disable else '0'
        id_value += '1' if per_fll_bypass_en else '0'
        id_value += '1' if soc_fll_bypass_en else '0'
        id_value += soc_jtag_reg_value.bin
        return self.driver.read_reg(self, self.reg_soc_confreg, 13, id_value, "Verify config reg.")
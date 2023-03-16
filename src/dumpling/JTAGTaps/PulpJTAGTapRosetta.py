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
from dumpling.Drivers.JTAG import JTAGDriver, JTAGRegister
from dumpling.JTAGTaps.PulpJTAGTap import PULPJtagTap
import bitstring
from bitstring import BitArray
bitstring.lsb0 = True #Enables the experimental mode to index LSB with 0 instead of the MSB (see thread https://github.com/scott-griffiths/bitstring/issues/156)


class PULPJTagTapRosetta(PULPJtagTap):
    def __init__(self, driver: JTAGDriver):
        super().__init__(driver)

        #Replace the soc CONFREG as Rosetta adds a couple of additional bits
        self.reg_soc_confreg = self._add_reg(JTAGRegister('SoC CONFREG', '00110', 13))

    def set_config_reg(self, soc_jtag_reg_value: BitArray, soc_fll_bypass_en: bool, per_fll_bypass_en: bool, blade_disable: bool, edram_disable: bool, hd_mem_backend_use_edram: bool):
        id_value = '0' if hd_mem_backend_use_edram else '1'
        id_value += '1' if edram_disable else '0'
        id_value += '1' if blade_disable else '0'
        id_value += '1' if per_fll_bypass_en else '0'
        id_value += '1' if soc_fll_bypass_en else '0'
        id_value += soc_jtag_reg_value.bin
        return self.driver.write_reg(self, self.reg_soc_confreg, id_value, "Program config reg.")

    def verify_config_reg(self, soc_jtag_reg_value: BitArray, soc_fll_bypass_en: bool, per_fll_bypass_en: bool, blade_disable: bool, edram_disable: bool, hd_mem_backend_use_edram: bool):
        id_value = '0' if hd_mem_backend_use_edram else '1'
        id_value += '1' if edram_disable else '0'
        id_value += '1' if blade_disable else '0'
        id_value += '1' if per_fll_bypass_en else '0'
        id_value += '1' if soc_fll_bypass_en else '0'
        id_value += soc_jtag_reg_value.bin
        return self.driver.read_reg(self, self.reg_soc_confreg, 13, id_value, "Verify config reg.")

import math
import re
from pathlib import Path

import bitstring
import click
from dumpling.Common.ElfParser import ElfParser
from bitstring import BitArray
bitstring.set_lsb0(True) #Enables the experimental mode to index LSB with 0 instead of the MSB (see thread https://github.com/scott-griffiths/bitstring/issues/156)
from dumpling.Common.HP93000 import HP93000VectorWriter
from dumpling.JTAGTaps.PulpJTAGTap import PULPJtagTap
from dumpling.Common.VectorBuilder import VectorBuilder
from dumpling.Drivers.JTAG import JTAGDriver
from dumpling.JTAGTaps.RISCVDebugTap import RISCVDebugTap, RISCVReg

pins = {
        'chip_reset' : {'name': 'rst_ni', 'default': '1'},
        'trst': {'name': 'jtag_trst_ni', 'default': '1'},
        'tms': {'name': 'jtag_tms_i', 'default': '0'},
        'tck': {'name': 'jtag_tck_i', 'default': '0'},
        'tdi': {'name': 'jtag_tdi_i', 'default': '0'},
        'tdo': {'name': 'jtag_tdo_o', 'default': 'X'}
    }
CLU_WAKEUP_REG = BitArray('0x00040004')

vector_builder = VectorBuilder(pins)
jtag_driver = JTAGDriver(vector_builder)

# Instantiate the two JTAG taps in Heartstream
riscv_debug_tap = RISCVDebugTap(jtag_driver)
pulp_tap = PULPJtagTap(jtag_driver)
# Add the taps to the jtag chain in the right order
jtag_driver.add_tap(riscv_debug_tap)
jtag_driver.add_tap(pulp_tap)

#Commands
pass_VectorWriter = click.make_pass_decorator(HP93000VectorWriter)

#Entry point for all Heartstream related commands
@click.group()
@click.option("--port-name", '-p', type=str, default="jtag_rst_port", show_default=True)
@click.option("--wtb-name", '-w', type=str, default="multiport", show_default=True)
@click.option('--output', '-o', type=click.Path(exists=False, file_okay=True, writable=True), default="vectors.avc", show_default=True)
@click.option("--device_cycle_name", '-d', type=str, default="dvc_1", )
@click.pass_context
def heartstream(ctx, port_name, wtb_name, device_cycle_name, output):
    """Generate stimuli for the GF12 Heartstream chip.
    """
    #Instantiate the vector writer and attach it to the command context so subcommands can access it.
    vector_builder.init()
    ctx.obj = HP93000VectorWriter(stimuli_file_path=Path(output), pins=pins, port=port_name, device_cycle_name=device_cycle_name, wtb_name=wtb_name)

@heartstream.command()
@click.option("--elf", "-e", required=True, type=click.Path(exists=True, file_okay=True, dir_okay=False), help="The path to the elf binary to preload.")
@click.option("--return_code", '-r', type=click.IntRange(min=0, max=255), default=0, help="Set a return code to check against during end of computation detection. A matched loop will be inserted to achieve ")
@click.option("--eoc_wait_cycles", '-w', default=0, type=click.IntRange(min=0), help="If set to a non zero integer, wait the given number of cycles for end of computation check and bdon't use ")
@click.option("--verify/--no_verify", default=True, help="Enables/Disables verifying the content written to L2.", show_default=True)
@click.option("--compress", '-c', is_flag=True, default=False, show_default=True, help="Compress all vectors by merging subsequent identical vectors into a single vector with increased repeat value.")
@click.option("--no_reset", is_flag=True, default=True, show_default=True, help="Don't reset the chip before executing the binary. Helpfull for debugging and to keep custom config preloaded via JTAG.")
@click.option("--no_resume", is_flag=True, default=True, show_default=True, help="Don't resume the core.")
@pass_VectorWriter
def execute_elf(writer: HP93000VectorWriter, elf, return_code, eoc_wait_cycles, verify, compress, no_reset, no_resume):
    """Generate vectors to load and execute the given elf binary.

    The command parses the binary supplied with the '--elf' parameter and
    writes the generated stimuli to the given OUTPUT file. Additionally to the
    AVC ASCII output, a .wtb and .tmf with identical basename is created. The
    vectors take care of resetting the chip, halting the core, preloading the
    binary into L2 memory with optional verification and resuming the core. If
    an expected return code is supplied with the optional '--return-code' flag,
    either a matched loop (polling) check or a single check (after a
    configurable number of idle clock cycles) for end of computation is added
    to the end of the stimuli vectors depending on the value of
    --eoc-wait-cycles.

    """

    with writer as vector_writer:
        vectors = []
        if not no_reset:
            # Assert reset
            vector_builder.chip_reset = 0
            # Wait 1us
            reset_vector = vector_builder.vector(comment="Assert reset")
            vectors += vector_builder.loop([reset_vector], 10)
            # Write the vectors to disk
            vector_writer.write_vectors(vectors, compress=compress)
            # Reset the jtag interface and wait for 10 cycles
            vectors = jtag_driver.jtag_reset()
            vectors += jtag_driver.jtag_idle_vectors(10)
            vector_writer.write_vectors(vectors, compress=compress)

        # Load L2 memory
        vectors = pulp_tap.init_pulp_tap()
        vectors += pulp_tap.loadL2(elf_binary=elf)
        vector_writer.write_vectors(vectors, compress=compress)

        # Optionally verify the data we just wrote to L2
        if verify:
            vectors = pulp_tap.verifyL2(elf, comment="Verify the content of L2 to match the binary.")
            vector_writer.write_vectors(vectors)

        if not no_resume:
            # Resume core
        	vectors = riscv_debug_tap.init_dmi()
        	vectors += riscv_debug_tap.writeMem(CLU_WAKEUP_REG, BitArray('0xFFFFFFFF'), retries=16)
        	writer.write_vectors(vectors)

        	if return_code != None:
        		if eoc_wait_cycles <= 0:
        			vectors = riscv_debug_tap.wait_for_end_of_computation(return_code, idle_vector_count=100, max_retries=10)
        		else:
        			vectors = [jtag_driver.jtag_idle_vector(repeat=eoc_wait_cycles, comment="Waiting for computation to finish before checking EOC register.")]
        			vectors += riscv_debug_tap.check_end_of_computation(return_code, wait_cycles=5000)
        		vector_writer.write_vectors(vectors, compress=compress)

@heartstream.command()
@click.option('--wait_cycles','-w', type=click.IntRange(min=1), default=10, show_default=True, help="The number of cycles to wait before verifying that core was actually resumed.")
@pass_VectorWriter
def wakeup_cluster(vector_writer: HP93000VectorWriter, wait_cycles):
    """Generate vectors to wakeup the cluster.

    The vectors will write via JTAG the cluster wakeup register, after waiting a configurable number of cycles.

    """

    with vector_writer as writer:
        # Wakeup
        vectors = riscv_debug_tap.init_dmi()
        vectors += [jtag_driver.jtag_idle_vector(repeat=wait_cycles, comment="Waiting for {} cycles before sending wakeup trigger.".format(wait_cycles))]
        vectors += riscv_debug_tap.writeMem(CLU_WAKEUP_REG, BitArray('0xFFFFFFFF'), retries=16)
        writer.write_vectors(vectors)

@heartstream.command()
@click.option('--reset_cycles','-r', type=click.IntRange(min=1), default=10, show_default=True, help="The number of cycles to assert the chip reset line.")
@pass_VectorWriter
def reset_chip(vector_writer: HP93000VectorWriter, reset_cycles):
    """Generate vectors to reset the core and the jtag interface

    """
    with vector_writer as writer:
        vectors = []
        vector_builder.chip_reset = 0
        vectors += [vector_builder.vector(reset_cycles, comment="Assert chip reset")]
        vector_builder.chip_reset = 1
        vectors += jtag_driver.jtag_reset()
        vectors += jtag_driver.jtag_idle_vectors(10)
        vectors += riscv_debug_tap.init_dmi()
        vectors += riscv_debug_tap.set_dmactive(True)
        vectors += jtag_driver.jtag_idle_vectors(10)
        writer.write_vectors(vectors)

@heartstream.command()
@click.argument("FLL", type=click.Choice(['SOC_FLL']))
@click.argument("MULT", type=click.IntRange(min=1, max=65535))
@click.option("--clk-div", default='4', type=click.Choice(['1','2','4','8','16','32','64','128','256']), help="Change the clock division factor of DCO clock to FLL output clock.")
@click.option("--lock", '-l', is_flag = True, default=False, show_default=True, help="Gate the output clock with the FLL lock signal")
@click.option("--tolerance", default=512, show_default=True, type=click.IntRange(min=0, max=2047), help="The margin around the target multiplication factor for clock to be considered stable.")
@click.option("--stable-cycles", default=16, show_default=True, type=click.IntRange(min=0, max=63), help="The number of stable cycles unil LOCK is asserted.")
@click.option("--unstable-cycles", default=16, show_default=True, type=click.IntRange(min=0, max=63), help="The number of unstable cycles unil LOCK is de-asserted.")
@click.option("--enable-dithering", is_flag=True, default=False, show_default=True, help="Enable dithering for higher frequency resolution.")
@click.option("--loop-gain-exponent", default=-7, type=click.IntRange(min=-15,max=0), show_default=True,  help="The gain exponent of the feedback loop. Gain = 2^<value>")
@click.option('--wait-cycles','-w', type=click.IntRange(min=1), default=200, show_default=True, help="The number of jtag cycles to wait between writing the two FLL config registers.")
@pass_VectorWriter
def change_freq(vector_writer: HP93000VectorWriter, fll, mult, clk_div, lock, tolerance, stable_cycles, unstable_cycles, loop_gain_exponent, enable_dithering, wait_cycles):
    """ Generate vectors to change the multiplication factor (MULT) and various other settings of the internal FLLs .

        The FLL argument determines which of the two independent FLLs in Heartstream is configured.
        The output frequency of the FLL is freq =<ref_freq>*<MULT>/<clk-div>.
        Since we need to write to two registers, we have to wait long enough for the FLL to become stable again before we try to modify the second registers.

    """
    with vector_writer as writer:
        vectors = pulp_tap.init_pulp_tap()
        if fll == "SOC_FLL":
            config1_address = BitArray('0x00051000')
            config2_address = BitArray('0x00051004')
        clk_div_value = int(math.log2(int(clk_div)))+1
        config1_value = bitstring.pack('0b1, bool, uint:4, uint:10=136, uint:16', lock, clk_div_value, mult)
        config2_value = bitstring.pack('bool, 0b000, uint:12, uint:6, uint:6, uint:4', enable_dithering, tolerance, stable_cycles, unstable_cycles, -loop_gain_exponent)

        vectors += pulp_tap.write32(start_addr=config1_address, data=[config1_value], comment="Configure {}".format(fll))
        vectors += [jtag_driver.jtag_idle_vector(repeat=wait_cycles)]
        vectors += pulp_tap.write32(start_addr=config2_address, data=[config2_value], comment="Configure {}".format(fll))
        writer.write_vectors(vectors)


@heartstream.command()
@click.option("--return-code", default=0, type=click.IntRange(min=0, max=255), show_default=True, help="The expected return code.")
@click.option('--eoc-wait-cycles','-w', type=click.IntRange(min=1), default=10, show_default=True, help="The number of cycles to wait for the eoc_register read operation to complete.")
@click.option("--compress", '-c', is_flag=True, default=False, show_default=True, help="Compress all vectors by merging subsequent identical vectors into a single vector with increased repeat value.")
@pass_VectorWriter
def check_eoc(vector_writer, return_code, eoc_wait_cycles, compress):
    """ Generate vectors to check for the end of computation.

    Programs compiled with the pulp-sdk or pulp-runtime write their exit code to a special end-of-computation register
    in APB SOC Control when they leave main. The expected return code (by default 0) can be modified to assume any value
    between 0 and 255. 
    """

    # Wait for end of computation by polling EOC register address
    with vector_writer as writer:
        if return_code != None:
            if eoc_wait_cycles <= 0:
                vectors = riscv_debug_tap.wait_for_end_of_computation(return_code, idle_vector_count=100, max_retries=10)
            else:
                vectors = [jtag_driver.jtag_idle_vector(repeat=eoc_wait_cycles, comment="Waiting for computation to finish before checking EOC register.")]
                vectors += riscv_debug_tap.check_end_of_computation(return_code, wait_cycles=5000)
            vector_writer.write_vectors(vectors, compress=compress)

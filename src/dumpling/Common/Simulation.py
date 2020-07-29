from pathlib import Path

import cocotb
from dumpling.Common.HP93000 import HP93000VectorReader
from cocotb.binary import BinaryValue
from cocotb.triggers import Timer

class CocotbDriver:
    """A mockup VectorWriter class to simulate the application of the stimuli with
    an RTL simulator. The CocotbDriver can be used like a normal VectorWriter
    (e.g. the HP93000VectorWriter). When you finished recording vectors (e.g.
    using the JTagDriver class) you can use the run_vectors() coroutine to in a
    cocotb testbench to start applying stimuli to your device under test
    applying the vectors you "wrote" with the vector writer.

    In addition to keys described in the BaseClass 'VectorWriter' the
    CocotbDriver expects the pinlist 'pins' to contain a wavefun key for each
    pin with an associated coroutine function that will be used to apply values
    to the signal or sample them. This allows to mimick the behavior of the
    ASIC tester wavetable by arbitrary shifting the time were data is applied
    or sampled.

    Each wavefunction is supposed to have the following signature::

       async def my_stimuli_appl_fun(signal, value):
         await cocotb.trigger.Timer('2', units='ns') #Wait 2ns
         signal <= value

    The CocotbDriver will await the supplied coroutine for each pin supplying the cocotb pin signal handle to 'signal' and the value of the current vector to 'value' as arguments to the
    coroutine function.

    The CocotbDriver class contains static helper functions to generate wavefunction coroutine for commonly used wavetable schemes ('simple_clock_gen_wavefun', 'simple_stimuli_appl_wavefun' and
    'simple_response_acq_wavefun').

    Args:
        pins: The pins description dictionary as described in the Docstring of VectorWriter.
        dut: The cocotb design under thest simulation handle i.e. the toplevel module where stimuli should be applied to.

    """
    @staticmethod
    def simple_clock_gen_wavefun(period_ps, duty_cycle=0.5 ,start_high=False, idle_low=True):
        """
        This function returns a coroutine wavefunction for clock application with the given period.

        The coroutine will apply a clock to signal if the value is '1'. The clock can either be idle-Low or idle-high when value is '0'.
        The start_high parameter decides whether the clock period a rising edge (start_high='False') or if the rising edge is applied after (1-duty_cycle)*period_ps

        Args:
            period_ps: The clock period used by the returned coroutine
            duty_cycle: The percentage of 'period_ps' the clock remains High
            start_high: Whether to start the period with a Rising Edge or with the Falling Edge
            idle_low: If signal should remain low when value is '0' or if it should remain high

        Returns:
            A coroutine for stimuli application that can be passed to 'CocotbDriver' as a wavefunction in the pin dictionary.
        """
        @cocotb.coroutine
        async def wavefun(signal, value):
            if value in [True, 1, '1']: #Make sure its not a string '0'
                if start_high:
                    signal <= 1
                    await Timer(int(period_ps*duty_cycle), units='ps')
                    signal <= 0
                    await Timer(int(period_ps*(1-duty_cycle)), units='ps')
                else:
                    signal <= 0
                    await Timer(int(period_ps*(1-duty_cycle)), units='ps')
                    signal <= 1
                    await Timer(int(period_ps*(duty_cycle)), units='ps')
            else:
                if idle_low:
                    signal <= 0
                else:
                    signal <= 0
                await Timer(period_ps, units='ps')
            return True # No missmatchs since we only apply data
        return wavefun


    @staticmethod
    def simple_stimuli_appl_wavefun(appl_delay_ps, wave_period_ps):
        """
        This function returns a coroutine wavefunction that implements a basic waveform applier that assigns signal the given value the desired skew after the rising clock edge.

        Args:
            signal: the signal to assign to
            value: the value to assign to the signal
            appl_delay_ps (int): the application delay in unit pico second
            wave_period_ps (int): the period of one wave, e.g. the period of the reference clock

        Returns:
            A coroutine for stimuli application that can be passed to 'CocotbDriver' as a wavefunction in the pin dictionary.

        """

        @cocotb.coroutine
        async def wavefun(signal:cocotb.handle.NonHierarchyObject, value):
            await Timer(appl_delay_ps, units='ps')
            signal <= BinaryValue(value)
            await Timer(wave_period_ps-appl_delay_ps, units='ps')
            return True #No missmatch since we do only apply data
        return wavefun

    @staticmethod
    def simple_response_acq_wavefun(acq_delay_ps: float, wave_period_ps: float):
        """
        This function returns a coroutine wavefunction that implements a basic waveform acquisition that samples the signal and compares it to the given value 'acq_delay_s' before the end of
        'wave_period_s'.

         I.e. the signal the value will be assigned to signal after 'wave_period_ps' - 'appl_delay_ps' pico seconds and the wavefun returns the result of the check
        after wave_period_ps has elapsed after its invocation.

        Args:
            acq_delay_ps (int): The skew before the end of the wave_period when the signal is sampled and compared.
            wave_period_ps (int): The period of the wave in unit pico seconds

        Returns:
            A coroutine for response acquisition that can be passed to 'CocotbDriver' as a wavefunction in the pin dictionary.

        """
        @cocotb.coroutine
        async def wavefun(signal:cocotb.handle.NonHierarchyObject, expected_value):
            match = True
            await Timer(wave_period_ps-acq_delay_ps, units='ps')
            if expected_value not in ['X', 'x']:
                if not signal.value.is_resolvable or signal != BinaryValue(expected_value):
                    signal._log.error("Missmatch on signal {}: Was {} instead of {}".format(signal._name, signal.value,expected_value))
                    match = False
            await Timer(acq_delay_ps, units='ps')
            return match
        return wavefun

    def __init__(self, pins, dut):
        self.pins = pins
        self.dut = dut
        self.vectors = []
        self.dut = dut

    async def simulate_avc(self, avc_path: Path):
        self.dut._log.info("Applying vector from file {} to DUT.".format(avc_path))
        with HP93000VectorReader(avc_path, self.pins) as reader:
            passed = True
            for vector in reader.vectors():
                passed &= await self.apply_vector(vector)
            return passed

    async def apply_vectors(self, vectors):
        self.dut._log.info("Applying {} vectors to DUT...".format(len(vectors)))
        passed = True
        for vector in vectors:
            passed &= await self.apply_vector(vector)
        return passed

    async def apply_vector(self, vector):
        if vector.get('comment', '') != '':
            self.dut._log.info(vector['comment'])
        if vector['type'] == 'vec':
            return_value = True
            for i in range(vector['repeat']):
                #Generate a list of all wavefunction coroutines
                wavefuns = []
                for logical_name, value in vector['vector'].items():
                    wavefun = self.pins[logical_name]['wavefun']
                    signal = getattr(self.dut,self.pins[logical_name]['name'])
                    wavefuns.append(wavefun(signal, value))
                #Execute all wavefunction in parallel and wait for completion
                forked_coroutines = [cocotb.fork(wavefun) for wavefun in wavefuns]
                #Aggregate the return value of each coroutine. If one wavefun returns false, the aggregated return value is also false
                for forked_coroutine in forked_coroutines:
                    return_value &= await forked_coroutine
            return return_value

        elif vector['type'] == 'match_loop':
            passed = False
            retry_count = 0
            # Try applying the condition vectors
            self.dut._log.info("Starting matched loop with {} retries.".format(vector['retries']))
            while not passed and retry_count <= vector['retries']:
                passed = True
                for cond_vector in vector['cond_vectors']:
                    passed &= await self.apply_vector(cond_vector)
                if not passed:
                    retry_count += 1
                    self.dut._log.info("Matched loop condition failed. Applying idle vectors and trying again.")
                    for idle_vector in vector['idle_vectors']:
                        await self.apply_vector(idle_vector)
            if not passed:
                self.dut._log.error("Matched loop failed permanently for {} retries.".format(retry_count))
            else:
                self.dut._log.info("Matched loop succeeded after {} retries".format(retry_count))
            return passed
        elif vector['type'] == 'loop':
            passed = True
            self.dut._log.info("Looping over {} vectors for {} iterations.".format(len(vector['loop_body']), vector['repeat']))
            for i in range(vector['repeat']):
                for loop_vector in vector['loop_body']:
                    passed &= await self.apply_vector(loop_vector)
            return passed
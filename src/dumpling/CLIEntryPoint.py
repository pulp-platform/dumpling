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

from pathlib import Path
import dumpling.Chips.Rosetta as Rosetta

import click
import click_completion
from dumpling.Chips import Vega
from dumpling.Chips import Siracusa
from dumpling.Chips import Trikarenos
from dumpling.Chips import Cerberus

click_completion.init()
_CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


@click.group(context_settings=_CONTEXT_SETTINGS)
def cli():
    """
    Generate ASIC tester vectors for PULP chips.
    """

@cli.command()
@click.option('--append/--overwrite', help="Append the completion code to the file", default=None)
@click.option('-i', '--case-insensitive/--no-case-insensitive', help="Case insensitive completion")
@click.argument('shell', required=False, type=click_completion.DocumentedChoice(click_completion.core.shells))
@click.argument('path', required=False)
def install_completions(append, case_insensitive, shell, path):
    """Install the command line tool's bash completion for your shell

    If you don't provide any additional arguments this command tries to detect your current shell in use and appends the relevant settings to your .bashrc, .zshrc etc."""
    extra_env = {'_CLICK_COMPLETION_COMMAND_CASE_INSENSITIVE_COMPLETE': 'ON'} if case_insensitive else {}
    shell, path = click_completion.core.install(shell=shell, path=path, append=append, extra_env=extra_env)
    click.echo('%s completion installed in %s' % (shell, path))

# Register first level subcommand
cli.add_command(Rosetta.rosetta)
cli.add_command(Vega.vega)
cli.add_command(Siracusa.siracusa)
cli.add_command(Trikarenos.trikarenos)
cli.add_command(Cerberus.cerberus)


# For debugging purposes only
if __name__ == '__main__':
    #cli(['rosetta', '-o' 'test.avc', 'write-mem', '0x1c008080=0xdeadbeef'])
    #cli(['rosetta', '-o' 'test.avc', 'halt-core-verify-pc'])
    #cli(['vega', 'enable-observability', 'pmu_soc_clken_o'])
    #cli(['vega', 'set-clk-bypass', '--soc_fll_bypass'])
    cli(['vega', 'verify-mem', '0x1a100004=0x448805F5# Read Fll config 1', '0x1a100000=0x000005f5# Read Fll1 status'])

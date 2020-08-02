from pathlib import Path
import dumpling.Chips.Rosetta as Rosetta

import click
import click_completion
from dumpling.Chips import Vega

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
    """Install the click-completion-command completion"""
    extra_env = {'_CLICK_COMPLETION_COMMAND_CASE_INSENSITIVE_COMPLETE': 'ON'} if case_insensitive else {}
    shell, path = click_completion.core.install(shell=shell, path=path, append=append, extra_env=extra_env)
    click.echo('%s completion installed in %s' % (shell, path))

# Register first level subcommand
cli.add_command(Rosetta.rosetta)
cli.add_command(Vega.vega)


# For debugging purposes only
if __name__ == '__main__':
    #cli(['rosetta', '-o' 'test.avc', 'write-mem', '0x1c008080=0xdeadbeef'])
    cli(['rosetta', '-o' 'test.avc', 'halt-core-verify-pc'])
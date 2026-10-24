import pytest

from ferromapas.__main__ import COMMANDS, main


@pytest.mark.parametrize("command", COMMANDS)
def test_command_requires_valid_arguments(command):
    # Todos los comandos están implementados; sin sus argumentos obligatorios, argparse falla.
    with pytest.raises(SystemExit):
        main([command, "--opcion-inexistente"])


def test_no_command_fails():
    with pytest.raises(SystemExit) as e:
        main([])
    assert e.value.code == 2

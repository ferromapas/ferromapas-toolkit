import pytest

from ferromapas.__main__ import COMMANDS, main


@pytest.mark.parametrize("command", COMMANDS)
def test_command_not_implemented(command, capsys):
    assert main([command]) == 1
    assert "no está implementado" in capsys.readouterr().err


def test_no_command_fails():
    with pytest.raises(SystemExit) as e:
        main([])
    assert e.value.code == 2

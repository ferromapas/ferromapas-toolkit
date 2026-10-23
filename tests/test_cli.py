import pytest

from ferromapas.__main__ import COMANDOS, main


@pytest.mark.parametrize("comando", COMANDOS)
def test_comando_no_implementado(comando, capsys):
    assert main([comando]) == 1
    assert "no está implementado" in capsys.readouterr().err


def test_sin_comando_falla():
    with pytest.raises(SystemExit) as e:
        main([])
    assert e.value.code == 2

from pathlib import Path

import pytest

from vestiario.pesdecrypt import decrypt

SAVE = Path(__file__).resolve().parent.parent / "saves" / "ML00000002"


def test_descriptografa_save_real():
    if not SAVE.exists():
        pytest.skip("copie um save de Master League para saves/ML00000002")
    partes = decrypt(SAVE.read_bytes())
    assert partes["header.dat"][144:146] == b"ML"
    assert len(partes["data.dat"]) > 3_316_488 + 13_000 * 596

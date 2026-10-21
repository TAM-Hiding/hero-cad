import pytest
from PySide6.QtWidgets import QMessageBox


@pytest.fixture(autouse=True)
def discard_at_test_teardown(monkeypatch):
    # Individual prompt tests override this; ordinary widget cleanup must not block.
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Discard)

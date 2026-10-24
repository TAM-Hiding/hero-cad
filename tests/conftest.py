import pytest
from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import QSettings


@pytest.fixture(autouse=True)
def isolated_application_preferences(monkeypatch, tmp_path):
    # Test windows must never inherit or overwrite a user's saved island layout.
    import hero_cad.ui.tool_island as module
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path/'config'))
    monkeypatch.setattr(module, 'application_settings',
                        lambda: QSettings(str(tmp_path/'preferences.ini'), QSettings.IniFormat))


@pytest.fixture(autouse=True)
def discard_at_test_teardown(monkeypatch):
    # Individual prompt tests override this; ordinary widget cleanup must not block.
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Discard)

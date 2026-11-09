import pytest
from PySide6.QtCore import QLocale, Qt

from hero_cad.ui.dimension_spinbox import DimensionSpinBox


@pytest.fixture
def field(qtbot):
    field = DimensionSpinBox()
    qtbot.addWidget(field)
    field.setLocale(QLocale.c())
    field.setDecimals(9)
    field.setRange(-100, 100)
    field.setSuffix(' mm')
    field.setKeyboardTracking(False)
    return field


@pytest.mark.parametrize(('value', 'display'), [
    (10, '10'),
    (10.5, '10.5'),
    (10.125, '10.125'),
    (0.9999, '0.9999'),
    (2.000001, '2.000001'),
    (-5, '-5'),
    (0, '0'),
])
def test_only_trailing_fractional_zeros_are_hidden(field, value, display):
    field.setValue(value)
    assert field.text() == f'{display} mm'
    assert field.value() == value


@pytest.mark.parametrize(('locale', 'display'), [('de_DE', '10,5 mm'), ('ar_EG', '١٠٫٥ mm')])
def test_localized_display_and_parsing(field, locale, display):
    field.setLocale(QLocale(locale))
    field.setValue(10.5)
    assert field.text() == display
    field.interpretText()
    assert field.value() == 10.5


def test_partial_input_is_preserved_until_commit(field, qtbot):
    field.setValue(10)
    field.show()
    qtbot.waitExposed(field)
    editor = field.lineEdit()
    editor.selectAll()
    qtbot.keyClicks(editor, '-')
    assert editor.text() == '- mm'
    qtbot.keyClicks(editor, '2.')
    assert editor.text() == '-2. mm'
    qtbot.keyClicks(editor, '000001200')
    assert editor.text() == '-2.000001200 mm'
    assert field.value() == 10
    qtbot.keyClick(editor, Qt.Key_Return)
    assert field.text() == '-2.0000012 mm'
    assert field.value() == -2.0000012

    field.setSingleStep(0.125)
    qtbot.keyClick(editor, Qt.Key_Up)
    assert field.value() == -2.0000012 + 0.125
    assert field.text() == '-1.8750012 mm'

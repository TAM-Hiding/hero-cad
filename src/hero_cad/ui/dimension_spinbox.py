"""Dimensional spin box with Qt's existing precision and input handling."""
from PySide6.QtWidgets import QDoubleSpinBox
from PySide6.QtCore import QLocale


def trim_decimal_zeros(text, locale):
    whole, point, fraction = text.partition(locale.decimalPoint())
    fraction = fraction.rstrip(locale.zeroDigit())
    return whole + point + fraction if fraction else whole


def format_dimension(value, locale, decimals=9):
    """Readout precision matches sketch editors without rounding model values."""
    locale = QLocale(locale)
    locale.setNumberOptions(locale.numberOptions() | QLocale.OmitGroupSeparator)
    return trim_decimal_zeros(locale.toString(float(value), 'f', decimals), locale)


class DimensionSpinBox(QDoubleSpinBox):
    def textFromValue(self, value):
        return trim_decimal_zeros(super().textFromValue(value), self.locale())

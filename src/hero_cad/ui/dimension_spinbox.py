"""Dimensional spin box with Qt's existing precision and input handling."""
from PySide6.QtWidgets import QDoubleSpinBox


class DimensionSpinBox(QDoubleSpinBox):
    def textFromValue(self, value):
        locale = self.locale()
        whole, point, fraction = super().textFromValue(value).partition(locale.decimalPoint())
        fraction = fraction.rstrip(locale.zeroDigit())
        return whole + point + fraction if fraction else whole

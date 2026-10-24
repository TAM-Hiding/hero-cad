"""Small named catalogue of shared Qt actions, not a second modeling engine."""
from dataclasses import dataclass
from PySide6.QtCore import QObject
from PySide6.QtGui import QAction


@dataclass
class Command:
    identifier: str
    action: QAction
    contexts: tuple
    description: str
    reason: str = ''


class CommandRegistry(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.commands = {}

    def register(self, identifier, action, *, contexts=(), description=None):
        if identifier in self.commands:
            raise ValueError(f'Duplicate command {identifier}')
        self.commands[identifier] = Command(identifier, action, contexts,
                                            description or action.toolTip() or action.text())
        return action

    def execute(self, identifier):
        command = self.commands[identifier]
        if not command.action.isEnabled():
            return False
        command.action.trigger()
        return True

    def enable(self, identifier, enabled, reason=''):
        command = self.commands[identifier]
        command.reason = '' if enabled else reason
        command.action.setEnabled(enabled)
        tooltip = command.description + (f'\nUnavailable: {command.reason}' if command.reason else '')
        if command.action.toolTip() != tooltip:
            command.action.setToolTip(tooltip)

    def for_context(self, context):
        return tuple(identifier for identifier, command in self.commands.items() if context in command.contexts)

"""
MDAP CLI - Interface em Tempo Real

Biblioteca para CLI rica do MDAP Agent com:
- Display em tempo real com Rich
- Sistema de eventos pub/sub
- Checkpoints interativos
- Visualizacao de codigo com syntax highlight
"""

from .events import EventBus, Event, EventType
from .display import MDAPDisplay
from .prompts import InteractivePrompt

__all__ = [
    'EventBus',
    'Event',
    'EventType',
    'MDAPDisplay',
    'InteractivePrompt',
]

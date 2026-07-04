from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class CursorDriver(ABC):
    """
    Abstract interface for executing actual OS-level cursor and keyboard actions.
    """
    @abstractmethod
    def click(self, x: int, y: int) -> bool:
        pass

    @abstractmethod
    def type_text(self, text: str) -> bool:
        pass

    @abstractmethod
    def press_key(self, key: str) -> bool:
        pass

    @abstractmethod
    def scroll(self, x: int, y: int, delta_x: int, delta_y: int) -> bool:
        pass

    @abstractmethod
    def navigate(self, url: str) -> bool:
        """
        Navigate to a given URL. Implementation is deferred.
        """
        pass

class OverlayRenderer(ABC):
    """
    Abstract interface for managing the visual UI overlay of the Ghost Cursor.
    """
    @abstractmethod
    def move_to(self, x: int, y: int) -> bool:
        pass

    @abstractmethod
    def flash(self) -> bool:
        pass

class VerifiableCursorDriver(CursorDriver):
    """
    Interface for cursor drivers that can be inspected for validation.
    """
    @abstractmethod
    def get_element_at(self, x: int, y: int) -> Optional[Dict[str, Any]]:
        """
        Returns AX element info dict at (x, y), or None if no element found.
        Used exclusively by ResultObserver for post-action verification.
        """
        pass

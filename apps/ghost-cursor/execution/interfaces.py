from abc import ABC, abstractmethod

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

"""Small, rate-limited volume increments for GTK wheel and touchpad events."""

import time

from gi.repository import Gdk


class VolumeScroll:
    STEP = 2
    INTERVAL = 0.045
    GESTURE_TIMEOUT = 0.25

    def __init__(self, change):
        self.change = change
        self.remainder = 0.0
        self.last_event = float("-inf")
        self.last_step = float("-inf")

    def __call__(self, _widget, event) -> bool:
        if event.direction == Gdk.ScrollDirection.SMOOTH:
            valid, dx, dy = event.get_scroll_deltas()
            if not valid or not dy or abs(dx) > abs(dy):
                return True
            self.feed(-dy, smooth=True)
        elif event.direction in (Gdk.ScrollDirection.UP, Gdk.ScrollDirection.DOWN):
            self.feed(1 if event.direction == Gdk.ScrollDirection.UP else -1, smooth=False)
        return True

    def feed(self, delta: float, *, smooth: bool) -> None:
        now = time.monotonic()
        if now - self.last_event > self.GESTURE_TIMEOUT or self.remainder * delta < 0:
            self.remainder = 0
        self.last_event = now
        self.remainder = self.remainder + delta if smooth else delta
        if abs(self.remainder) < 1:
            return

        direction = 1 if self.remainder > 0 else -1
        # Consume large events without queuing extra changes after the gesture.
        self.remainder = 0
        if now - self.last_step >= self.INTERVAL:
            self.last_step = now
            self.change(direction * self.STEP)

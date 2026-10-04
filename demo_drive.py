"""A pretend GPS that drives along a route, for testing navigation without a car."""
from kivy.clock import Clock

UPDATES_PER_SECOND = 10


class DemoDrive:
    def __init__(self, route, on_position, speed):
        """Calls on_position(lat, lon, heading) as the pretend car moves at speed meters per second."""
        self.route = route
        self.on_position = on_position
        self.speed = speed
        self.along = 0.0
        self.event = Clock.schedule_interval(self.tick, 1 / UPDATES_PER_SECOND)

    def tick(self, dt):
        self.along = min(self.along + self.speed * dt, self.route.length)
        self.on_position(*self.route.point_at(self.along))
        if self.along >= self.route.length:
            self.stop()

    def stop(self):
        self.event.cancel()

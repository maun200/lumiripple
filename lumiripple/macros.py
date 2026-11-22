"""Record and replay key sequences. Tokens are opaque: the input backend creates and understands them."""

MAX_SECONDS, MAX_EVENTS, INSTANT_GAP = 60, 2000, 0.003


class Recording:
    def __init__(self, start):
        self.start, self.events, self.down = start, [], []

    def expired(self, now):
        return now - self.start >= MAX_SECONDS or len(self.events) >= MAX_EVENTS

    def key(self, token, down, now):
        if self.expired(now):
            return
        if down and token not in self.down:
            self.down.append(token)
        elif not down and token in self.down:
            self.down.remove(token)
        else:                                       # auto repeat, or a release without a press
            return
        self.events.append([now, token, down])

    def finish(self, now):
        """Events from time 0; keys still held are released at the end."""
        if not self.events:
            return []
        t0, end = self.events[0][0], max(min(now, self.start + MAX_SECONDS), self.events[-1][0])
        return [[round(t - t0, 4), k, d] for t, k, d in self.events + [[end, k, False] for k in self.down]]


class Player:
    """Plays without blocking. Time runs in macro time, so the speed can change at any moment."""

    def __init__(self, send):
        self.send, self.rest, self.down = send, [], []
        self.name, self.speed, self.pos, self.at, self.began, self.last, self.reason = "", 1.0, 0.0, 0.0, 0.0, None, "done"

    @property
    def active(self):
        return bool(self.rest)

    def start(self, name, events, now, speed=1.0):
        if not self.rest and events:
            self.name, self.rest, self.speed, self.reason = name, [tuple(e) for e in events], speed, "done"
            self.pos, self.at, self.began, self.last = 0.0, now, now, None

    def _to(self, now):
        self.pos += max(now - self.at, 0) * self.speed
        self.at = max(now, self.at)

    def due(self, now):
        return max((self.rest[0][0] - self.pos) / self.speed - max(now - self.at, 0), 0.0) if self.rest else None

    def tick(self, now):
        if not self.rest:
            return
        self._to(now)
        while self.rest and self.rest[0][0] <= self.pos + 1e-9:
            _, token, down = self.rest.pop(0)
            if down:
                self.down.append(token)
                self.last = token
            elif token in self.down:
                self.down.remove(token)
            self.send(token, down)

    def set_speed(self, speed, now):
        self._to(now)
        self.speed = speed

    def instant(self, now):
        self._to(now)
        self.speed = 1.0
        self.rest = [(self.pos + i * INSTANT_GAP, k, d) for i, (_, k, d) in enumerate(self.rest)]

    def abort(self):
        if self.rest:
            self.reason = "cancelled"
        self.rest = []
        for token in list(self.down):
            self.send(token, False)
        self.down.clear()

    def view(self, now, label):
        if not self.rest:
            return None
        gone = max(now - self.began, 0)
        left = max((self.rest[-1][0] - self.pos) / self.speed - max(now - self.at, 0), 0)
        nxt = next((k for _, k, d in self.rest if d), None)
        return {"name": self.name, "speed": self.speed, "elapsed": gone, "total": gone + left,
                "last": None if self.last is None else label(self.last), "next": None if nxt is None else label(nxt)}

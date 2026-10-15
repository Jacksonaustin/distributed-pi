import threading
from datetime import datetime


class EventLog:
    def __init__(self, path):
        self.path = path
        self.entries = []
        self.lock = threading.Lock()

    def log(self, event_type, term, details):
        entry = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "event": event_type,
            "term": term,
            "details": details,
        }
        line = f'{entry["time"]} term={term} {event_type} {details}'
        with self.lock:
            self.entries.append(entry)
            with open(self.path, "a") as f:
                f.write(line + "\n")
        print(line)

    def recent(self, n=20):
        with self.lock:
            return list(self.entries[-n:])

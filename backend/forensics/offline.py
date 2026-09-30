"""Explicit lightweight mode; never pretends AI is running."""
import threading
from fastapi import HTTPException


class UnavailableAI:
    device = 'unavailable'
    status = 'Disabled'
    error = 'Lightweight forensic mode. Install full requirements and enable AI for real inference.'
    active = set()
    lock = threading.RLock()

    def enqueue(self, vid):
        return False  # Upload remains available; video stays UPLOADED.

    def count(self):
        raise RuntimeError(self.error)

    def search(self, **kwargs):
        raise HTTPException(503, self.error)

    def delete_video(self, vid):
        pass

    def close(self):
        pass

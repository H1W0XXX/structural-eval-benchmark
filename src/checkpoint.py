"""Durable task results and stream heartbeats, independent of API credentials."""
import datetime
import json
import os
from pathlib import Path
import threading
import time


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class CheckpointStore:
    def __init__(self, output, config, resume=False):
        self.output = Path(output)
        self.directory = Path(str(output) + '.checkpoint')
        self.directory.mkdir(parents=True, exist_ok=True)
        manifest = self.directory / 'config.json'
        if manifest.exists():
            if not resume:
                raise ValueError('Checkpoint exists; use --resume or a new --output')
            if json.loads(manifest.read_text(encoding='utf-8')) != config:
                raise ValueError('Resume configuration does not match checkpoint')
        else:
            if self.output.exists():
                raise ValueError('Output exists without a checkpoint; choose a new --output')
            atomic_json(manifest, config)
        self.ids = config['task_ids']
        self.results = {}
        for index, task_id in enumerate(self.ids):
            path = self.directory / f'{index:04d}.json'
            if path.exists():
                result = json.loads(path.read_text(encoding='utf-8'))
                if result['id'] != task_id:
                    raise ValueError('Checkpoint task ID mismatch')
                self.results[task_id] = result

    def save(self, result):
        index = self.ids.index(result['id'])
        atomic_json(self.directory / f'{index:04d}.json', result)
        self.results[result['id']] = result
        atomic_json(self.output, [self.results[k] for k in self.ids if k in self.results])


_event_lock = threading.Lock()


def append_event(path, event):
    if path is None:
        return
    event = dict(event, timestamp=datetime.datetime.now().astimezone().isoformat())
    with _event_lock:
        with open(path, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + '\n')
            handle.flush()
            os.fsync(handle.fileno())


class StreamProgress:
    def __init__(self, label, path=None, interval=15):
        self.label = label
        self.path = path
        self.interval = interval
        self.started = time.monotonic()
        self.last_chunk = None
        self.chunks = self.content_chars = self.reasoning_chars = 0
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._heartbeat, daemon=True)

    def emit(self, phase):
        with self.lock:
            current = time.monotonic()
            event = dict(label=self.label, phase=phase, elapsed_s=round(current - self.started, 1),
                         idle_s=round(current - (self.last_chunk or self.started), 1), chunks=self.chunks,
                         content_chars=self.content_chars, reasoning_chars=self.reasoning_chars)
        print(f"[{self.label}] stream {phase}: elapsed={event['elapsed_s']}s idle={event['idle_s']}s "
              f"chunks={event['chunks']} content_chars={event['content_chars']} reasoning_chars={event['reasoning_chars']}", flush=True)
        append_event(self.path, event)

    def start(self):
        self.emit('connecting')
        self.thread.start()

    def received(self, content='', reasoning=''):
        with self.lock:
            self.chunks += 1
            first = self.chunks == 1
            self.last_chunk = time.monotonic()
            self.content_chars += len(content or '')
            self.reasoning_chars += len(reasoning or '')
        if first:
            self.emit('first_chunk')

    def _heartbeat(self):
        while not self.stopped.wait(self.interval):
            self.emit('receiving')

    def close(self):
        self.stopped.set()
        self.thread.join()
        self.emit('closed')

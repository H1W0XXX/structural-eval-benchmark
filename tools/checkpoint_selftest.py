import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.checkpoint import CheckpointStore, StreamProgress
from run_eval import run_task_batch


class CheckpointSelfTest(unittest.TestCase):
    def test_completed_task_survives_later_failure_and_resumes(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'result.json'
            config = {'task_ids': ['a', 'b'], 'max_tokens': 32768}
            store = CheckpointStore(output, config)
            def runner(index, task):
                if task == 'b':
                    raise RuntimeError('interrupted')
                return {'id': task, 'ratio': 1}
            with self.assertRaises(RuntimeError):
                run_task_batch(['a', 'b'], 1, runner, show_progress=False, on_result=store.save)
            self.assertEqual(json.loads(output.read_text())[0]['id'], 'a')
            resumed = CheckpointStore(output, config, resume=True)
            pending = [t for t in config['task_ids'] if t not in resumed.results]
            self.assertEqual(pending, ['b'])
            run_task_batch(pending, 2, lambda i, t: {'id': t, 'ratio': 0.5}, show_progress=False, on_result=resumed.save)
            self.assertEqual([r['id'] for r in json.loads(output.read_text())], ['a', 'b'])

    def test_resume_rejects_changed_config_and_no_resume_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'result.json'
            config = {'task_ids': ['a'], 'max_tokens': 32768}
            CheckpointStore(output, config)
            with self.assertRaises(ValueError):
                CheckpointStore(output, config)
            with self.assertRaises(ValueError):
                CheckpointStore(output, dict(config, max_tokens=8192), resume=True)

    def test_heartbeat_records_idle_and_stream_activity(self):
        with tempfile.TemporaryDirectory() as temp:
            events = Path(temp) / 'events.jsonl'
            progress = StreamProgress('task attempt 1', events, interval=0.01)
            progress.start()
            try:
                progress.received('abc', 'thinking')
                time.sleep(0.04)
            finally:
                progress.close()
            records = [json.loads(s) for s in events.read_text().splitlines()]
            self.assertIn('receiving', [r['phase'] for r in records])
            self.assertEqual(records[-1]['content_chars'], 3)
            self.assertEqual(records[-1]['reasoning_chars'], 8)
            self.assertEqual(records[-1]['chunks'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)

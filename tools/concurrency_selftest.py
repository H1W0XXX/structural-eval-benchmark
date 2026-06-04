import os
import sys
import threading
import time
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from run_eval import run_task_batch


class ConcurrencySelfTest(unittest.TestCase):
    def test_concurrent_results_keep_input_order(self):
        tasks = ["task-0", "task-1", "task-2", "task-3"]

        def runner(index, task):
            time.sleep((len(tasks) - index) * 0.01)
            return {"id": task, "index": index}

        results = run_task_batch(tasks, concurrency=4, task_runner=runner, show_progress=False)

        self.assertEqual([r["id"] for r in results], tasks)
        self.assertEqual([r["index"] for r in results], list(range(len(tasks))))

    def test_concurrency_runs_multiple_tasks_at_once(self):
        tasks = list(range(6))
        lock = threading.Lock()
        active = 0
        max_active = 0

        def runner(index, task):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.03)
            with lock:
                active -= 1
            return task

        results = run_task_batch(tasks, concurrency=3, task_runner=runner, show_progress=False)

        self.assertEqual(results, tasks)
        self.assertGreater(max_active, 1)

    def test_sequential_mode_still_works(self):
        tasks = ["a", "b", "c"]
        seen = []

        def runner(index, task):
            seen.append((index, task))
            return task.upper()

        results = run_task_batch(tasks, concurrency=1, task_runner=runner, show_progress=False)

        self.assertEqual(results, ["A", "B", "C"])
        self.assertEqual(seen, [(0, "a"), (1, "b"), (2, "c")])

    def test_invalid_concurrency_is_rejected(self):
        with self.assertRaises(ValueError):
            run_task_batch([], concurrency=0, task_runner=lambda index, task: task, show_progress=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)

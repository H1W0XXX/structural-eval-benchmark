"""Run both models concurrently; restart interrupted workers from task checkpoints."""
import argparse
from collections import Counter
import datetime
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.checkpoint import atomic_json

MODELS = ['neolink/deepseek-v4.1-flash', 'neolink/glm-5.3-flash']


def now():
    return datetime.datetime.now().astimezone().isoformat()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--worker', choices=MODELS)
    args = parser.parse_args()
    run = Path(args.run_dir).resolve()
    run.mkdir(parents=True, exist_ok=True)
    os.chdir(ROOT)
    if args.worker:
        output = run / ('eval_result_' + args.worker.replace('/', '_') + '.json')
        sys.argv = [str(ROOT / 'run_eval.py'), '--model', args.worker,
                    '--api-base', 'https://vnet.neolink.com/api/v1',
                    '--api-key', os.environ['STRUCTURAL_EVAL_API_KEY'],
                    '--concurrency', '8', '--max-retries', '2', '--max-tokens', '32768',
                    '--reasoning-effort', 'high', '--output', str(output), '--resume',
                    '--progress-interval', '15', '--api-timeout', '120']
        runpy.run_path(str(ROOT / 'run_eval.py'), run_name='__main__')
        return

    state = dict(started_at=now(), launcher_pid=os.getpid(), max_tokens=32768,
                 reasoning_effort='high', concurrency_per_model=8, models=[])
    processes = {}
    def launch(model, entry):
        log_path = run / (model.replace('/', '_') + '.log')
        with log_path.open('a', encoding='utf-8') as log:
            log.write(f'\n=== launch {now()} (resume enabled) ===\n')
            log.flush()
            process = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()),
                                        '--run-dir', str(run), '--worker', model],
                                       stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        processes[model] = process
        entry.update(pid=process.pid, status='running', log=str(log_path))
    for model in MODELS:
        entry = dict(model=model, restarts=0, started_at=now())
        state['models'].append(entry)
        launch(model, entry)
    while True:
        active = False
        for entry in state['models']:
            model = entry['model']
            output = run / ('eval_result_' + model.replace('/', '_') + '.json')
            if output.exists():
                results = json.loads(output.read_text(encoding='utf-8'))
                entry['completed_tasks'] = len(results)
                entry['result'] = str(output)
                entry['reasons'] = dict(Counter(r['reason'] for r in results))
                entry['weighted_accuracy_on_completed'] = 100 * sum(r['score'] for r in results) / sum(r['difficulty'] for r in results) if results else 0
            code = processes[model].poll()
            if code is None:
                active = True
            elif entry['status'] == 'running':
                if code != 0 and entry['restarts'] < 2:
                    entry['restarts'] += 1
                    launch(model, entry)
                    active = True
                else:
                    entry.update(exit_code=code, finished_at=now(),
                                 status='completed' if code == 0 and entry.get('completed_tasks') == 25 else 'failed')
        state['updated_at'] = now()
        if not active:
            state['finished_at'] = now()
        atomic_json(run / 'status.json', state)
        if not active:
            if any(e['status'] != 'completed' for e in state['models']):
                raise SystemExit(1)
            break
        time.sleep(15)


if __name__ == '__main__':
    main()

import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_eval import extract_json, run_chat_completion


class ResponseSelfTest(unittest.TestCase):
    def test_nested_bare_json_with_escaped_strings(self):
        model = {'points': [{'id': 'P1', 'label': 'a } { " \\ b'}], 'links': [], 'supports': [], 'loads': []}
        text = json.dumps(model)
        self.assertEqual(json.loads(extract_json(text)), model)
        self.assertEqual(json.loads(extract_json('Answer:\n' + text + '\nDone.')), model)

    def test_existing_wrappers(self):
        text = '{"points": [{"id": "P1"}], "links": []}'
        for wrapped in [f'<json>{text}</json>', f'```json\n{text}\n```', f'```\n{text}\n```', f'<|begin_of_box|>{text}<|end_of_box|>']:
            self.assertEqual(extract_json(wrapped), text)

    def test_no_json(self):
        self.assertIsNone(extract_json('No answer'))

    def test_stream_records_reasoning_limit_and_usage(self):
        client = Mock()
        usage = Mock()
        usage.model_dump.return_value = {'completion_tokens': 32768}
        client.chat.completions.create.return_value = [
            SimpleNamespace(usage=None, choices=[SimpleNamespace(finish_reason=None, delta=SimpleNamespace(content=None, reasoning_content='thinking'))]),
            SimpleNamespace(usage=None, choices=[SimpleNamespace(finish_reason='length', delta=SimpleNamespace(content=None))]),
            SimpleNamespace(usage=usage, choices=[]),
        ]
        metadata = {}
        self.assertEqual(run_chat_completion(client, 'model', [], max_tokens=32768, metadata=metadata, reasoning_effort='high'), '')
        self.assertEqual(metadata['finish_reason'], 'length')
        self.assertEqual(metadata['reasoning_chars'], 8)
        self.assertEqual(metadata['usage']['completion_tokens'], 32768)
        self.assertEqual(client.chat.completions.create.call_args.kwargs['max_tokens'], 32768)
        self.assertEqual(client.chat.completions.create.call_args.kwargs['reasoning_effort'], 'high')

    def test_api_exception_is_distinct_from_empty_response(self):
        client = Mock()
        client.chat.completions.create.side_effect = RuntimeError('test failure')
        metadata = {}
        self.assertIsNone(run_chat_completion(client, 'model', [], metadata=metadata))
        self.assertEqual(metadata['error'], 'test failure')


if __name__ == '__main__':
    unittest.main(verbosity=2)

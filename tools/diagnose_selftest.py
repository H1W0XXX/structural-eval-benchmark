import copy
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from run_eval import diagnose_failure
from src.solver_bridge import TrussSolver


class DiagnoseFailureSelfTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        model_path = Path("data/raw_models/frame_010.json")
        with model_path.open("r", encoding="utf-8") as f:
            cls.gt_model = json.load(f)
        cls.solver = TrussSolver("bin/framecalc.wasm")

    def _run_case(self, mutate_fn):
        candidate = copy.deepcopy(self.gt_model)
        mutate_fn(candidate)
        partial, msg = diagnose_failure(self.solver, candidate, self.gt_model)
        return partial, msg

    def test_supports_rotate_90_should_be_025(self):
        def mutate(m):
            # Rotate all support directions by +90 degrees.
            for s in m["supports"]:
                s["angleDeg"] = (float(s.get("angleDeg", 0)) + 90.0) % 360.0

        partial, msg = self._run_case(mutate)
        self.assertAlmostEqual(partial, 0.25)
        self.assertIn("boundary conditions", msg.lower())

    def test_loads_double_should_be_075(self):
        def mutate(m):
            # Double all load magnitudes.
            for ld in m["loads"]:
                kind = ld.get("kind")
                if kind == "pointLoad" and "value" in ld:
                    ld["value"] = float(ld["value"]) * 2
                elif kind == "distributedLoad":
                    if "wStart" in ld:
                        ld["wStart"] = float(ld["wStart"]) * 2
                    if "wEnd" in ld:
                        ld["wEnd"] = float(ld["wEnd"]) * 2
                elif kind == "bendingMoment" and "value" in ld:
                    ld["value"] = float(ld["value"]) * 2

        partial, msg = self._run_case(mutate)
        self.assertAlmostEqual(partial, 0.75)
        self.assertIn("loads are incorrect", msg.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)

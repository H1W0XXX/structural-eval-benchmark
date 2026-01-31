import json
import os
from pathlib import Path

class BenchmarkDataLoader:
    def __init__(self, data_root="data"):
        self.root = Path(data_root)
        self.img_dir = self.root / "images"
        self.meta_dir = self.root / "ground_truth_meta"
        self.raw_dir = self.root / "raw_models"

    def load_tasks_for_eval(self):
        """
        加载用于评测的任务列表 (只读 meta 和图片)
        """
        tasks = []
        if not self.meta_dir.exists():
            print(f"Warning: {self.meta_dir} does not exist. Please run tools/generate_gt.py first.")
            return []

        for meta_file in self.meta_dir.glob("*.json"):
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                
                # 校验图片是否存在
                img_name = meta.get("image_filename")
                img_path = self.img_dir / img_name
                if not img_path.exists():
                    print(f"Skipping {meta_file.name}: Image not found at {img_path}")
                    continue

                tasks.append({
                    "id": meta["id"],
                    "difficulty": meta.get("difficulty", 1),
                    "image_path": str(img_path),
                    "gt_solution": meta["solution"] # 里面已经存了算好的正确答案
                })
            except Exception as e:
                print(f"Error loading {meta_file}: {e}")
        
        # 按 ID 排序，保证顺序固定 (e.g. beam_001 先于 beam_002)
        tasks.sort(key=lambda x: x['id'])
        
        return tasks

    def load_raw_models(self):
        """
        加载原始 JSON 模型 (用于 tools/generate_gt.py 生成真值)
        """
        models = []
        for json_file in self.raw_dir.glob("*.json"):
            models.append({
                "id": json_file.stem,
                "path": str(json_file),
                "filename": json_file.name
            })
        return models

    def load_raw_model_by_id(self, task_id):
        """
        [Debug模式专用] 根据 Task ID 读取原始的正确 JSON 文件
        """
        # 假设文件名规则是 {task_id}.json
        # 如果你的 id 是 "frame_001"，文件名也是 "frame_001.json"
        json_path = self.raw_dir / f"{task_id}.json"

        if not json_path.exists():
            # 尝试做一下兼容，有时候 ID 可能不带后缀
            return None

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading raw model {json_path}: {e}")
            return None
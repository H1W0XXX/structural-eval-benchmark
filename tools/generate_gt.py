import sys
import os
import json
from pathlib import Path

# 把项目根目录加到 path，方便 import src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.solver_bridge import TrussSolver
from src.data_loader import BenchmarkDataLoader

def get_difficulty(filename, data):
    name = os.path.splitext(filename)[0]
    
    # User explicit overrides (Legacy)
    if name == "frame_010": return 5
    if name in ["beam_003", "beam_004", "beam_005"]: return 1
    if name in ["beam_001", "beam_002"]: return 2

    # Heuristics for new files
    links = data.get("links", [])
    num_links = len(links)
    
    if "beam" in name:
        # Check for hinges
        has_hinge = False
        for l in links:
            if l.get("endA") == "hinge" or l.get("endB") == "hinge":
                has_hinge = True
                break
        return 2 if has_hinge else 1

    if "truss" in name:
        if num_links > 20: return 4
        if num_links > 10: return 3
        return 2

    if "frame" in name:
        if num_links >= 14: return 5
        if num_links >= 10: return 4
        if num_links >= 5: return 3
        return 2
    
    return 1 # Fallback

def main():
    print("=== Generating Ground Truth Metadata ===")
    
    # 1. 初始化
    loader = BenchmarkDataLoader()
    solver = TrussSolver("bin/framecalc.wasm") # 确保路径对
    
    raw_models = loader.load_raw_models()
    if not raw_models:
        print("No raw models found in data/raw_models/")
        return

    # 确保 meta 目录存在
    loader.meta_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for model_info in raw_models:
        print(f"Processing {model_info['id']}...")
        
        # 读取 5KB 的大 JSON
        with open(model_info['path'], 'r', encoding='utf-8') as f:
            full_json = json.load(f)
        
        # 跑 Solver 算出真值
        # 注意：这里假设 raw json 的格式直接就是 solver 能吃的格式
        # 如果 raw json 包含编辑器杂质，需要这里做一次 cleaning
        solution, error = solver.solve(full_json)
        
        if error or not solution:
            print(f"❌ Failed to solve {model_info['id']}. Error: {error}")
            continue

        # 智能判断图片后缀
        img_name = f"{model_info['id']}.png"
        if not (loader.img_dir / img_name).exists():
            if (loader.img_dir / f"{model_info['id']}.jpg").exists():
                img_name = f"{model_info['id']}.jpg"
            
        # 构造 Meta 数据
        meta_data = {
            "id": model_info['id'],
            "difficulty": get_difficulty(model_info['filename'], full_json),
            "image_filename": img_name, 
            "solution": solution # 缓存正确答案
        }
        
        # 写入 Meta 文件
        out_path = loader.meta_dir / model_info['filename']
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(meta_data, f, indent=2)
            
        print(f"✅ Saved meta to {out_path} (Diff: {meta_data['difficulty']})")
        count += 1

    print(f"\nDone. Generated {count} GT files.")

if __name__ == "__main__":
    main()
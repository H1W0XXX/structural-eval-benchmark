import os
import json
import glob

RAW_DIR = "data/raw_models"
META_DIR = "data/ground_truth_meta"

def get_difficulty(filename, data):
    name = os.path.splitext(filename)[0]
    
    # User explicit overrides
    if name == "frame_010": return 5
    if name in ["beam_003", "beam_004", "beam_005"]: return 1
    if name in ["beam_001", "beam_002"]: return 2

    # Heuristics
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
    raw_files = glob.glob(os.path.join(RAW_DIR, "*.json"))
    print(f"Found {len(raw_files)} raw models.")

    for raw_path in raw_files:
        filename = os.path.basename(raw_path)
        name = os.path.splitext(filename)[0]
        
        # Read raw model
        with open(raw_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        score = get_difficulty(filename, raw_data)
        print(f"[{name}] Difficulty: {score}")

        # Update meta file
        meta_path = os.path.join(META_DIR, filename)
        if os.path.exists(meta_path):
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta_data = json.load(f)
            
            meta_data["difficulty"] = score
            
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta_data, f, indent=2)
        else:
            print(f"Warning: Meta file for {name} not found.")

if __name__ == "__main__":
    main()

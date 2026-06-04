import os
import re
import json
import base64
import argparse
import mimetypes
import copy
from tqdm import tqdm
from openai import OpenAI
import traceback

# 引入项目模块
from src.solver_bridge import TrussSolver
from src.metrics import compute_score
from src.data_loader import BenchmarkDataLoader
from src.prompts import PROMPT_REGISTRY

# 尝试引入 json_repair，如果没有安装则退化到 json
try:
    import json_repair

    JSON_LIB = json_repair
except ImportError:
    import json

    JSON_LIB = json
    print(
        "[Warning] 'json_repair' library not found. Installing it (pip install json_repair) is highly recommended for robust parsing.")


# --- 辅助函数 ---
def encode_image(image_path):
    """将图片文件读取并转换为 Base64 字符串"""
    if not os.path.exists(image_path):
        return None
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = "image/png"
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    return f"data:{mime_type};base64,{encoded_string}"


def extract_json(response_text):
    """从模型回复中提取 <json> 或 markdown 内容"""
    # 1. 尝试找 <json>...</json>
    match = re.search(r'<json>(.*?)</json>', response_text, re.DOTALL)
    if match: return match.group(1).strip()

    # 2. 尝试找 <|begin_of_box|>...<|end_of_box|> (Special token usage)
    match = re.search(r'<\|begin_of_box\|>(.*?)<\|end_of_box\|>', response_text, re.DOTALL)
    if match: return match.group(1).strip()

    # 3. 尝试找 Markdown ```json ... ```
    match = re.search(r'```json(.*?)```', response_text, re.DOTALL)
    if match: return match.group(1).strip()

    # 4. 尝试找 ``` ... ```
    match = re.search(r'```(.*?)```', response_text, re.DOTALL)
    if match: return match.group(1).strip()

    # 5. 找最外层大括号
    match = re.search(r'\{.*?\}', response_text, re.DOTALL)
    if match: return match.group(0).strip()

    return None


def short_text(text, max_len=160):
    """压缩日志文本，避免控制台输出太长。"""
    if not text:
        return ""
    compact = " ".join(str(text).split())
    if len(compact) <= max_len:
        return compact
    return compact[:max_len - 3] + "..."


def run_chat_completion(client, model_name, messages, temperature=0.2, stream_output=False):
    """封装 API 调用，默认只收集完整回复，不逐 token 打印。"""
    try:
        if stream_output:
            print(f"\n[Model Output Start]:")

        stream = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=8192,
            stream=True
        )
        
        full_content = []
        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    if stream_output:
                        print(delta, end="", flush=True)
                    full_content.append(delta)

        if stream_output:
            print(f"\n[Model Output End]\n{'-'*40}")

        return "".join(full_content)

    except Exception as e:
        print(f"\n[API Error] {e}")
        return None


def keep_best_retry_score(
    best_score,
    best_attempt,
    final_details,
    fail_reason,
    candidate_score,
    candidate_attempt,
    candidate_details,
    candidate_reason,
):
    """
    Retry 评分策略：保留历史最高分；同分时保留更早的尝试，便于结果稳定。
    """
    if best_attempt == 0 or candidate_score > best_score:
        return candidate_score, candidate_attempt, candidate_details, candidate_reason
    return best_score, best_attempt, final_details, fail_reason


# --- 诊断相关函数 ---

def apply_standard_load(model):
    """
    移除所有原有载荷，给所有杆件施加世界坐标向下的均布载荷
    """
    model["loads"] = []
    links = model.get("links", [])
    for link in links:
        model["loads"].append({
            "id": f"TEST_LD_{link['id']}",
            "kind": "distributedLoad",
            "at": {"type": "link", "id": link["id"]},
            "wStart": 10,
            "wEnd": 10,
            "angleDeg": 270, # 向下
            "angleMode": "world"
        })
    return model

def apply_uniform_material_and_rigid_joints(model):
    """
    统一材质截面，并将所有连接设为刚接
    """
    for link in model.get("links", []):
        link["E"] = 200e9
        link["A"] = 0.01
        link["Iz"] = 0.0001
        link["density"] = 7850
        # 强制刚接
        link["endA"] = "rigid"
        link["endB"] = "rigid"
    return model

def solve_and_compare_reactions(solver, model_ai, model_gt):
    """
    求解两个模型并对比支座反力
    返回: True (match) / False (mismatch)
    """
    sol_ai, err_ai = solver.solve(model_ai)
    sol_gt, err_gt = solver.solve(model_gt)

    if err_ai or err_gt or not sol_ai or not sol_gt:
        return False # 求解失败视为不匹配

    # 复用 compute_score 的反力对比逻辑 (忽略弯矩)
    # 构造一个伪造的 gt_solution 格式，只包含 reactions
    score, details = compute_score(sol_ai, {"reactions": sol_gt["reactions"], "max_moment": 0}, tolerance=0.05)
    
    # 只要反力匹配即可
    return details.get("reactions_match", False)


def diagnose_failure(solver, ai_json, gt_json):
    """
    执行三步诊断逻辑
    返回: (partial_score, feedback_message)
    """
    # 0. 准备工作：深拷贝以防修改原数据
    ai_base = copy.deepcopy(ai_json)
    gt_base = copy.deepcopy(gt_json)

    # --- Step 1: 几何/拓扑验证 ---
    # 操作：统一材质、刚接、标准载荷
    # ai_s1 = apply_standard_load(apply_uniform_material_and_rigid_joints(copy.deepcopy(ai_base)))
    # gt_s1 = apply_standard_load(apply_uniform_material_and_rigid_joints(copy.deepcopy(gt_base)))
    
    # Refined Step 1:
    def modify_supports_to_fixed(model):
        for sup in model.get("supports", []):
            sup["kind"] = "fixed"
            sup["angleDeg"] = 0 # Reset angle
        return model

    ai_s1 = apply_standard_load(modify_supports_to_fixed(apply_uniform_material_and_rigid_joints(copy.deepcopy(ai_base))))
    gt_s1 = apply_standard_load(modify_supports_to_fixed(apply_uniform_material_and_rigid_joints(copy.deepcopy(gt_base))))
    
    if not solve_and_compare_reactions(solver, ai_s1, gt_s1):
        return 0.0, "The geometric structure is incorrect. Please check node coordinates and member connectivity."

    # --- Step 2: 约束类型验证 ---
    # 操作：恢复原始约束类型，但保持刚接，标准载荷。
    ai_s2 = apply_standard_load(apply_uniform_material_and_rigid_joints(copy.deepcopy(ai_base)))
    gt_s2 = apply_standard_load(apply_uniform_material_and_rigid_joints(copy.deepcopy(gt_base)))
    
    if not solve_and_compare_reactions(solver, ai_s2, gt_s2):
        return 0.25, "The geometry is correct, but the boundary conditions (supports) are incorrect. Check support types and locations."

    # --- Step 3: 连接方式验证 ---
    # 操作：恢复原始连接方式 (Hinge/Rigid)，恢复原始约束，标准载荷。
    def apply_uniform_material_only(model):
        for link in model.get("links", []):
            link["E"] = 200e9
            link["A"] = 0.01
            link["Iz"] = 0.0001
            link["density"] = 7850
        return model

    ai_s3 = apply_standard_load(apply_uniform_material_only(copy.deepcopy(ai_base)))
    gt_s3 = apply_standard_load(apply_uniform_material_only(copy.deepcopy(gt_base)))

    if solve_and_compare_reactions(solver, ai_s3, gt_s3):
        # 结果一样 -> 说明连接方式没问题，之前总算不对是因为 原题载荷(Loads) 错了
        return 0.75, "The structure, supports, and connections are correct. Only the applied loads are incorrect."
    else:
        # 结果不一样 -> 说明连接方式(Joints)有问题
        return 0.50, "Geometry and supports are correct, but the member connection types (hinge/rigid) are incorrect."


def main():
    parser = argparse.ArgumentParser(description="Structural AI Benchmark Evaluator")
    parser.add_argument("--model", type=str, default="debug-mode", help="Model name")
    parser.add_argument("--api-base", type=str, default="http://localhost:8000/v1", help="API URL")
    parser.add_argument("--api-key", type=str, default="EMPTY", help="API Key")
    parser.add_argument("--limit", type=int, default=0, help="Limit tasks")
    parser.add_argument("--max-retries", type=int, default=2, help="Max retry attempts")
    parser.add_argument("--debug", action="store_true", help="Run sanity check using Ground Truth JSON (No AI)")
    parser.add_argument("--prompt-type", type=str, default="standard", choices=PROMPT_REGISTRY.keys())
    parser.add_argument("--filter", type=str, default=None, help="Filter tasks")
    parser.add_argument("--verbose-response", action="store_true", help="Print full streaming model responses to console")

    args = parser.parse_args()

    # 1. System Prompt
    current_system_prompt = PROMPT_REGISTRY.get(args.prompt_type)
    print(f"Loaded Prompt Template: [{args.prompt_type}]")

    # 2. Components
    loader = BenchmarkDataLoader()
    solver = TrussSolver("bin/framecalc.wasm")
    client = OpenAI(api_key=args.api_key, base_url=args.api_base) if not args.debug else None

    # 3. Tasks
    tasks = loader.load_tasks_for_eval()
    if not tasks: return

    if args.filter:
        tasks = [t for t in tasks if args.filter in t['id']]
    if args.limit > 0:
        tasks = tasks[:args.limit]

    print(f"Starting evaluation on {len(tasks)} tasks.")
    results = []

    for task in tqdm(tasks, desc="Evaluating", ascii=True):
        task_id = task['id']
        gt_solution = task['gt_solution']
        if isinstance(gt_solution, list) and len(gt_solution) > 0: gt_solution = gt_solution[0]

        # Load Raw GT Model for diagnosis
        gt_raw_json = loader.load_raw_model_by_id(task_id)

        best_score = 0
        final_details = {}
        fail_reason = "Unknown"
        attempts_used = 0
        best_attempt = 0
        attempt_logs = []

        # --- Debug Mode ---
        if args.debug:
            attempts_used = 1
            ai_json = gt_raw_json
            if not ai_json:
                fail_reason = "GT JSON Missing"
            else:
                ai_solution, solver_error = solver.solve(ai_json)
                if solver_error:
                    fail_reason = f"Physics Solver Crashed: {solver_error}"
                else:
                    score, details = compute_score(ai_solution, gt_solution)
                    best_score = score
                    best_attempt = 1
                    final_details = details
                    fail_reason = "Success" if score == 1.0 else "Wrong Answer"

        # --- AI Mode ---
        else:
            base64_image = encode_image(task['image_path'])
            # 基础对话历史 (System + User/Image)
            base_messages = [
                {"role": "system", "content": current_system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": "Analyze the structure in this image and output the JSON definition."},
                    {"type": "image_url", "image_url": {"url": base64_image}}
                ]}
            ]
            
            # 用于重试的上下文 (Last Assistant Response + Error)
            retry_context = []

            for attempt in range(args.max_retries + 1):
                attempts_used = attempt + 1
                current_temp = 0.6 if attempt == 0 else 0.7
                
                # 构造本次请求的消息列表
                messages = base_messages + retry_context

                tqdm.write(f"[{task_id}] attempt {attempts_used}/{args.max_retries + 1}: requesting API")
                response_text = run_chat_completion(
                    client,
                    args.model,
                    messages,
                    temperature=current_temp,
                    stream_output=args.verbose_response
                )
                attempt_log = {
                    "attempt": attempts_used,
                    "temperature": current_temp,
                    "response_text": response_text,
                    "extracted_json": None,
                    "feedback": "",
                    "score": None,
                    "details": {},
                    "failure": None
                }
                
                if not response_text:
                    fail_reason = "API Failure"
                    attempt_log["failure"] = fail_reason
                    attempt_logs.append(attempt_log)
                    tqdm.write(f"[{task_id}] attempt {attempts_used}: API failure")
                    break

                json_str = extract_json(response_text)
                attempt_log["extracted_json"] = json_str
                error_feedback = ""

                if not json_str:
                    error_feedback = "I cannot find valid JSON. Please output standard JSON inside <json> tags."
                    fail_reason = "Parse Error"
                    attempt_log["failure"] = fail_reason
                else:
                    try:
                        ai_json = JSON_LIB.loads(json_str)
                        ai_solution, solver_error = solver.solve(ai_json)

                        if solver_error:
                            error_feedback = f"Solver Error: {solver_error}. Check connectivity."
                            fail_reason = "Solver Crashed"
                            attempt_log["failure"] = fail_reason
                        elif not ai_solution:
                            error_feedback = "Unstable structure (empty result)."
                            fail_reason = "Unstable"
                            attempt_log["failure"] = fail_reason
                        else:
                            score, details = compute_score(ai_solution, gt_solution)
                            attempt_log["score"] = score
                            attempt_log["details"] = details

                            if score == 1.0:
                                best_score = 1.0
                                best_attempt = attempts_used
                                final_details = details
                                fail_reason = "Success"
                                attempt_log["failure"] = None
                                attempt_logs.append(attempt_log)
                                tqdm.write(f"[{task_id}] attempt {attempts_used}: success")
                                break # Perfect! 
                            else:
                                # ❌ 计算结果不对，启动诊断
                                fail_reason = "Wrong Answer"
                                final_details = details
                                attempt_log["failure"] = fail_reason
                                
                                # 只有当存在 GT Raw Model 时才能诊断
                                if gt_raw_json:
                                    partial_score, diag_feedback = diagnose_failure(solver, ai_json, gt_raw_json)
                                    error_feedback = f"Result incorrect. Diagnostic: {diag_feedback}"
                                    attempt_log["diagnostic_score"] = partial_score
                                    
                                    best_score, best_attempt, final_details, fail_reason = keep_best_retry_score(
                                        best_score,
                                        best_attempt,
                                        final_details,
                                        fail_reason,
                                        partial_score,
                                        attempts_used,
                                        details,
                                        f"Partial: {diag_feedback}",
                                    )
                                else:
                                    error_feedback = "Result incorrect (Reaction forces mismatch)."

                    except Exception as e:
                        error_feedback = f"JSON Syntax Error: {e}"
                        fail_reason = "Syntax Error"
                        attempt_log["failure"] = fail_reason

                attempt_log["feedback"] = error_feedback
                attempt_logs.append(attempt_log)

                # Retry Logic: 只保留最近一次的错误
                if attempt < args.max_retries and error_feedback:
                    tqdm.write(f"[{task_id}] attempt {attempts_used}: {short_text(error_feedback)}")
                    # 更新 retry_context，覆盖掉旧的错误历史
                    retry_context = [
                        {"role": "assistant", "content": response_text},
                        {"role": "user", "content": f"Error: {error_feedback} Fix the JSON."}
                    ]

        # Final Score Calculation: Difficulty * Ratio
        final_score = best_score * task.get("difficulty", 1)

        results.append({
            "id": task_id,
            "score": final_score, # Now this is weighted
            "ratio": best_score,  # Store the raw ratio (0.0 - 1.0)
            "difficulty": task.get("difficulty", 1),
            "reason": fail_reason,
            "attempts_used": attempts_used,
            "best_attempt": best_attempt,
            "details": final_details,
            "attempt_logs": attempt_logs
        })
        tqdm.write(f"[{task_id}] done: ratio={best_score:.2f}, reason={fail_reason}, attempts={attempts_used}")

    # Summary
    total_score = sum(r['score'] for r in results)
    total_possible = sum(r['difficulty'] for r in results) if results else 0
    
    avg_ratio = (sum(r['ratio'] for r in results) / len(results)) * 100 if results else 0
    weighted_acc = (total_score / total_possible) * 100 if total_possible else 0

    print("\n" + "=" * 60)
    print(f"Evaluation Report: {args.model}")
    print(f"Filter: {args.filter if args.filter else 'None'} | Max Retries: {args.max_retries}")
    print("-" * 60)
    print(f"{'Category':<15} | {'Tasks':<8} | {'Score':<10} | {'Max Score':<10} | {'Accuracy':<10}")
    print("-" * 60)

    # Breakdown by Category (Beam, Frame, Truss)
    categories = {'beam': [], 'frame': [], 'truss': []}
    
    for r in results:
        # Determine category from ID prefix (e.g., beam_001 -> beam)
        cat_key = r['id'].split('_')[0].lower()
        if cat_key in categories:
            categories[cat_key].append(r)
        else:
            # Handle unknown prefixes if any
            if 'other' not in categories: categories['other'] = []
            categories['other'].append(r)

    # Print rows
    for cat, items in categories.items():
        if not items: continue # Skip empty categories (e.g. if filtered)
        
        c_score = sum(x['score'] for x in items)
        c_max = sum(x['difficulty'] for x in items)
        c_acc = (c_score / c_max) * 100 if c_max > 0 else 0
        
        print(f"{cat.capitalize():<15} | {len(items):<8} | {c_score:<10.2f} | {c_max:<10.0f} | {c_acc:<9.2f}%")

    print("-" * 60)
    print(f"{'OVERALL':<15} | {len(results):<8} | {total_score:<10.2f} | {total_possible:<10.0f} | {weighted_acc:<9.2f}%")
    print("=" * 60)
    
    output_filename = f"eval_result_{'DEBUG' if args.debug else args.model.replace('/', '_')}.json"
    with open(output_filename, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {output_filename}")

if __name__ == "__main__":
    main()

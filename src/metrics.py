import numpy as np


def extract_values_from_list(raw_list):
    """
    辅助函数：从求解器输出的复杂列表中提取纯数值
    兼容两种格式：
    1. [10.5, -5.0]  (纯数字)
    2. [{"value": 10.5}, {"value": -5.0}] (对象字典)
    """
    values = []
    for item in raw_list:
        if isinstance(item, (int, float)):
            values.append(float(item))
        elif isinstance(item, dict):
            # 优先找 'value' 字段，如果没有则尝试找 'force'
            val = item.get("value", item.get("force", 0.0))
            values.append(float(val))
    return values


def compute_score(ai_solution: dict, gt_solution: dict, tolerance=0.05):
    """
    对比 AI 算出的结果和标准答案
    返回: (score, details_dict)
    score: 0 或 1
    """
    if not ai_solution or not gt_solution:
        return 0, {"reason": "Solution is None"}

    # --- 1. 数据清洗与提取 ---
    # 使用辅助函数提取纯数值列表
    ai_raw_list = extract_values_from_list(ai_solution.get("reactions", []))
    gt_raw_list = extract_values_from_list(gt_solution.get("reactions", []))

    # --- Part A: 支座反力 (Reactions) ---
    # 取绝对值并从大到小排序，消除顺序和正负号的影响
    ai_reacts = sorted([abs(x) for x in ai_raw_list], reverse=True)
    gt_reacts = sorted([abs(x) for x in gt_raw_list], reverse=True)

    reactions_pass = False

    # 对比逻辑
    if len(ai_reacts) == len(gt_reacts):
        # 转换为 numpy 数组方便计算
        ai_arr = np.array(ai_reacts)
        gt_arr = np.array(gt_reacts)

        # 避免分母为 0
        denom = gt_arr.copy()
        denom[denom == 0] = 1.0

        diff = np.abs(ai_arr - gt_arr)

        # 判定标准：绝对误差 < 1e-4 或者 相对误差 < tolerance
        # (这样既能处理大数，也能处理接近0的小数)
        is_close = (diff < 1e-3) | (diff / denom <= tolerance)
        reactions_pass = np.all(is_close)
    else:
        # 支座数量都不对，直接判错
        pass

        # --- Part B: 最大弯矩 (Global Max Moment) ---
    # 同样要处理可能的字典格式，不过 max_moment 通常是个单值
    raw_ai_moment = ai_solution.get("max_moment", 0.0)
    raw_gt_moment = gt_solution.get("max_moment", 0.0)

    # 如果是字典，提取 value
    if isinstance(raw_ai_moment, dict): raw_ai_moment = raw_ai_moment.get("value", 0.0)
    if isinstance(raw_gt_moment, dict): raw_gt_moment = raw_gt_moment.get("value", 0.0)

    ai_moment = abs(float(raw_ai_moment))
    gt_moment = abs(float(raw_gt_moment))

    moment_pass = False
    if gt_moment == 0:
        moment_pass = ai_moment < 1e-3
    else:
        moment_pass = abs(ai_moment - gt_moment) / gt_moment <= tolerance

    # --- 最终判定 ---
    is_correct = reactions_pass and moment_pass

    details = {
        "reactions_match": bool(reactions_pass),
        "moment_match": bool(moment_pass),
        "ai_reacts": ai_reacts,  # 用于调试日志
        "gt_reacts": gt_reacts
    }

    return (1.0 if is_correct else 0.0), details
---
license: cc-by-nc-4.0
task_categories:
- visual-question-answering
- image-to-text
language:
- en
- zh
tags:
- benchmark
- visual-reasoning
- multimodal
- structural-mechanics
- image-to-json
- visual-question-answering
- stem
size_categories:
- n<1K
---

# StructuralEval: 结构力学大模型视觉推理评测基准

**StructuralEval** 是一个专注于**结构力学**领域的垂直大模型评测基准。本项目旨在评估多模态大语言模型（LMMs）在专业工程场景下的**视觉感知**、**空间推理**以及**结构建模**能力。

与传统的数学或通用视觉评测不同，本基准并不要求 AI 直接输出计算结果，而是要求 AI 扮演“建模工程师”的角色，将结构图片转化为计算机可识别的标准结构定义（JSON）。

## 核心理念

**"AI 负责建模，引擎负责计算"**

1.  **视觉转译 (Visual-to-Schema)**: AI 模型输入一张包含梁 (Beam)、刚架 (Frame) 或 桁架 (Truss) 的图片，识别其中的节点坐标、构件连接关系、支座类型（铰接、固接等）以及荷载信息。
2.  **物理验证 (Physics-Based Verification)**: AI 输出的 JSON 模型会被送入内置的 **WASM 物理求解器 (FrameCalc)** 进行有限元分析。
3.  **结果对齐**: 系统通过比较 AI 模型的物理响应（支座反力、最大弯矩）与真值（Ground Truth）来判定 AI 是否真正“读懂”了结构，而非简单的文本匹配。

## 可视化与调试

本项目的 JSON 定义格式与 [FrameCalc 在线结构分析工具](https://framecalc.aeutlook.com/) 完全兼容。

*   **可视化方法**: 您可以将 `data/raw_models/` 中的任何 JSON 文件内容复制并导入到上述网站中，进行图形化查看和结果校核。
*   **经典题目**: 
    *   `frame_010.json`: 该题目源自 **天津大学 2021 年结构力学考研真题**，具有极高的专业难度，挑战 AI 对复杂多跨静定/超静定结构的理解。

## 项目特点

*   **基于真实物理引擎**: 集成 WebAssembly (WASM) 编译的高性能结构求解器，确保评测结果的物理严谨性。
*   **多维度难度分级**: 数据集包含从简单的简支梁到复杂的超静定刚架，难度分为 1-5 级。
    *   **Level 1-2**: 基础梁结构，考察基本的构件与支座识别。
    *   **Level 3**: 简单桁架与刚架，考察节点连接性与多构件推理。
    *   **Level 4-5**: 复杂多跨刚架与大型桁架，考察对复杂拓扑和混合荷载的全局理解。
*   **容错性解析**: 内置鲁棒的 JSON 解析机制，专注于模型内容的准确性，而非格式的微小瑕疵。

## 目录结构

```text
structural-eval-benchmark/
├── bin/                 # 物理求解器核心 (framecalc.wasm)
├── data/
│   ├── images/          # 题目图片 (png/jpg)
│   ├── ground_truth_meta/ # 包含标准答案与难度分级的元数据
│   └── raw_models/      # 原始建模文件 (用于生成 GT)
├── src/                 # 核心源码 (加载器、评测逻辑、Prompt)
├── tools/               # 辅助工具 (生成真值、可视化等)
├── run_eval.py          # 评测主程序
└── requirements.txt     # 依赖清单
```

## 快速开始

### 1. 环境准备

确保安装 Python 3.8+，并安装项目依赖：

```bash
pip install -r requirements.txt
```

*(注：主要依赖包括 `openai`, `tqdm`, `wasmtime` 等)*

### 2. 运行评测

使用 `run_eval.py` 启动评测。您需要提供兼容 OpenAI 接口的模型 API Key。

```bash
# 标准评测模式
python run_eval.py --model "gpt-4o" --api-key "sk-..." 

# 任务过滤 (按 ID 关键字筛选，例如只评测“beam”类题目)
python run_eval.py --model "gemini-3-pro-preview" --api-base https://generativelanguage.googleapis.com/v1beta/openai/ --filter "beam"

# 指定 API Base URL ，允许模型答错后重试3次
python run_eval.py --model "qwen-vl-plus-2025-01-25" --api-base "https://dashscope.aliyuncs.com/compatible-mode/v1" --api-key "sk-..." --max-retries 3
```

### 3. 调试模式 (Debug)

如果您想测试环境或验证 Ground Truth 数据的正确性（不调用 AI）：

```bash
python run_eval.py --debug
```

## 扩展数据集

如果您希望添加新的测试题目，请遵循以下步骤，系统会自动计算难度并生成真值：

1.  **准备数据**:
    *   将结构建模 JSON 放入 `data/raw_models/`。
    *   将对应的图片放入 `data/images/`（支持 .png 或 .jpg）。
2.  **生成真值**:
    运行以下命令，工具会自动调用求解器计算物理真值，并根据构件数量和特征自动打分（Difficulty 1-5）。
    ```bash
    python tools/generate_gt.py
    ```
3.  **开始评测**: 新题目将自动包含在下一次评测中。

## 难度评分标准

*   **Beam (梁)**: 基础分 1 分，含铰接 +1 分。
*   **Frame (刚架)**: 根据构件数量分级 (2-5 分)。
*   **Truss (桁架)**: 根据构件数量分级 (2-4 分)。

## 许可证

本项目采用 **CC BY-NC 4.0 (署名-非商业性使用)** 许可协议：
*   **禁止商用**: 未经许可，不得将本项目及其包含的数据集用于商业目的。
*   **标注来源**: 免费使用的前提是必须在您的项目说明、论文或作品中明确标注本项目来源（StructuralEval 基准）。

## 评分与诊断机制 (Scoring & Diagnosis)

为了更细致地评估模型在结构分析中的思维盲区，本基准采用了一套**分级诊断评分系统**。当 AI 的答案不正确时，系统并不会直接判定为 0 分，而是通过一系列“控制变量”实验来诊断错误原因，并给予部分分数。

### 1. 诊断流程 (Step-by-Step Diagnosis)

当 AI 生成的结构无法通过全量验证时，评测脚本会自动按以下顺序进行排查：

1.  **几何/拓扑检查 (Geometry Check)**:
    *   将 AI 模型与真值模型的材质统一、连接方式全部改为刚接、移除原始载荷并施加统一标准载荷，同时暂时将所有支座改为固定端。
    *   **判定**: 如果此时反力一致，说明**节点位置和杆件连接关系**是正确的。
    *   **失败后果**: 得分 **0.0** (Structure Wrong)。

2.  **边界条件检查 (Support Check)**:
    *   在通过几何检查的基础上，恢复原始的支座定义（保留统一刚接和标准载荷）。
    *   **判定**: 如果此时反力一致，说明**支座类型和位置**是正确的。
    *   **失败后果**: 得分 **0.25** (Supports Wrong)。

3.  **连接方式检查 (Connection Check)**:
    *   在通过上述检查的基础上，恢复原始的构件连接定义（如铰接/刚接），但仍使用标准载荷。
    *   **判定**: 如果此时反力不一致，说明**构件的 Release (铰接) 设置**有误。
    *   **失败后果**: 得分 **0.50** (Connections Wrong)。

4.  **载荷检查 (Load Check)**:
    *   如果上述步骤全对，但原始模型的全量计算结果不对，则唯一剩下的变量是**原题载荷**。
    *   **判定**: 结构完全正确，仅载荷参数错误。
    *   **得分**: **0.75** (Loads Wrong)。

5.  **完全正确 (Perfect)**:
    *   所有物理响应与真值完全匹配。
    *   **得分**: **1.00**。

### 2. 最终得分计算 (Weighted Accuracy)

为了体现题目难度的差异，最终榜单采用**加权准确率**计算：

$$
\text{单题得分} = \text{题目难度 (1-5)} \times \text{诊断系数 (0.0 - 1.0)}
$$

$$
\text{加权准确率 (Weighted Accuracy)} = \frac{\sum \text{所有单题得分}}{\sum \text{所有题目的总难度分}} \times 100\%
$$

例如：
*   一道难度为 **3** 的刚架题，模型结构做对了但载荷写错（系数 0.75），得分为 $3 \times 0.75 = 2.25$。
*   一道难度为 **1** 的梁题，模型全对（系数 1.0），得分为 $1 \times 1.0 = 1.0$。
*   总得分 3.25，满分 4.0，加权准确率为 81.25%。

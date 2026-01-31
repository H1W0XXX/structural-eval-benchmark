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

# StructuralEval: A Visual Reasoning Benchmark for Structural Mechanics

**StructuralEval** is a specialized benchmark designed for the field of **structural mechanics**. It evaluates the **visual perception**, **spatial reasoning**, and **structural modeling** capabilities of Multimodal Large Language Models (MLLMs).

Unlike general visual benchmarks, StructuralEval requires AI to act as a "Modeling Engineer," converting structural diagrams into standardized JSON definitions.

## Core Philosophy

**"AI for Modeling, Engine for Calculation"**

1.  **Visual-to-Schema**: Given an image of a Beam, Frame, or Truss, the AI identifies node coordinates, member connectivity, support types (fixed, pinned, etc.), and loading information.
2.  **Physics-Based Verification**: The AI-generated JSON is fed into the built-in **WASM Physics Solver (FrameCalc)** for finite element analysis.
3.  **Result Alignment**: The system compares the physical response (support reactions, max bending moments) of the AI's model with the Ground Truth (GT). This determines if the AI truly "understands" the structure rather than just matching text patterns.

## Visualization & Debugging

The JSON format used in this project is fully compatible with the [FrameCalc Online Structural Analysis Tool](https://framecalc.aeutlook.com/).

*   **How to Visualize**: You can copy the content of any JSON file from `data/raw_models/` and import it into the website for graphical inspection and result verification.
*   **Classic Case**: 
    *   `frame_010.json`: This task is based on a **2021 Tianjin University Graduate Entrance Exam** problem for Structural Mechanics. It features a complex statically indeterminate structure that poses a significant challenge to AI reasoning.

## Key Features

*   **Integrated Physics Engine**: Uses a high-performance solver compiled to WebAssembly (WASM), ensuring physical rigor in evaluations.
*   **Multi-Level Difficulty**: The dataset ranges from simple beams to complex frames, with difficulty levels from 1 to 5.
    *   **Level 1-2**: Basic beam structures, testing basic member and support identification.
    *   **Level 3**: Simple trusses and frames, testing connectivity and multi-member reasoning.
    *   **Level 4-5**: Complex multi-span frames and large trusses, testing global understanding of complex topologies and mixed loads.
*   **Fault-Tolerant Parsing**: Includes robust JSON extraction and repair mechanisms, focusing on the accuracy of the model content rather than minor formatting issues.

## Directory Structure

```text
structural-eval-benchmark/
├── bin/                 # Physics solver core (framecalc.wasm)
├── data/
│   ├── images/          # Task images (png/jpg)
│   ├── ground_truth_meta/ # Metadata containing GT solutions and difficulty levels
│   └── raw_models/      # Original modeling files (used to generate GT)
├── src/                 # Core source code (loaders, metrics, prompts)
├── tools/               # Helper tools (GT generation, visualization, etc.)
├── run_eval.py          # Main evaluation script
└── requirements.txt     # Dependency list
```

## Quick Start

### 1. Installation

Ensure you have Python 3.8+ installed, then install dependencies:

```bash
pip install -r requirements.txt
```

### 2. Run Evaluation

Use `run_eval.py` to start the evaluation. You need to provide an API key compatible with the OpenAI interface.

```bash
# Standard evaluation
python run_eval.py --model "gpt-4o" --api-key "sk-..." 

# Filter tasks (e.g., only evaluate "beam" tasks)
python run_eval.py --model "gemini-1.5-pro" --api-base "https://..." --filter "beam"

# Enable retries (allows the model to fix errors up to 3 times)
python run_eval.py --model "qwen-vl-max" --api-key "sk-..." --max-retries 3
```

### 3. Debug Mode

To test your environment or verify Ground Truth data without calling the AI API:

```bash
python run_eval.py --debug
```

## Scoring & Diagnosis

To precisely identify the "blind spots" in AI reasoning, we use a **Step-by-Step Diagnostic System**. If an answer is incorrect, the system performs "controlled experiments" to diagnose the root cause and awards partial credit.

### 1. Diagnostic Workflow

If the full verification fails, the script executes the following checks:

1.  **Geometry Check**:
    *   The system unifies materials, sets all connections to rigid, applies a standard downward load, and forces all supports to "Fixed".
    *   **Result**: If reactions match, the **Geometry (nodes and members)** is correct.
    *   **Failure**: Score **0.0**.

2.  **Support Check**:
    *   Based on a correct geometry, the system restores original support types but keeps rigid connections and standard loads.
    *   **Result**: If reactions match, the **Support types and locations** are correct.
    *   **Failure**: Score **0.25**.

3.  **Connection Check**:
    *   Restores original connection types (e.g., hinges/releases) but keeps standard loads.
    *   **Result**: If reactions do not match, the **Member releases (hinges)** are incorrect.
    *   **Failure**: Score **0.50**.

4.  **Load Check**:
    *   If all structural elements are correct but the full calculation still fails, the error must lie in the **Applied Loads**.
    *   **Result**: The physical structure is perfect; only load parameters are wrong.
    *   **Score**: **0.75**.

5.  **Perfect Match**:
    *   All physical responses match the ground truth.
    *   **Score**: **1.00**.

### 2. Weighted Accuracy Calculation

Final scores are weighted by the difficulty of the tasks:

$$
\text{Task Score} = \text{Difficulty (1-5)} \times \text{Diagnostic Ratio (0.0 - 1.0)}
$$ 

$$ 
\text{Weighted Accuracy} = \frac{\sum \text{Task Scores}}{\sum \text{Total Possible Difficulty}} \times 100\%
$$ 

## License

This project is licensed under **CC BY-NC 4.0 (Attribution-NonCommercial 4.0 International)**:
*   **Non-Commercial**: You may not use this project or its dataset for commercial purposes without permission.
*   **Attribution**: You must give appropriate credit to this project (StructuralEval Benchmark) in any publications or derivative works.

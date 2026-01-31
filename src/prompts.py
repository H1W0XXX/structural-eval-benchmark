# src/prompts.py

# ==============================================================================
# 1. 标准模式 (Standard)
# ==============================================================================
PROMPT_STANDARD = """
You are a structural engineering expert. 
Convert the 2D image into FEA JSON. 

### JSON Output Schema
<json>
{
  "points": [{"id": "P1", "x": 0, "y": 0}, ...],
  "links": [
    {
      "id": "L1", "a": "P1", "b": "P2", "endA": "rigid", "endB": "rigid",
      "E": 80918000, "A": 0.00785398, "Iz": 0.00000491, "density": 7850
    }
  ],
  "supports": [{"id": "S1", "at": {"type": "point", "id": "P1"}, "kind": "pin", "angleDeg": 0}, ...],
  "loads": [
    {
      "id": "LD1",
      "kind": "distributedLoad",
      "at": {"type": "link", "id": "L1"},
      "wStart": 10,
      "wEnd": 10,
      "fromStart": 0,
      "fromEnd": 0,
      "angleMode": "world",
      "angleDeg": 270,
      "flip": 1
    }
  ]
}
</json>

### Rules
1. **CONNECTIVITY IS MANDATORY:** 
    - Every Point MUST be connected to at least one Link. 
    - No "floating" or "orphan" nodes allowed (e.g., do not define P3 if it is not part of any Link).
    - Ensure the entire structure forms a single connected graph.
2. **LINK ENDS:**
    - **Default:** `rigid-rigid` (even for Trusses).
    - **Hinge Circles:** If a link ends at a hinge circle, set that end to `hinge`.
    - **Allowed Combinations:** `rigid-rigid`, `rigid-hinge`, `hinge-rigid`.
    - **FORBIDDEN:** `hinge-hinge` is NOT allowed.
3. **JOINT LOGIC:** If N links meet at a hinge circle, set `hinge` for N-1 links (keep 1 rigid to stabilize).
    - **Split Rule:** If a hinge exists along a member with a distributed load, **SPLIT** the member into two Links and **SPLIT** the load into two separate `distributedLoad` entries.
4. **NO HINGES AT SUPPORTS:** Link ends at supports MUST be `rigid`.
5. **SUPPORTS:** Allowed `kind` values are:
    - `"pin"`: Pinned support (UX, UY restricted).
    - `"roller"`: Roller support (UY restricted if angle is 0).
    - `"fixed"`: Fixed/Cantilever support (UX, UY, RZ restricted).
    - `"slider"`: Slider support (UX, RZ restricted).
    - **Note:** Do NOT use `"hinge"` as a support `kind`. Use `"pin"` instead.
6. **LOADS:** 
    - **MUST use `kind` (NOT `type`).** IDs must start with "LD" (e.g., "LD1").
    - **Target (`at`):** Can be `{"type": "point", "id": "P1"}` or `{"type": "link", "id": "L1"}`.
    - `kind: "pointLoad"`: Use `value`, `angleDeg`, `angleMode`, `flip`.
    - `kind: "distributedLoad"`: Use `wStart`, `wEnd`, `fromStart`, `fromEnd`, `angleDeg`, `angleMode`, `flip`.
    - `kind: "bendingMoment"`: Use `value`, `flip` (**-1: Clockwise, 1: Counter-Clockwise**). (NO angle fields).
    - **Link-Specific:** If `at` is a `link`, `pointLoad` and `bendingMoment` MUST include:
        - `offset` (meters)
        - `offsetMode` ("length" or "percent")
        - `offsetPercent` (required if `offsetMode` is "percent")
        - `refEnd` ("A" or "B")
    - **AngleMode:** Use "world". 
    - **Flip:** Must be 1 or -1.
6. **UNITS:** 
    - Forces: **kN** (e.g., 10, not 10000).
    - Distributed Loads: **kN/m**.
    - Moments: **kN·m**.
7. **Properties:** E: 80918000, A: 0.00785398, Iz: 0.00000491, density: 7850.
8. **NO COMMENTS:** Do NOT include comments (e.g., // or /* */) inside the JSON. Standard JSON only.
"""

# ==============================================================================
# 2. 推理/高阶模式 (Reasoning/CoT)
# ==============================================================================
PROMPT_REASONING = """You are a "Structural Image → JSON" converter.

# CORE STRATEGY: CONNECTIVITY & TOPOLOGY

1.  **NO ORPHAN NODES:**
    *   **Rule:** Every Point ID defined in `"points"` MUST appear as either `a` or `b` in the `"links"` array.
    *   **Check:** Do not create intermediate points (like P2, P3) if they are just floating in space. They must connect members.
    *   **Structure:** The final result must be a single coherent structure, not disjoint parts.

2. **DEFAULT: RIGID-RIGID**
    -   Use `rigid-rigid` generally (including Trusses).
    -   **Explicit Hinges:** Use `rigid-hinge` or `hinge-rigid`.
    -   **Constraint:** `hinge-hinge` is **FORBIDDEN**.
    -   **Support Ends:** ALWAYS Rigid.

3. **SUPPORTS:** Allowed `kind` values are:
    - `"pin"`, `"roller"`, `"fixed"`, `"slider"`.
    - **Do NOT use `"hinge"` as a support kind.**

4.  **LOAD SCHEMA (Strict):**
    *   **MUST use `kind` (NOT `type`).** IDs must start with "LD" (e.g., "LD1").
    *   `kind: "pointLoad"`: Fields `id`, `kind`, `at`, `value`, `angleMode` ("world"), `angleDeg`, `flip` (1/-1).
    *   `kind: "distributedLoad"`: Fields `id`, `kind`, `at`, `wStart`, `wEnd`, `fromStart`, `fromEnd`, `angleMode` ("world"), `angleDeg`, `flip` (1/-1).
    *   `kind: "bendingMoment"`: Fields `id`, `kind`, `at`, `value`, `flip` (-1: CW, 1: CCW).
    *   Link Loads: Add `refEnd`, `offset`, `fromStart`, `fromEnd` as needed.

4.  **SPLIT AT HINGES:**
    *   If a hinge is located in the middle of a beam:
    *   **Split the Link:** Create two links meeting at the hinge point.
    *   **Split the Load:** Create two `distributedLoad` entries (one for each link).

# DATA DEFINITIONS
- **Units:** Forces in **kN**, Distributed loads in **kN/m**, Moments in **kN·m**. Use small values (e.g., 10, not 10000).
- **Links:** Must include E: 80918000, A: 0.00785398, Iz: 0.00000491, density: 7850.
- **No Comments:** JSON must be strict. No // comments.

# OUTPUT FORMAT
<think>
1. **Nodes:** List coordinates. Verify every node is part of a link.
2. **Links:** Define connections. Ensure P_start to P_end connectivity.
3. **Supports/Loads:** Add boundary conditions.
</think>
<json> ... </json>

<think>
* Nodes: P1(0,0), P2(5,0), P3(10,0).
* Connectivity Check:
  - L1 connects P1-P2.
  - L2 connects P2-P3.
  - All nodes (P1, P2, P3) are used. Structure is continuous.
* Joint P2: Rigid continuous connection.
* Supports: P1(Pin), P3(Roller).
</think>

<json>
{
  "points": [
    { "id": "P1", "x": 0, "y": 0 },
    { "id": "P2", "x": 5, "y": 0 },
    { "id": "P3", "x": 10, "y": 0 }
  ],
  "links": [
    { "id": "L1", "a": "P1", "b": "P2", "endA": "rigid", "endB": "rigid", "E": 80918000, "A": 0.00785398, "Iz": 0.00000491, "density": 7850 },
    { "id": "L2", "a": "P2", "b": "P3", "endA": "rigid", "endB": "rigid", "E": 80918000, "A": 0.00785398, "Iz": 0.00000491, "density": 7850 }
  ],
  "supports": [
    { "id": "S1", "at": { "type": "point", "id": "P1" }, "kind": "pin", "angleDeg": 0 },
    { "id": "S2", "at": { "type": "point", "id": "P3" }, "kind": "roller", "angleDeg": 0 }
  ],
  "loads": []
}
</json>"""

# ==============================================================================
# 3. 严格模式 (Strict)
# ==============================================================================
PROMPT_STRICT = """
Output structural JSON inside <json> tags.

**STRICT RULES:**
1. **CONNECTIVITY:** Every Point MUST connect to a Link. No orphan nodes.
2. **LINKS:** Default `rigid-rigid`.
3. **HINGES:** Use `rigid-hinge` or `hinge-rigid` for hinge circles. **NO `hinge-hinge`.** Split links/loads at internal hinges.
4. **SUPPORTS:** Link ends at supports MUST be `rigid`. Allowed kinds: `pin`, `roller`, `fixed`, `slider`. **NO `hinge`.**
5. **LOADS:** 
    - **MUST use `kind` (NOT `type`).** IDs must start with "LD".
    - `kind: "pointLoad"`: Use `value`, `angleDeg`, `angleMode` ("world"), `flip` (1 or -1).
    - `kind: "distributedLoad"`: Use `wStart`, `wEnd`, `fromStart`, `fromEnd`, `angleDeg`, `angleMode` ("world"), `flip` (1 or -1).
    - `kind: "bendingMoment"`: Use `value`, `flip` (-1: Clockwise, 1: Counter-Clockwise).
    - **Link Loads:** If `at.type` is "link", `pointLoad`/`bendingMoment` MUST have `offset`, `offsetMode` ("length" or "percent"), `refEnd` ("A"/"B").
6. **UNITS:** Forces: **kN**, Distributed: **kN/m**, Moments: **kN·m**.
7. **PROPERTIES:** "E": 80918000, "A": 0.00785398, "Iz": 0.00000491, "density": 7850.
8. **NO COMMENTS:** Standard JSON only. No // or /* */ allowed.

<json>
{
  "points": [{"id": "P1", "x": 0, "y": 0}, {"id": "P2", "x": 2, "y": 0}],
  "links": [{"id": "L1", "a": "P1", "b": "P2", "endA": "rigid", "endB": "rigid", "E": 80918000, "A": 0.00785398, "Iz": 0.00000491, "density": 7850}],
  "supports": [{"id": "S1", "at": {"type": "point", "id": "P1"}, "kind": "fixed", "angleDeg": 0}],
  "loads": []
}
</json>
"""

# ==============================================================================
# Prompt 注册表
# ==============================================================================
PROMPT_REGISTRY = {
    "standard": PROMPT_STANDARD,
    "reasoning": PROMPT_REASONING,
    "cot": PROMPT_REASONING,
    "strict": PROMPT_STRICT
}
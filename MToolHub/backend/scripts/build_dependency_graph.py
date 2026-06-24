"""
build_dependency_graph.py - Tool Dependency Graph (TDG) 构建脚本

三层流水线：
  第 0 层：参数结构化抽取
  第 1 层：编码器语义召回（bge-m3 / PubMedBERT）
  第 2 层：单位兼容性确定性过滤
  第 3 层：LLM 语义验证

运行方式：
    python scripts/build_dependency_graph.py \
        --converter-json /path/to/tool_unit_metadata.json \
        --calculator-json /path/to/tools_metadata.json \
        --output data/registry/tool_dependency_graph.json \
        --embedding-model /path/to/bge-m3 \
        --similarity-threshold 0.5 \
        --skip-llm  # 跳过第三层 LLM 验证（调试用）
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ============================================================================
# 同义词表：将 calculator 参数名归一化到 converter 的物质名
# ============================================================================
SUBSTANCE_SYNONYMS = {
    # 肾功能
    "bun": "urea_nitrogen",
    "blood_urea_nitrogen": "urea_nitrogen",
    "urea": "urea_nitrogen",
    # 电解质
    "na": "sodium",
    "serum_sodium": "sodium",
    "k": "potassium_k",
    "serum_potassium": "potassium_k",
    "ca": "calcium",
    "serum_calcium": "calcium",
    "ionized_calcium": "calcium_ionized",
    "mg": "magnesium",
    # 肝功能
    "bili": "bilirubin",
    "tbili": "bilirubin",
    "total_bilirubin": "bilirubin",
    "direct_bilirubin": "bilirubin_direct",
    "indirect_bilirubin": "bilirubin_indirect",
    "ast": "aspartate_aminotransferase_ast",
    "sgot": "aspartate_aminotransferase_ast",
    "alt": "alanine_aminotransferase_alt",
    "sgpt": "alanine_aminotransferase_alt",
    # 血液
    "hb": "hemoglobin",
    "hgb": "hemoglobin",
    "haemoglobin": "hemoglobin",
    "hct": "hematocrit",
    "plt": "platelet",
    "platelets": "platelet",
    "wbc": "white_blood_cell",
    # 代谢
    "glu": "glucose",
    "blood_glucose": "glucose",
    "fasting_glucose": "glucose",
    "serum_glucose": "glucose",
    "cr": "creatinine",
    "scr": "creatinine",
    "serum_creatinine": "creatinine",
    # 蛋白质
    "alb": "albumin",
    "serum_albumin": "albumin",
    "tp": "total_protein",
    # 脂类
    "ldl": "ldl_cholesterol",
    "hdl": "hdl_cholesterol",
    "tg": "triglyceride",
    "triglycerides": "triglyceride",
    "chol": "cholesterol",
    "total_cholesterol": "cholesterol",
    # 其他
    "pco2": "carbon_dioxide_partial_pressure",
    "po2": "oxygen_partial_pressure",
    "hba1c": "glycated_hemoglobin_hba1c",
    "inr": "international_normalized_ratio_inr",
    "psa": "prostate_specific_antigen_psa",
    "tsh": "thyroid_stimulating_hormone_tsh",
    "t3": "triiodothyronine_t3",
    "t4": "thyroxine_t4",
    "crp": "c_reactive_protein",
    "esr": "erythrocyte_sedimentation_rate",
    "fibrinogen": "fibrinogen",
    "ferritin": "ferritin",
    "iron": "iron",
    "transferrin": "transferrin",
    "uric_acid": "uric_acid",
    "lactate": "lactic_acid",
    "ammonia": "ammonia",
    "phosphorus": "phosphorus",
    "phosphate": "phosphorus",
}

# 常见单位正则模式
UNIT_PATTERN = re.compile(
    r"(?:in|requires?|expects?|units?:?)\s+"
    r"((?:u|m|n|p|k|c|d)?(?:mol|g|L|IU|U|Eq|mL|dL|mm|cm|kg|lbs?|lb|in|ft|"
    r"cells?|mmHg|kPa|sec|min|hr|day|wk|mo|yr|%|Celsius|Fahrenheit|mg)"
    r"(?:\s*/\s*(?:L|dL|mL|mm3|m2|m3|hr|min|sec|day|kg|100mL|100ml))?)",
    re.IGNORECASE
)

# 更宽松的单位提取（直接从 options 或 description 中找到单位字符串）
SI_UNIT_INDICATORS = re.compile(
    r"(umol/L|mmol/L|nmol/L|pmol/L|"
    r"micromol/L|"
    r"g/L|mg/L|ug/L|ng/L|pg/L|"
    r"g/dL|mg/dL|ug/dL|ng/dL|"
    r"mEq/L|IU/L|mIU/L|uIU/mL|"
    r"U/L|mU/L|kU/L|"
    r"cells/uL|cells/mm3|"
    r"kg|cm|mmHg|kPa|kg/m2|"
    r"mL/min|Celsius|mmol/mol|%)",
    re.IGNORECASE
)


# ============================================================================
# 第 0 层：参数结构化抽取
# ============================================================================

def extract_converter_params(converter_json_path: str) -> List[Dict[str, Any]]:
    """从 tool_unit_metadata.json 提取 converter 参数池。

    每个 converter 产出一个 output 记录（物质名 + 支持的单位列表）。
    """
    with open(converter_json_path, "r", encoding="utf-8") as f:
        converters = json.load(f)

    params = []
    for conv in converters:
        fn = conv.get("function_name", "")
        # 从 function_name 提取物质名：convert_xxx_unit -> xxx
        substance = fn.replace("convert_", "").replace("_unit", "")

        # 提取支持的单位列表
        units = conv.get("units", [])
        if not units:
            # fallback：从 parameters 的 options 字段解析
            for p in conv.get("parameters", []):
                if p.get("name") in ("input_unit", "target_unit"):
                    opts = p.get("options", "")
                    units = [u.strip().strip("'\"") for u in opts.split(",")]
                    break

        # 构造描述文本（用于编码器匹配，不含单位）
        name = conv.get("name", "")
        short_desc = conv.get("short_description", "")
        # 去掉描述中的单位部分，只保留物质语义
        semantic_desc = re.sub(r"between:?\s*.*$", "", short_desc).strip()
        if not semantic_desc:
            semantic_desc = name.replace("Unit Converter", "").strip()

        params.append({
            "tool_id": f"tool-unit:{fn}",
            "tool_type": "converter",
            "param_role": "output",
            "substance": substance,
            "description": semantic_desc,
            "encoding_text": f"{substance.replace('_', ' ')}, {semantic_desc}",
            "supported_units": units,
            "function_name": fn,
        })

    return params


def extract_calculator_params(calculator_json_path: str) -> List[Dict[str, Any]]:
    """从 tools_metadata.json 提取 calculator 参数池。

    每个 calculator 的每个 input 参数产出一条记录。
    """
    with open(calculator_json_path, "r", encoding="utf-8") as f:
        calculators = json.load(f)

    params = []
    for calc in calculators:
        fn = calc.get("function_name", "")
        calc_name = calc.get("name", fn)
        calc_desc = calc.get("short_description", "")

        input_schema = calc.get("parameters", [])
        if not isinstance(input_schema, list):
            continue

        for param in input_schema:
            param_name = param.get("name", "")
            param_desc = param.get("description", "")
            param_type = param.get("type", "")
            param_options = param.get("options", "")

            # 只关注数值类型参数（可能需要单位转换）
            if param_type not in ("float", "int", "number"):
                continue

            # 提取描述中提到的单位
            required_unit = None
            unit_matches = SI_UNIT_INDICATORS.findall(param_desc)
            if unit_matches:
                required_unit = unit_matches[0]

            # 归一化参数名
            normalized_name = param_name.lower().strip()
            # 通过同义词表查找
            substance = SUBSTANCE_SYNONYMS.get(normalized_name, normalized_name)

            params.append({
                "tool_id": f"tool-mdcalc:{fn}",
                "tool_type": "calculator",
                "param_role": "input",
                "param_name": param_name,
                "substance": substance,
                "description": param_desc,
                "encoding_text": f"{param_name.replace('_', ' ')}, {param_desc}",
                "required_unit": required_unit,
                "calculator_name": calc_name,
                "calculator_desc": calc_desc,
                "function_name": fn,
            })

    return params


# ============================================================================
# 第 1 层：编码器语义召回
# ============================================================================

def encode_params(params: List[Dict[str, Any]], model) -> np.ndarray:
    """用编码器将参数描述编码为向量。"""
    texts = [p["encoding_text"] for p in params]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    return np.array(embeddings, dtype=np.float32)


def semantic_recall(
    converter_params: List[Dict[str, Any]],
    calculator_params: List[Dict[str, Any]],
    converter_embeddings: np.ndarray,
    calculator_embeddings: np.ndarray,
    top_k: int = 10,
    threshold: float = 0.5,
) -> List[Dict[str, Any]]:
    """第一层：语义召回候选边。

    对每个 converter output，找出与哪些 calculator inputs 语义相似。
    """
    # 余弦相似度矩阵：(num_converters, num_calculator_params)
    similarity_matrix = converter_embeddings @ calculator_embeddings.T

    candidates = []
    for i, conv in enumerate(converter_params):
        scores = similarity_matrix[i]
        # 找 top-k 且超过阈值的
        top_indices = np.argsort(scores)[::-1][:top_k]

        for j in top_indices:
            score = float(scores[j])
            if score < threshold:
                break

            calc_param = calculator_params[j]
            candidates.append({
                "converter": conv,
                "calculator_param": calc_param,
                "similarity_score": round(score, 4),
            })

    print(f"[Layer 1] Semantic recall: {len(candidates)} candidate edges "
          f"(from {len(converter_params)} converters x {len(calculator_params)} calc params)")
    return candidates


# ============================================================================
# 第 2 层：单位兼容性确定性过滤
# ============================================================================

def unit_compatibility_filter(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """第二层：检查单位兼容性，过滤不合理的候选。

    规则：
    1. converter 的 supported_units 必须包含 calculator 参数要求的单位
    2. 物质名需要一致或可通过同义词表映射
    """
    filtered = []
    for cand in candidates:
        conv = cand["converter"]
        calc_param = cand["calculator_param"]

        # 检查物质名一致性
        conv_substance = conv["substance"].lower()
        calc_substance = calc_param["substance"].lower()

        # 去掉常见前缀和数字后缀进行比较
        def normalize_substance(s):
            s = re.sub(r"_([\d]+)$", "", s)  # remove trailing numbers like glucose_249
            s = s.replace("serum_", "").replace("blood_", "").replace("urine_", "")
            return s

        conv_norm = normalize_substance(conv_substance)
        calc_norm = normalize_substance(calc_substance)

        # 匹配规则：精确匹配、或 converter 物质是 calc 物质的全词 (total_bilirubin matches bilirubin)
        substance_match = (
            conv_norm == calc_norm
            or conv_norm.endswith("_" + calc_norm)  # total_bilirubin -> bilirubin
            or conv_norm.startswith(calc_norm + "_")  # bilirubin_direct if calc asks bilirubin
            or calc_norm == conv_norm
        )

        if not substance_match:
            continue

        # 检查单位兼容性
        required_unit = calc_param.get("required_unit")
        # 归一化 Unicode: 将各种 micro sign 统一为 ASCII u
        def normalize_unit_str(s):
            return s.lower().strip().replace("\u00b5", "u").replace("\u03bc", "u")

        supported_units = [normalize_unit_str(u) for u in conv.get("supported_units", [])]

        # 单位别名映射（description 中的自然语言写法 -> 标准缩写）
        UNIT_ALIASES = {
            "micromol/l": "umol/l",
            "milligram/dl": "mg/dl",
            "milligram/l": "mg/l",
            "microgram/l": "ug/l",
            "nanogram/l": "ng/l",
            "picogram/l": "pg/l",
            "millimol/l": "mmol/l",
            "nanomol/l": "nmol/l",
            "picomol/l": "pmol/l",
        }

        unit_compatible = False
        unit_info = {"type": "UNKNOWN"}

        if required_unit:
            required_normalized = normalize_unit_str(required_unit)
            # Apply alias
            required_normalized = UNIT_ALIASES.get(required_normalized, required_normalized)

            if required_normalized in supported_units:
                unit_compatible = True
                non_si_alternatives = [
                    u for u in conv.get("supported_units", [])
                    if normalize_unit_str(u) != required_normalized
                ]
                unit_info = {
                    "type": "CONVERTIBLE",
                    "target_unit": required_unit,
                    "alternative_units": non_si_alternatives,
                }
        else:
            # 没有明确的单位要求，但物质名匹配，标记为 UNCERTAIN
            unit_compatible = True
            unit_info = {"type": "UNCERTAIN"}

        if unit_compatible:
            cand["unit_info"] = unit_info
            filtered.append(cand)

    print(f"[Layer 2] Unit filter: {len(filtered)} edges passed "
          f"(filtered {len(candidates) - len(filtered)} incompatible)")
    return filtered


# ============================================================================
# 第 3 层：LLM 语义验证
# ============================================================================

def build_llm_prompt(candidate: Dict[str, Any]) -> str:
    """构造 LLM 验证 prompt。"""
    conv = candidate["converter"]
    calc_param = candidate["calculator_param"]
    unit_info = candidate.get("unit_info", {})

    prompt = f"""Given the following tool dependency candidate:

- Source tool: {conv['function_name']} (Unit Converter)
  Converts: {conv['substance'].replace('_', ' ')}
  Supported units: {', '.join(conv.get('supported_units', []))}

- Target tool: {calc_param['function_name']} ({calc_param['calculator_name']})
  Description: {calc_param['calculator_desc']}
  Target parameter: "{calc_param['param_name']}"
  Parameter description: "{calc_param['description']}"
  Required unit: {unit_info.get('target_unit', 'not specified')}

- Unit compatibility: {unit_info.get('type', 'UNKNOWN')}
- Semantic similarity: {candidate['similarity_score']}

Question: Is this a valid clinical dependency? Specifically:
1. Does the converter handle the exact same substance that the calculator parameter needs?
2. Would a clinician realistically need to convert this value before using the calculator?
3. Are there any semantic conflicts (e.g., serum vs urine, baseline vs current)?

Respond ONLY in JSON format:
{{"valid": true/false, "confidence": 0.0-1.0, "reason": "brief explanation"}}"""
    return prompt


def llm_verify_batch(
    candidates: List[Dict[str, Any]],
    api_key: str,
    model: str = "deepseek/deepseek-r1",
    confidence_threshold: float = 0.7,
    openrouter: bool = False,
) -> List[Dict[str, Any]]:
    """第三层：批量 LLM 验证（支持 Anthropic 和 OpenRouter）。"""
    if openrouter:
        try:
            from openai import OpenAI
        except ImportError:
            print("[ERR] openai SDK not installed: pip install openai")
            for cand in candidates:
                cand["llm_confidence"] = None
                cand["llm_reason"] = "no openai SDK"
            return candidates
        client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
        def call_llm(prompt):
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=200,
            )
            return resp.choices[0].message.content.strip()
    else:
        try:
            import anthropic
        except ImportError:
            print("[ERR] anthropic SDK not installed")
            for cand in candidates:
                cand["llm_confidence"] = None
                cand["llm_reason"] = "no anthropic SDK"
            return candidates
        client = anthropic.Anthropic(api_key=api_key)
        def call_llm(prompt):
            resp = client.messages.create(
                model=model, max_tokens=200, temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()

    verified = []
    for i, cand in enumerate(candidates):
        prompt = build_llm_prompt(cand)
        try:
            text = call_llm(prompt)
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json.loads(text)
            cand["llm_valid"] = result.get("valid", False)
            cand["llm_confidence"] = result.get("confidence", 0.0)
            cand["llm_reason"] = result.get("reason", "")
            if result.get("valid") and result.get("confidence", 0) >= confidence_threshold:
                verified.append(cand)
        except Exception as e:
            cand["llm_valid"] = None
            cand["llm_confidence"] = None
            cand["llm_reason"] = f"error: {str(e)[:100]}"
            verified.append(cand)

        if (i + 1) % 10 == 0:
            print(f"  [Layer 3] Verified {i+1}/{len(candidates)}")

    print(f"[Layer 3] LLM verify: {len(verified)} confirmed (rejected {len(candidates) - len(verified)})")
    return verified


# ============================================================================
# 输出：构建 TDG JSON
# ============================================================================

def build_tdg_json(edges: List[Dict[str, Any]]) -> Dict[str, Any]:
    """将验证后的边集构造为 TDG JSON 格式。"""
    from datetime import datetime

    # 去重：同一对 (converter, calculator, param) 只保留相似度最高的
    seen = {}
    for edge in edges:
        key = (
            edge["converter"]["tool_id"],
            edge["calculator_param"]["tool_id"],
            edge["calculator_param"]["param_name"],
        )
        if key not in seen or edge["similarity_score"] > seen[key]["similarity_score"]:
            seen[key] = edge

    unique_edges = list(seen.values())

    # 构建边列表
    edge_list = []
    for edge in unique_edges:
        conv = edge["converter"]
        calc_param = edge["calculator_param"]
        unit_info = edge.get("unit_info", {})

        edge_list.append({
            "src": conv["tool_id"],
            "dst": calc_param["tool_id"],
            "src_output_field": "converted_value",
            "dst_input_param": calc_param["param_name"],
            "substance": conv["substance"],
            "unit_from": unit_info.get("alternative_units", []),
            "unit_to": unit_info.get("target_unit", ""),
            "similarity_score": edge["similarity_score"],
            "llm_confidence": edge.get("llm_confidence"),
            "llm_reason": edge.get("llm_reason", ""),
        })

    # 构建邻接表（按 calculator 分组）
    adjacency = {}
    for e in edge_list:
        dst = e["dst"]
        if dst not in adjacency:
            adjacency[dst] = {"prerequisites": [], "params": {}}
        if e["src"] not in adjacency[dst]["prerequisites"]:
            adjacency[dst]["prerequisites"].append(e["src"])
        adjacency[dst]["params"][e["dst_input_param"]] = {
            "converter": e["src"],
            "target_unit": e["unit_to"],
            "alternative_units": e["unit_from"],
        }

    # 统计
    converters_with_edges = len(set(e["src"] for e in edge_list))
    calculators_with_edges = len(adjacency)

    tdg = {
        "version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "construction_method": "embedding_recall + unit_filter + llm_verify",
        "statistics": {
            "total_edges": len(edge_list),
            "unique_converters": converters_with_edges,
            "unique_calculators": calculators_with_edges,
        },
        "edges": edge_list,
        "adjacency": adjacency,
    }

    return tdg


# ============================================================================
# 主流程
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Build Tool Dependency Graph (TDG)")
    parser.add_argument("--converter-json", default=None,
                        help="Path to tool_unit_metadata.json")
    parser.add_argument("--calculator-json", default=None,
                        help="Path to tools_metadata.json")
    parser.add_argument("--output", default="data/registry/tool_dependency_graph.json",
                        help="Output TDG JSON path")
    parser.add_argument("--embedding-model", default=None,
                        help="Path to sentence-transformers model (bge-m3)")
    parser.add_argument("--similarity-threshold", type=float, default=0.5,
                        help="Minimum cosine similarity for recall (layer 1)")
    parser.add_argument("--top-k", type=int, default=15,
                        help="Top-k candidates per converter (layer 1)")
    parser.add_argument("--from-json", default=None,
                        help="Skip Layers 0-2, load existing TDG JSON and only run LLM verification")
    parser.add_argument("--skip-llm", action="store_true",
                        help="Skip layer 3 LLM verification")
    parser.add_argument("--api-key", default=None,
                        help="Anthropic API key for LLM verification")
    parser.add_argument("--openrouter", action="store_true",
                        help="Use OpenRouter API instead of Anthropic")
    parser.add_argument("--llm-model", default="deepseek/deepseek-r1")
    parser.add_argument("--confidence-threshold", type=float, default=0.7,
                        help="Minimum LLM confidence to accept edge")
    args = parser.parse_args()

    print("=" * 60)
    print("Tool Dependency Graph (TDG) Builder")
    print("=" * 60)

    # ── --from-json 快速模式：跳过 0-2 层，直接从已有 JSON 做 LLM 验证 ──────
    if args.from_json:
        print(f"\n[Mode] Loading existing TDG from: {args.from_json}")
        with open(args.from_json, "r", encoding="utf-8") as f:
            existing = json.load(f)
        existing_edges = existing["edges"]
        print(f"  Loaded {len(existing_edges)} edges")

        # 需要元数据文件来重建完整的 candidate 格式（为 LLM prompt 提供描述）
        if not args.converter_json or not args.calculator_json:
            print("[ERR] --from-json requires --converter-json and --calculator-json for LLM prompt context")
            sys.exit(1)

        conv_params = extract_converter_params(args.converter_json)
        calc_params = extract_calculator_params(args.calculator_json)
        # 建立索引
        conv_map = {p["tool_id"]: p for p in conv_params}
        calc_map = {}
        for p in calc_params:
            key = (p["tool_id"], p["param_name"])
            calc_map[key] = p

        # 重建 candidate 格式
        filtered = []
        for e in existing_edges:
            conv = conv_map.get(e["src"])
            calc = calc_map.get((e["dst"], e["dst_input_param"]))
            if not conv or not calc:
                continue
            filtered.append({
                "converter": conv,
                "calculator_param": calc,
                "similarity_score": e.get("similarity_score", 0.0),
                "unit_info": {
                    "type": "CONVERTIBLE",
                    "target_unit": e.get("unit_to", ""),
                    "alternative_units": e.get("unit_from", []),
                },
            })
        print(f"  Reconstructed {len(filtered)} candidates for LLM verification")
        # 跳到第三层
    else:
        # ── 第 0 层：参数抽取 ─────────────────────────────────────────────────
        if not args.converter_json or not args.calculator_json:
            print("[ERR] --converter-json and --calculator-json are required")
            sys.exit(1)
        print("\n[Layer 0] Extracting parameters...")
        converter_params = extract_converter_params(args.converter_json)
        calculator_params = extract_calculator_params(args.calculator_json)
        print(f"  Converters: {len(converter_params)} output params")
        print(f"  Calculators: {len(calculator_params)} input params (numeric only)")

        # ── 第 1 层：编码器召回 ───────────────────────────────────────────────
        print("\n[Layer 1] Semantic recall with embedding model...")
        if args.embedding_model:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(args.embedding_model)
        else:
            try:
                from sentence_transformers import SentenceTransformer
                default_paths = ["/data/wxb/models/bge-m3", "/app/models/bge-m3", "BAAI/bge-m3"]
                model = None
                for p in default_paths:
                    try:
                        model = SentenceTransformer(p)
                        print(f"  Loaded model from: {p}")
                        break
                    except Exception:
                        continue
                if model is None:
                    raise RuntimeError("Cannot load embedding model")
            except ImportError:
                print("  [ERR] sentence-transformers not installed!")
                sys.exit(1)

        converter_embeddings = encode_params(converter_params, model)
        calculator_embeddings = encode_params(calculator_params, model)

        candidates = semantic_recall(
            converter_params, calculator_params,
            converter_embeddings, calculator_embeddings,
            top_k=args.top_k,
            threshold=args.similarity_threshold,
        )

        # ── 第 2 层：单位兼容性过滤 ──────────────────────────────────────────
        print("\n[Layer 2] Unit compatibility filtering...")
        filtered = unit_compatibility_filter(candidates)

    # ── 第 3 层：LLM 验证 ────────────────────────────────────────────────
    if args.skip_llm:
        print("\n[Layer 3] Skipped (--skip-llm)")
        verified = filtered
        for cand in verified:
            cand["llm_confidence"] = None
            cand["llm_reason"] = "LLM verification skipped"
    else:
        print(f"\n[Layer 3] LLM verification ({len(filtered)} candidates)...")
        api_key = args.api_key
        if not api_key:
            api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
        if not api_key:
            print("  [WARN] No API key provided, skipping LLM verification")
            verified = filtered
            for cand in verified:
                cand["llm_confidence"] = None
                cand["llm_reason"] = "No API key"
        else:
            verified = llm_verify_batch(
                filtered, api_key, args.llm_model, args.confidence_threshold,
                openrouter=args.openrouter,
            )

    # ── 输出 ─────────────────────────────────────────────────────────────
    print("\n[Output] Building TDG JSON...")
    tdg = build_tdg_json(verified)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(tdg, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"TDG built successfully!")
    print(f"  Output: {output_path}")
    print(f"  Total edges: {tdg['statistics']['total_edges']}")
    print(f"  Converters with edges: {tdg['statistics']['unique_converters']}")
    print(f"  Calculators with edges: {tdg['statistics']['unique_calculators']}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

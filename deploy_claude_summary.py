# deploy_claude_dashboard_summary.py
from tabpy.tabpy_tools.client import Client
import pandas as pd
import json
import os
from anthropic import Anthropic
from difflib import get_close_matches

# -----------------------------
# Load data once on server start
# -----------------------------
BASE = "Dataset"

df_patient_exp = pd.read_excel(f"{BASE}/Patient_experience.xlsx")
df_infections  = pd.read_excel(f"{BASE}/Infections.xlsx")
df_readmissions= pd.read_excel(f"{BASE}/Readmission.xlsx")
df_deathcomp   = pd.read_excel(f"{BASE}/Complication_and_Death.xlsx")
df_timely      = pd.read_excel(f"{BASE}/Timely care with join.xlsx")


# -----------------------------
# Helpers
# -----------------------------
def ensure_cols(df, cols, df_name):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"{df_name} is missing columns: {missing}")

def _norm(s: str) -> str:
    return str(s).strip().casefold()

def norm_series(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.casefold()

def to_num(x):
    try:
        if isinstance(x, str) and x.strip().lower() in {
            "not applicable", "not available", "na", "n/a", "nan", ""
        }:
            return None
        return float(x)
    except Exception:
        return None

def _collect_facility_names(*dfs):
    names = set()
    for d in dfs:
        if "Facility Name" in d.columns:
            names.update(map(str, d["Facility Name"].dropna().unique()))
    return sorted(n for n in names if n and str(n).strip())

ALL_FACILITY_NAMES = _collect_facility_names(
    df_patient_exp, df_infections, df_readmissions, df_deathcomp, df_timely
)
FACILITY_INDEX = {_norm(n): n for n in ALL_FACILITY_NAMES}

def _resolve_facility_name(user_input: str) -> tuple[str, str]:
    """
    Returns (resolved_name, note).
    If exact not found, tries fuzzy match.
    """
    if not user_input:
        return "", "No facility selected."

    n = _norm(user_input)
    if n in FACILITY_INDEX:
        return FACILITY_INDEX[n], ""

    candidates = get_close_matches(user_input, ALL_FACILITY_NAMES, n=1, cutoff=0.88)
    if candidates:
        chosen = candidates[0]
        return chosen, f"(Resolved to closest match: {chosen})"

    suggestions = get_close_matches(user_input, ALL_FACILITY_NAMES, n=5, cutoff=0.6)
    if suggestions:
        sug = " | ".join(suggestions)
        return "", f"Facility not found: '{user_input}'. Did you mean one of: {sug}?"

    return "", f"Facility not found: '{user_input}'."

def add_norm_facility_col(df: pd.DataFrame) -> pd.DataFrame:
    if "Facility Name" in df.columns and "_facility_norm" not in df.columns:
        df["_facility_norm"] = norm_series(df["Facility Name"])
    return df

def filter_facility(df: pd.DataFrame, facility_resolved: str) -> pd.DataFrame:
    """
    Filter by facility using normalized match.
    """
    df = add_norm_facility_col(df)
    return df[df["_facility_norm"] == _norm(facility_resolved)]


# Normalize once for all dataframes (so we don't recompute per call)
df_patient_exp = add_norm_facility_col(df_patient_exp)
df_infections  = add_norm_facility_col(df_infections)
df_readmissions= add_norm_facility_col(df_readmissions)
df_deathcomp   = add_norm_facility_col(df_deathcomp)
df_timely      = add_norm_facility_col(df_timely)


# -----------------------------
# Measure metadata (units + directionality)
# Only define what you're confident about; fallback exists.
# -----------------------------
MEASURE_META = {
    # ED Flow (minutes; lower is better)
    "OP_18b": {"name": "ED throughput time (median)", "unit": "minutes", "better": "lower"},
    "OP_18c": {"name": "ED throughput time (median) - psych/mental health", "unit": "minutes", "better": "lower"},
    "OP_22": {"name": "ED access measure (OP_22)", "unit": "percent", "better": "lower"},
    # Sepsis (percent; higher is better)
    "SEP_1":       {"name": "Sepsis bundle (SEP-1)", "unit": "percent", "better": "higher"},
    "SEP_SH_3HR":  {"name": "Septic shock care within 3 hours", "unit": "percent", "better": "higher"},
    "SEP_SH_6HR":  {"name": "Septic shock care within 6 hours", "unit": "percent", "better": "higher"},
    "SEV_SEP_3HR": {"name": "Severe sepsis care within 3 hours", "unit": "percent", "better": "higher"},
    "SEV_SEP_6HR": {"name": "Severe sepsis care within 6 hours", "unit": "percent", "better": "higher"},

    # Prevention/Safety examples (percent; higher is better)
    "IMM_3": {"name": "Healthcare personnel influenza vaccination", "unit": "percent", "better": "higher"},
    "VTE_1": {"name": "VTE prophylaxis", "unit": "percent", "better": "higher"},
    "VTE_2": {"name": "VTE prophylaxis (additional)", "unit": "percent", "better": "higher"},
    "HCP_COVID_19": {"name": "Healthcare personnel COVID-19 vaccination", "unit": "percent", "better": "higher"},

    # ED volume is usually categorical/context, not "better/worse"
    "EDV": {"name": "Emergency department volume", "unit": "category", "better": "context"},

}

def meta_for(mid: str) -> dict:
    mid = str(mid or "").strip()
    m = MEASURE_META.get(mid)
    if m:
        return m
    return {"name": mid, "unit": "unknown", "better": "unknown"}


# -----------------------------
# Endpoint function
# -----------------------------
def claude_dashboard_summary(facility_name):
    """
    Tableau passes a string (facility name).
    Returns a single multi-line string for display in Tableau.
    """
    # Handle Tableau passing lists
    if isinstance(facility_name, (list, tuple)) and facility_name:
        facility_name = facility_name[0]
    facility_name = str(facility_name or "").strip()

    resolved, note = _resolve_facility_name(facility_name)
    if not resolved:
        return note

    # -----------------------------
    # Infections (SIR; lower is better)
    # -----------------------------
    INFECTION_IDS = ["HAI_1_SIR","HAI_2_SIR","HAI_3_SIR","HAI_4_SIR","HAI_5_SIR","HAI_6_SIR"]
    ensure_cols(df_infections, ["Facility Name","Measure ID","Score"], "Infections")

    infection_f = filter_facility(df_infections, resolved)
    infection_f = infection_f[infection_f["Measure ID"].isin(INFECTION_IDS)][["Measure ID","Score"]].reset_index(drop=True)

    inf_compact = []
    for _, r in infection_f.iterrows():
        v = to_num(r["Score"])
        if v is not None:
            inf_compact.append({
                "name": str(r["Measure ID"]),
                "value": round(v, 3),
                "unit": "sir",
                "better": "lower"
            })

    # -----------------------------
    # Death & Complications (rates; lower is better)
    # Keep "Compared to National" for safe relative statements
    # -----------------------------
    DEATHCOMP_IDS = [
        "MORT_30_AMI","MORT_30_CABG","MORT_30_COPD","MORT_30_HF","MORT_30_PN","MORT_30_STK",
        "COMP_HIP_KNEE","PSI_03","PSI_04","PSI_06","PSI_08","PSI_09","PSI_10",
        "PSI_11","PSI_12","PSI_13","PSI_14","PSI_15","PSI_90"
    ]
    ensure_cols(df_deathcomp, ["Facility Name","Measure ID","Score","Compared to National"], "Complication & Death")

    deathcomp_f = filter_facility(df_deathcomp, resolved)
    deathcomp_f = deathcomp_f[deathcomp_f["Measure ID"].isin(DEATHCOMP_IDS)][
        ["Measure ID","Score","Compared to National"]
    ].reset_index(drop=True)

    dc_compact = []
    for _, r in deathcomp_f.iterrows():
        v = to_num(r["Score"])
        entry = {
            "name": str(r.get("Measure ID")),
            "value": round(v, 3) if v is not None else None,
            "unit": "rate",
            "better": "lower"
        }
        ctn = r.get("Compared to National")
        if isinstance(ctn, str) and ctn.strip():
            entry["compared_to_national"] = ctn.strip()
        dc_compact.append(entry)

    # -----------------------------
    # Readmissions (diff = predicted - expected; negative is better)
    # -----------------------------
    ensure_cols(
        df_readmissions,
        ["Facility Name","Measure Name","Predicted Readmission Rate","Expected Readmission Rate"],
        "Readmission"
    )

    readmit_f = filter_facility(df_readmissions, resolved)[
        ["Measure Name","Predicted Readmission Rate","Expected Readmission Rate"]
    ].reset_index(drop=True)

    readm_compact = []
    if not readmit_f.empty:
        rtmp = readmit_f.copy()
        rtmp["pred"] = pd.to_numeric(rtmp["Predicted Readmission Rate"], errors="coerce")
        rtmp["exp"]  = pd.to_numeric(rtmp["Expected Readmission Rate"], errors="coerce")
        rtmp["diff"] = rtmp["pred"] - rtmp["exp"]
        rtmp = rtmp.dropna(subset=["pred","exp","diff"]).sort_values("diff", ascending=False).head(3)

        readm_compact = [
            {
                "name": str(row["Measure Name"]),
                "predicted": round(row["pred"], 3),
                "expected": round(row["exp"], 3),
                "difference": round(row["diff"], 3),
                "better": "lower"  # lower difference (negative) indicates fewer readmissions than expected
            }
            for _, row in rtmp.iterrows()
        ]

    # -----------------------------
    # Timely Care (ED flow, sepsis, prevention/safety)
    # FIXED: missing comma previously caused sepsis IDs to be lost
    # -----------------------------
    ensure_cols(df_timely, ["Facility Name","Measure ID","Score"], "Timely Care")

    timely_whitelist = {
        "EDV",
        "ED_2_Strata_1","ED_2_Strata_2",  # if present; can help ED access context
        "IMM_3","OP_18b","OP_18c","HCP_COVID_19",
        "SEP_1","SEP_SH_3HR","SEP_SH_6HR","SEV_SEP_3HR","SEV_SEP_6HR",
        "VTE_1","VTE_2",
        "OP_22","OP_23","OP_29","OP_31","OP_40"
    }

    timely_f = filter_facility(df_timely, resolved)[["Measure ID","Score"]].reset_index(drop=True)

    timely_compact = []
    for _, r in timely_f.iterrows():
        mid = str(r.get("Measure ID") or "").strip()
        if mid in timely_whitelist:
            raw = r.get("Score")
            meta = meta_for(mid)

            # EDV can be categorical (low/medium/high). Keep it as text if numeric conversion fails.
            v_num = to_num(raw)
            if v_num is not None:
                timely_compact.append({
                    "name": meta["name"],
                    "value": round(v_num, 3),
                    "unit": meta["unit"],
                    "better": meta["better"],
                    "id": mid
                })
            else:
                # Keep categorical/context scores as text safely
                s = str(raw).strip()
                if s and s.lower() not in {"not available", "not applicable", "na", "n/a", "nan"}:
                    timely_compact.append({
                        "name": meta["name"],
                        "value_text": s,
                        "unit": meta["unit"],
                        "better": meta["better"],
                        "id": mid
                    })

    # -----------------------------
    # Patient Experience (no national benchmark added per your instruction)
    # -----------------------------
    ensure_cols(df_patient_exp, ["Facility Name","HCAHPS Measure ID","HCAHPS Linear Mean Value"], "Patient Experience")

    px_keep_ids = {
        "H_COMP_1_LINEAR_SCORE","H_COMP_2_LINEAR_SCORE","H_COMP_3_LINEAR_SCORE",
        "H_COMP_5_LINEAR_SCORE","H_COMP_6_LINEAR_SCORE","H_COMP_7_LINEAR_SCORE",
        "H_CLEAN_LINEAR_SCORE","H_QUIET_LINEAR_SCORE",
        "H_HSP_RATING_LINEAR_SCORE","H_RECMND_LINEAR_SCORE"
    }

    patient_f = filter_facility(df_patient_exp, resolved)[
        ["HCAHPS Measure ID","HCAHPS Linear Mean Value"]
    ].reset_index(drop=True)

    px_compact = []
    for _, r in patient_f.iterrows():
        mid = str(r.get("HCAHPS Measure ID") or "").strip()
        if mid in px_keep_ids:
            v = to_num(r.get("HCAHPS Linear Mean Value"))
            if v is not None:
                px_compact.append({
                    "id": mid,
                    "value": round(v, 2),
                    "unit": "linear_mean",
                    "better": "higher"
                })

    # -----------------------------
    # Compact payload for Claude
    # -----------------------------
    compact = {
        "facility": resolved,
        "patient_experience": px_compact,
        "infections": inf_compact,
        "readmissions": readm_compact,
        "mortality_complications": dc_compact,
        "timely_care": timely_compact
    }
    compact_str = json.dumps(compact, separators=(",", ":"))

    # -----------------------------
    # Prompt (Removed external links to reduce hallucinations)
    # Embedded directionality rules + strict comparison rules
    # -----------------------------
    directionality_rules = (
        "Metric interpretation rules:\n"
        "- Time measures in minutes: lower is better.\n"
        "- Compliance measures in percent: higher is better.\n"
        "- Infection SIR: lower is better.\n"
        "- Mortality/complication rates: lower is better.\n"
        "- ED volume categories (if present) are context only, not good/bad.\n"
        "- Only make 'compared to national' statements when the data explicitly includes a comparison label.\n"
    )

    prompt = f"""
You are a hospital quality and performance analyst writing for executive leadership.

Using only the provided JSON performance data for the facility: {resolved},
produce a one-screen, executive-ready performance summary suitable for display
inside a Tableau dashboard.

Formatting rules (important):
- Do NOT use Markdown.
- Do NOT use hashtags (#), asterisks (*), or bullet symbols.
- Use plain text only.
- Separate sections using line breaks.
- Use short section titles followed by paragraphs or hyphen-free sentences.

Structure the output exactly as follows:

AI-Assisted Performance Summary
Facility Name

Overall Performance Snapshot
(2–3 concise sentences summarizing overall performance using only what the data supports)

Key Strengths
(2-3 short sentences highlighting the strongest areas supported by the data)

Priority Concerns
(3–4 short sentences identifying underperforming or high-risk areas supported by the data)

Key Interconnections
(1–2 sentences linking related patterns WITHOUT implying causality)

Prioritized Actions
(2–3 concise, process-focused recommendations directly tied to the weakest metrics)

Content rules:
- Base all insights strictly on the provided metrics.
- Avoid causal claims; describe patterns only.
- Do not introduce new programs, technologies, staffing assumptions, or speculative causes.
- Do not reference internal variable names.
- Do not use measure IDs; use the provided metric names when available.
- Prioritize insights in proportion to dashboard prominence: ED flow and access, sepsis timeliness, readmissions, and patient experience.
- Keep the tone neutral and executive-friendly.
- Do not exceed 200-250 words.

{directionality_rules}

JSON:
{compact_str}
""".strip()

    # -----------------------------
    # Call Claude
    # -----------------------------
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return ("[Configuration error] ANTHROPIC_API_KEY is not set on the TabPy server.\n"
                "Set it and restart TabPy.")

    try:
        anthropic = Anthropic(api_key=api_key)
        resp = anthropic.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=900,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip() if resp.content else ""
        if not text:
            text = "[Claude returned an empty response.]"
        return (f"{note}\n\n{text}" if note else text)

    except Exception as e:
        return f"[Claude error] {type(e).__name__}: {e}"


# -----------------------------
# Deploy
# -----------------------------
if __name__ == "__main__":
    client = Client("http://localhost:9004/")
    client.deploy(
        "claude_dashboard_summary",
        claude_dashboard_summary,
        description="Claude-generated hospital performance summary for a given facility name.",
        override=True,
    )
    print("Deployed endpoint: claude_dashboard_summary")

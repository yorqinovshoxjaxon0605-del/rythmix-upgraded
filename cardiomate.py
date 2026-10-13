import json
import random
import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any

import httpx
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="CardioMate Cardiac AI Predictor")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "cardiomate_history.db"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL_NAME = "llama3"


def init_db() -> None:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cardiac_analysis_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            risk_score REAL NOT NULL,
            status TEXT NOT NULL,
            signal_variance REAL NOT NULL,
            active_drugs TEXT NOT NULL,
            comorbidities TEXT NOT NULL,
            selected_lead TEXT NOT NULL,
            ai_recommendation TEXT NOT NULL,
            ai_source TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


init_db()


def log_to_sql(
    risk_score: float,
    status: str,
    variance: float,
    drugs: List[str],
    comorbidities: List[str],
    selected_lead: str,
    recommendation: str,
    source: str,
) -> None:
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """
            INSERT INTO cardiac_analysis_logs 
            (timestamp, risk_score, status, signal_variance, active_drugs, comorbidities, selected_lead, ai_recommendation, ai_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                timestamp,
                risk_score,
                status,
                variance,
                json.dumps(drugs),
                json.dumps(comorbidities),
                selected_lead,
                recommendation,
                source,
            ),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"SQL Log Error: {e}")


# --- DATA MODEL ---
class CardiacAnalysisRequest(BaseModel):
    ecg_signal: Optional[List[List[float]]] = None
    drugs: Optional[List[str]] = []
    comorbidities: Optional[List[str]] = []
    selected_lead: Optional[str] = "II"


# --- ENDPOINTS ---
@app.get("/")
def root() -> Dict[str, str]:
    return {
        "status": "CardioMate AI Engine Active",
        "mode": "12-Lead Electrocardiogram Analyzer",
        "database": f"SQLite Connected ({DB_FILE})"
    }


@app.post("/predict")
async def predict_risk(payload: CardiacAnalysisRequest) -> Dict[str, Any]:
    signals = payload.ecg_signal
    if signals and len(signals) > 0:
        lead_ii = signals[1] if len(signals) > 1 else signals[0]
        mean_ii = sum(lead_ii) / len(lead_ii) if lead_ii else 0.0
        signal_variance = (
            float(sum((x - mean_ii) ** 2 for x in lead_ii) / len(lead_ii))
            if lead_ii
            else 0.05
        )
    else:
        signal_variance = 0.05

    drugs = payload.drugs or []
    comorbidities = payload.comorbidities or []
    selected_lead = payload.selected_lead or "II"

    # Dynamic Pediatric Vitals Engine
    base_hr = 138
    base_sys, base_dia = 85, 52
    base_lvef = 58
    base_spo2 = 98

    if "Epinephrine" in drugs:
        base_hr += 18
        base_sys += 12
        base_dia += 6
    if "Milrinone" in drugs:
        base_lvef += 6
        base_sys -= 4
    if "Amiodarone" in drugs:
        base_hr -= 15
    if "Dopamine" in drugs:
        base_hr += 10
        base_sys += 8

    if "Baseline Hypotension" in comorbidities:
        base_sys -= 15
        base_dia -= 10
    if "Congenital Defect Watch" in comorbidities:
        base_spo2 -= 4
        base_lvef -= 5

    map_val = int(base_dia + (base_sys - base_dia) / 3)

    is_anomaly = (
        signal_variance > 0.15 
        or len(comorbidities) >= 3 
        or "ST-Segment Shift Analysis" in comorbidities
    )

    if is_anomaly:
        imminent_risk = round(random.uniform(0.65, 0.88), 2)
        decomp_risk = round(random.uniform(0.50, 0.75), 2)
        status = "CRITICAL_ALERT"
    else:
        imminent_risk = round(random.uniform(0.08, 0.22), 2)
        decomp_risk = round(random.uniform(0.15, 0.35), 2)
        status = "STABLE"

    risk_score = imminent_risk

    ollama_analysis = await query_ollama_ai(
        variance=signal_variance,
        is_anomaly=is_anomaly,
        drugs=drugs,
        comorbidities=comorbidities,
        selected_lead=selected_lead
    )

    recommendation = str(ollama_analysis.get("recommendation", ""))
    source = str(ollama_analysis.get("source", ""))

    log_to_sql(
        risk_score=risk_score,
        status=status,
        variance=signal_variance,
        drugs=drugs,
        comorbidities=comorbidities,
        selected_lead=selected_lead,
        recommendation=recommendation,
        source=source
    )

    return {
        "risk_score": risk_score,
        "status": status,
        "selected_lead": selected_lead,
        "signal_variance": round(signal_variance, 4),
        "active_drugs": drugs,
        "comorbidities": comorbidities,
        "vitals": {
            "hr": base_hr,
            "bp": f"{base_sys}/{base_dia}",
            "bp_sys": base_sys,
            "bp_dia": base_dia,
            "map": map_val,
            "spo2": base_spo2,
            "lvef": base_lvef
        },
        "multi_horizon_risk": {
            "imminent_risk": imminent_risk,
            "decompensation_risk": decomp_risk
        },
        "ai_recommendation": recommendation,
        "ai_source": source
    }


@app.get("/history")
def get_history(limit: int = 20) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM cardiac_analysis_logs ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


async def query_ollama_ai(
    variance: float, is_anomaly: bool, drugs: List[str], comorbidities: List[str], selected_lead: str
) -> Dict[str, str]:
    prompt = f"""You are CardioMate Pediatric Cardiac AI.
Analyze patient status based on:
- Selected ECG Lead: {selected_lead}
- ECG Signal Variance: {variance:.4f}
- Active Drugs: {', '.join(drugs) if drugs else 'None'}
- Comorbidities: {', '.join(comorbidities) if comorbidities else 'None'}
- Anomaly Status: {is_anomaly}

Provide a short 1-sentence clinical decision and risk analysis for the doctor.
Return ONLY JSON with key:
{{"recommendation": "Your clinical recommendation here"}}
"""

    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL_NAME,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
            )
            if response.status_code == 200:
                result = response.json()
                ai_json = json.loads(result.get("response", "{}"))
                return {
                    "recommendation": str(ai_json.get("recommendation", "ECG pattern stable.")),
                    "source": "OLLAMA_LOCAL_MODEL",
                }
    except Exception:
        pass

    if is_anomaly:
        fallback_rec = f"CRITICAL: High hemodynamic risk observed on Lead {selected_lead}. Monitor for ischemia or dysrhythmia."
    else:
        fallback_rec = f"Lead {selected_lead} telemetry within normal baseline. Hemodynamics stable."

    return {
        "recommendation": fallback_rec,
        "source": "FASTAPI_HEURISTIC_FALLBACK",
    }

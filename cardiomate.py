import json
import random
import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any

import httpx
from fastapi import FastAPI, HTTPException, status
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="CardioMate Cardiac AI Predictor")

# CORS Configuration
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


# --- 1. SQL DATABASE INITIALIZATION ---
def init_db() -> None:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Analysis Logs Table
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS cardiac_analysis_logs
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       timestamp
                       TEXT
                       NOT
                       NULL,
                       risk_score
                       REAL
                       NOT
                       NULL,
                       status
                       TEXT
                       NOT
                       NULL,
                       signal_variance
                       REAL
                       NOT
                       NULL,
                       active_drugs
                       TEXT
                       NOT
                       NULL,
                       comorbidities
                       TEXT
                       NOT
                       NULL,
                       selected_lead
                       TEXT
                       NOT
                       NULL,
                       ai_recommendation
                       TEXT
                       NOT
                       NULL,
                       ai_source
                       TEXT
                       NOT
                       NULL
                   )
                   """)

    # Users Table for Landing & Sign-Up Authorization
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS users
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       username
                       TEXT
                       UNIQUE
                       NOT
                       NULL,
                       password
                       TEXT
                       NOT
                       NULL,
                       full_name
                       TEXT
                       NOT
                       NULL,
                       university
                       TEXT
                       NOT
                       NULL,
                       created_at
                       TEXT
                       NOT
                       NULL
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
            (timestamp, risk_score, status, signal_variance, active_drugs, comorbidities, selected_lead,
             ai_recommendation, ai_source)
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


# --- 2. DATA MODELS ---
class UserRegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str
    university: str


class UserLoginRequest(BaseModel):
    username: str
    password: str


class CardiacAnalysisRequest(BaseModel):
    ecg_signal: Optional[List[List[float]]] = None
    drugs: Optional[List[str]] = []
    drug_doses: Optional[Dict[str, float]] = None
    comorbidities: Optional[List[str]] = []
    selected_lead: Optional[str] = "II"


# --- 3. AUTHENTICATION & USER ENDPOINTS ---
@app.post("/register")
def register_user(payload: UserRegisterRequest) -> Dict[str, Any]:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        cursor.execute(
            "INSERT INTO users (username, password, full_name, university, created_at) VALUES (?, ?, ?, ?, ?)",
            (payload.username, payload.password, payload.full_name, payload.university, created_at)
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()

        return {
            "status": "success",
            "message": "Registration successful",
            "user": {
                "id": user_id,
                "username": payload.username,
                "full_name": payload.full_name,
                "university": payload.university
            }
        }
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )


@app.post("/login")
def login_user(payload: UserLoginRequest) -> Dict[str, Any]:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, username, full_name, university FROM users WHERE username = ? AND password = ?",
        (payload.username, payload.password)
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        user_data = dict(row)
        return {
            "status": "success",
            "message": "Login successful",
            "user": user_data
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )


# --- 4. PREDICTION & OLLAMA AI ENDPOINTS ---
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
    drug_doses = payload.drug_doses or {}
    comorbidities = payload.comorbidities or []
    selected_lead = payload.selected_lead or "II"

    # Physiological Baseline Vitals
    base_hr = 74
    base_sys, base_dia = 120, 80
    base_lvef = 58
    base_spo2 = 98

    # Clinical Alignments
    if "Hypertension / LVH Watch" in comorbidities or "Hypertension" in comorbidities:
        base_sys += 22
        base_dia += 12
        base_hr += 4
    if "Coronary Artery Disease" in comorbidities:
        base_lvef -= 6
        base_hr += 6
    if "Baseline Hypotension" in comorbidities:
        base_sys -= 28
        base_dia -= 18
        base_hr += 14  # Reflex tachycardia
    if "Congenital Defect Watch" in comorbidities:
        base_spo2 -= 4
        base_lvef -= 5

    # Check for Atrial Fibrillation Anomaly
    is_afib_anomaly = (
        signal_variance > 0.15
        or "ST-Segment Shift Analysis" in comorbidities
        or "ST-Shift Watch" in comorbidities
        or "Atrial Fibrillation" in comorbidities
    )

    # 1. Epinephrine: Inotrope & chronotrope (dose in mcg/min, typical 2-20)
    if "Epinephrine" in drugs:
        dose = float(drug_doses.get("Epinephrine", 5.0))
        base_hr += int(dose * 3.5)
        base_sys += int(dose * 3.0)
        base_dia += int(dose * 1.2)
        base_lvef += min(15, int(dose * 1.2))

    # 2. Milrinone: Inodilator (dose in mcg/kg/min, typical 0.25-0.75)
    if "Milrinone" in drugs:
        dose = float(drug_doses.get("Milrinone", 0.50))
        base_lvef += int(dose * 18.0)
        base_sys -= int(dose * 14.0)
        base_dia -= int(dose * 8.0)
        base_hr += int(dose * 10.0)

    # 3. Dopamine: MAP & inotropy (dose in mcg/kg/min, typical 5-20)
    if "Dopamine" in drugs:
        dose = float(drug_doses.get("Dopamine", 10.0))
        base_hr += int(dose * 1.2)
        base_sys += int(dose * 1.8)
        base_dia += int(dose * 0.9)

    # 4. Metoprolol: Beta-1 blocker (dose in mg IV, typical 2.5-10)
    if "Metoprolol" in drugs:
        dose = float(drug_doses.get("Metoprolol", 5.0))
        base_hr -= int(dose * 3.0)
        base_sys -= int(dose * 2.0)
        base_dia -= int(dose * 1.0)

    # 5. Amiodarone: Class III antiarrhythmic (dose in mg IV, typical 150-300 mg bolus)
    has_amiodarone = "Amiodarone" in drugs
    amio_dose = float(drug_doses.get("Amiodarone", 150.0)) if has_amiodarone else 0.0

    afib_chemically_converted = False

    if is_afib_anomaly:
        # Therapeutic chemical cardioversion / rate control with Amiodarone (>=150mg) or Metoprolol (>=5mg)
        if (has_amiodarone and amio_dose >= 150.0) or ("Metoprolol" in drugs and float(drug_doses.get("Metoprolol", 0.0)) >= 5.0):
            afib_chemically_converted = True
            is_anomaly = False
            base_hr = max(60, min(85, base_hr))  # Controlled ventricular response
            status_code = "RHYTHM_CONVERTED_STABLE"
            imminent_risk = round(random.uniform(0.12, 0.22), 2)
            decomp_risk = round(random.uniform(0.16, 0.30), 2)
        else:
            is_anomaly = True
            base_hr += 55  # Severe AFib Tachycardia
            base_sys += 14
            base_lvef -= 10
            status_code = "CRITICAL_AFIB"
            imminent_risk = round(random.uniform(0.72, 0.89), 2)
            decomp_risk = round(random.uniform(0.60, 0.78), 2)
    else:
        is_anomaly = False
        if has_amiodarone:
            base_hr -= int(amio_dose * 0.06)
        status_code = "STABLE"
        imminent_risk = round(random.uniform(0.08, 0.20), 2)
        decomp_risk = round(random.uniform(0.12, 0.28), 2)

    base_hr = max(42, min(210, base_hr))
    base_sys = max(60, min(220, base_sys))
    base_dia = max(35, min(140, base_dia))
    base_lvef = max(20, min(75, base_lvef))
    map_val = int(base_dia + (base_sys - base_dia) / 3)

    risk_score = imminent_risk

    # Build drug text for Ollama Prompt
    active_drug_descs = [f"{d} ({drug_doses.get(d, 'therapeutic')} dose)" for d in drugs]

    ollama_analysis = await query_ollama_ai(
        variance=signal_variance,
        is_anomaly=is_anomaly,
        drugs=active_drug_descs if active_drug_descs else drugs,
        comorbidities=comorbidities,
        selected_lead=selected_lead
    )

    recommendation = str(ollama_analysis.get("recommendation", ""))
    source = str(ollama_analysis.get("source", ""))

    if not recommendation:
        if is_anomaly:
            recommendation = f"CRITICAL: Atrial Fibrillation detected on Lead {selected_lead}. Rapid ventricular response. Administer Amiodarone 150mg IV bolus for rhythm conversion."
        elif afib_chemically_converted:
            recommendation = f"Lead {selected_lead}: Atrial Fibrillation successfully converted to sinus rhythm via Amiodarone ({int(amio_dose)} mg IV). Rate controlled (HR {base_hr} BPM)."
        else:
            recommendation = f"Lead {selected_lead} telemetry within normal baseline. Hemodynamics and cardiac output stable."

    log_to_sql(
        risk_score=risk_score,
        status=status_code,
        variance=signal_variance,
        drugs=drugs,
        comorbidities=comorbidities,
        selected_lead=selected_lead,
        recommendation=recommendation,
        source=source
    )

    return {
        "risk_score": risk_score,
        "status": status_code,
        "selected_lead": selected_lead,
        "signal_variance": round(signal_variance, 4),
        "active_drugs": drugs,
        "drug_doses": drug_doses,
        "afib_chemically_converted": afib_chemically_converted,
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

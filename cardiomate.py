import hashlib
import hmac
import json
import os
import random
import secrets
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

import httpx
from fastapi import FastAPI, HTTPException, Depends, Request, Response, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = os.getenv("DB_FILE", str(BASE_DIR / "data/cardiomate_history.db"))
Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "").rstrip("/")
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "llama3")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
app = FastAPI(title="CardioMate Educational Simulator")

def connect():
    conn = sqlite3.connect(DB_FILE, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, full_name TEXT NOT NULL,
            university TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS cardiac_analysis_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
            risk_score REAL NOT NULL, status TEXT NOT NULL, signal_variance REAL NOT NULL,
            active_drugs TEXT NOT NULL, comorbidities TEXT NOT NULL,
            selected_lead TEXT NOT NULL, ai_recommendation TEXT NOT NULL,
            ai_source TEXT NOT NULL, user_id INTEGER);
        """)
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(cardiac_analysis_logs)")}
        if "user_id" not in columns:
            conn.execute("ALTER TABLE cardiac_analysis_logs ADD COLUMN user_id INTEGER")
        if "selected_lead" not in columns:
            conn.execute("ALTER TABLE cardiac_analysis_logs ADD COLUMN selected_lead TEXT NOT NULL DEFAULT 'II'")

init_db()

def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000).hex()
    return f"pbkdf2_sha256$600000${salt}${digest}"

def verify_password(password, stored):
    try:
        scheme, rounds, salt, digest = stored.split("$")
        if scheme != "pbkdf2_sha256" or int(rounds) != 600000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds)).hex()
        return hmac.compare_digest(actual, digest)
    except (ValueError, TypeError):
        # Legacy plaintext passwords are intentionally not accepted online.
        return False

def public_user(row):
    return {key: row[key] for key in ("id", "username", "full_name", "university")}

def start_session(response, user_id):
    token = secrets.token_urlsafe(32)
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
        conn.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                     (hashlib.sha256(token.encode()).hexdigest(), user_id, time.time() + 86400))
    response.set_cookie("cardiomate_session", token, httponly=True,
                        secure=COOKIE_SECURE, samesite="strict", max_age=86400)

def require_user(request: Request):
    token = request.cookies.get("cardiomate_session", "")
    with connect() as conn:
        user = conn.execute("""SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id
            WHERE s.token_hash=? AND s.expires_at>?""",
            (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
    if user is None:
        raise HTTPException(401, "Please sign in again.")
    return public_user(user)

class UserRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=160)
    university: str = Field(min_length=1, max_length=200)

class UserLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)

class CardiacAnalysisRequest(BaseModel):
    ecg_signal: Optional[List[List[float]]] = None
    drugs: List[str] = Field(default_factory=list, max_length=20)
    drug_doses: Dict[str, float] = Field(default_factory=dict)
    comorbidities: List[str] = Field(default_factory=list, max_length=20)
    selected_lead: str = Field(default="II", max_length=8)

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(BASE_DIR / "index.html")

@app.get("/heart.glb", include_in_schema=False)
def heart_model():
    model = BASE_DIR / "heart.glb"
    if not model.is_file():
        raise HTTPException(404, "Optional heart.glb was not supplied.")
    return FileResponse(model, media_type="model/gltf-binary")

@app.get("/health")
def health():
    with connect() as conn:
        conn.execute("SELECT 1").fetchone()
    return {"status": "ok", "mode": "educational_simulation",
            "ollama_configured": bool(OLLAMA_BASE_URL)}

@app.post("/register")
def register_user(payload: UserRegisterRequest, response: Response):
    password_hash = hash_password(payload.password)
    try:
        with connect() as conn:
            result = conn.execute("""INSERT INTO users
                (username,password,full_name,university,created_at) VALUES (?,?,?,?,?)""",
                (payload.username, password_hash, payload.full_name, payload.university,
                 datetime.now().isoformat()))
            user = {"id": result.lastrowid, "username": payload.username,
                    "full_name": payload.full_name, "university": payload.university}
    except sqlite3.IntegrityError:
        raise HTTPException(400, "Username already registered")
    start_session(response, user["id"])
    return {"status": "success", "user": user}

@app.post("/login")
def login_user(payload: UserLoginRequest, response: Response):
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (payload.username,)).fetchone()
    if row is None or not verify_password(payload.password, row["password"]):
        raise HTTPException(401, "Invalid username or password")
    start_session(response, row["id"])
    return {"status": "success", "user": public_user(row)}

@app.get("/me")
def me(user=Depends(require_user)):
    return {"user": user}

@app.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("cardiomate_session", "")
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie("cardiomate_session", secure=COOKIE_SECURE, httponly=True, samesite="strict")
    return {"status": "success"}

def log_to_sql(risk_score, status, variance, drugs, comorbidities,
               selected_lead, recommendation, source, user_id):
    with connect() as conn:
        conn.execute("""INSERT INTO cardiac_analysis_logs
            (timestamp,risk_score,status,signal_variance,active_drugs,comorbidities,
             selected_lead,ai_recommendation,ai_source,user_id) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(), risk_score, status, variance, json.dumps(drugs),
             json.dumps(comorbidities), selected_lead, recommendation, source, user_id))

@app.post("/predict")
async def predict_risk(payload: CardiacAnalysisRequest, user=Depends(require_user)) -> Dict[str, Any]:
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
        source=source,
        user_id=user["id"]
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
def get_history(limit: int = Query(20, ge=1, le=100), user=Depends(require_user)):
    with connect() as conn:
        rows = conn.execute("SELECT * FROM cardiac_analysis_logs WHERE user_id=? ORDER BY id DESC LIMIT ?",
                            (user["id"], limit)).fetchall()
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
        if not OLLAMA_BASE_URL:
            raise RuntimeError("Ollama is not configured")
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
# CardioMate / Rythmix AI Study — deployment package

## What caused the connection failure

The original page called http://127.0.0.1:8000. On a deployed website, this
address refers to each visitor's computer. Uploading Python files to GitHub
Pages does not run them: Pages supports static sites, not a Python server.

This package serves index.html and the API from the SAME FastAPI service.
Do not double-click index.html or deploy it by itself to GitHub Pages.

## Deploy using GitHub and Render

1. Put the contents of this folder at the root of a GitHub repository.
   Do not upload the original database or the original password-containing seeder.
2. In Render, create a Blueprint linked to that repository. It reads render.yaml.
3. Review Render's displayed costs: this configuration requests a PAID Starter
   web service and a 1 GB persistent disk. It has not been deployed or purchased.
4. After deployment succeeds, open the HTTPS URL Render provides. Register a
   new account with a password of at least 10 characters. Existing uploaded
   accounts are not included.
5. Check /health: status should be "ok". Sign in and confirm the backend banner
   shows CONNECTED. With no Ollama configured, it also shows SIMULATION.

Equivalent manual Web Service settings:

| Setting | Value |
| --- | --- |
| Runtime | Python 3 |
| Build command | pip install -r requirements.txt |
| Start command | python -m uvicorn cardiomate:app --host 0.0.0.0 --port $PORT |
| Health check | /health |
| Persistent disk mount | /var/data |
| DB_FILE environment variable | /var/data/cardiomate_history.db |
| COOKIE_SECURE environment variable | true |

Use one service instance with this SQLite setup. A free Render web service can
run the demo with its default DB_FILE, but its filesystem is ephemeral: accounts
and history can disappear on restarts/redeploys. Do not treat that as durable storage.

## Local development

Use Python 3.12 or later and a virtual environment:

```bash
python -m pip install -r requirements.txt
```

macOS/Linux:

```bash
COOKIE_SECURE=false python -m uvicorn cardiomate:app --host 127.0.0.1 --port 8000
```

Windows PowerShell:

```powershell
$env:COOKIE_SECURE = "false"
python -m uvicorn cardiomate:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 in your browser. The database initializes automatically.
Keep COOKIE_SECURE=true on the HTTPS deployment.

## Optional Ollama

Without OLLAMA_BASE_URL, the backend uses its existing heuristic fallback,
without trying a localhost Ollama service. To enable Ollama, set
OLLAMA_BASE_URL to an endpoint reachable by the SERVER, and optionally set
OLLAMA_MODEL_NAME (default llama3). The model must already be installed there.
Your laptop's 127.0.0.1 is not reachable from Render. This package does not host
Ollama. Use a protected service connection; do not expose an unsecured Ollama port.

## Scope and remaining limitations

- Frontend design and simulation rules are retained; no clinical validation is implied.
- Risk values are randomly sampled and vitals use simplified rules. They are not
  clinically validated predictions. Existing rhythm and drug logic has not been
  medically corrected. Use simulated data only, never diagnosis or treatment.
- Passwords are hashed with salted PBKDF2. Sign-in uses an HttpOnly session cookie;
  prediction and history require a session, and history is scoped to its owner.
- No patient-ready security review, account recovery, email verification, or
  login rate limiting has been implemented. This is an educational demo deployment.
- The uploaded database and embedded preset credentials were intentionally omitted.
  Rotate any real or reused passwords contained in the original files, especially
  if those files were committed to a public repository. Deleting a file alone
  does not remove it from Git history.
- heart.glb was not provided. The original external model fallback remains;
  its availability has not been verified. You can add your own authorized heart.glb
  beside index.html. External CSS, icons and Three.js also require network access.
- Automated backend tests and JavaScript syntax checks are provided/performed;
  the full browser layout and a live hosting deployment are not verified here.

## Tests

```bash
python -m pip install pytest
python -m pytest -q
```

## Hosting documentation

- https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site
- https://render.com/docs/deploy-fastapi
- https://render.com/docs/disks

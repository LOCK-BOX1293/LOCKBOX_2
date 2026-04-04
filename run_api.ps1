Write-Host "Starting Hackbite 2 Retrieval API..." -ForegroundColor Cyan
& .\venv\Scripts\python.exe -m uvicorn src.api.routes:app --reload --host 0.0.0.0 --port 8000

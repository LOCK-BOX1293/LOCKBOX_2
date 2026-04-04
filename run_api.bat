@echo off
echo Starting Hackbite 2 Retrieval API...
call .\venv\Scripts\activate.bat
uvicorn src.api.routes:app --reload --host 0.0.0.0 --port 8000
pause

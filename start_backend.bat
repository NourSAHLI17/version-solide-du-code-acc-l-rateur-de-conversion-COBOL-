@echo off
cd cobol-modernization-service
python -m uvicorn app.main:app --port 8010 --timeout-keep-alive 600
pause

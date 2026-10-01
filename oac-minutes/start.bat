@echo off
REM Double-click to start OAC Minutes (Windows). First run installs what it needs.
cd /d "%~dp0"
if not exist .venv (
  echo First run: setting up, about a minute...
  py -3 -m venv .venv 2>nul || python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
echo Starting OAC Minutes. Keep this window open while you use the app; close it to stop.
streamlit run app.py --browser.gatherUsageStats false
pause

#!/bin/bash
# Double-click to start OAC Minutes (macOS). First run installs what it needs.
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Get it from https://www.python.org/downloads/ and run this again."
  read -r -p "Press Enter to close."; exit 1
fi
if [ ! -d .venv ]; then
  echo "First run: setting up (about a minute)..."
  python3 -m venv .venv || { read -r -p "Could not create the environment. Press Enter to close."; exit 1; }
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt || { read -r -p "Install failed. Press Enter to close."; exit 1; }
echo "Starting OAC Minutes. Keep this window open while you use the app; close it to stop."
exec streamlit run app.py --browser.gatherUsageStats false

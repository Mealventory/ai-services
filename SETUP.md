# AI Service Setup (Python 3.11.9)

## 1) Install Python 3.11.9

- Official download page: https://www.python.org/downloads/release/python-3119/
- Download: Windows installer (64-bit)
- During installation, enable:
	- Add python.exe to PATH
	- Install launcher for all users (py launcher)

## 2) Verify Python on your machine

Run these commands from a new terminal:

py -3.11 --version
py -0p

Expected: Python 3.11.9 is listed.

## 3) Create and activate virtual environment

From project root (Capstone):

cd ai-services
py -3.11 -m venv .venv

PowerShell:

.\.venv\Scripts\Activate.ps1

CMD:

.\.venv\Scripts\activate.bat

## 4) Install dependencies

python -m pip install --upgrade pip
pip install -r requirements.txt

## 5) Configure environment files and credentials

Copy .env.example to .env.

If credentials folder does not exist at project root, create it.

To create google-vision.json:

- Ensure 2FA is enabled for the Google account you will use.
- Open: https://console.cloud.google.com/
- Select project: mealventory-ai
- Go to IAM & Admin > Service Accounts
- Select service account: mealventory-ai-service
- Open Keys
- Click Add Key > Create New Key
- Choose JSON and create
- Place the file under credentials
- Rename it to google-vision.json

## 6) Run the AI service

uvicorn main:app --reload --host 0.0.0.0 --port 8001

Service URL:

http://127.0.0.1:8001

## 7) If py command is not found

Reopen terminal, then try:

C:\Users\<your-user>\AppData\Local\Programs\Python\Python311\python.exe --version

If that works, reinstall Python 3.11.9 and ensure PATH + py launcher were selected.
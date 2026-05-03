# MEDINSPECTAI

To visualize your stored data — use our scripts:

What to checkScriptRules in blob               python check_storage.py
Rules in AI Search                             python check_search.py
Recover to local filespython                   recover_from_search.py
Local JSON files             Open              backend/rules/*.json in VS Code

Your PDF = outer carton only 📦

Full submission pack = 
  📦 Outer carton    → 31 PASS, 5 FAIL checked ✅
  💊 Blister foil    → 9 CANNOT_DETERMINE
  📄 Package leaflet → 12 CANNOT_DETERMINE
  📋 SmPC document   → 4 CANNOT_DETERMINE


  cd C:\Users\m685857\Downloads\MedInspectAI(1)\MEDINSPECTAI\backend
.venv\Scripts\activate
uvicorn main:app --reload --timeout-keep-alive 300

cd C:\Users\m685857\Downloads\MedInspectAI(1)\MEDINSPECTAI
python -m http.server 3000 --directory frontend

local host
http://localhost:3000

Token limit = max amount of text (input + output) GPT can handle in one go

if you increase CHUNK_SIZE, you’ll have fewer GPT calls

C:\Users\m685910\AppData\Local\Programs\Python\Python312\python.exe -m pip install apscheduler
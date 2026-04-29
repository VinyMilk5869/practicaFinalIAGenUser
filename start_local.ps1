$python = "C:\Users\Santy\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

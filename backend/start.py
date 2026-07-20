import sys
import traceback

try:
    import uvicorn
    import api
    print("API imported, starting server on 8000...")
    uvicorn.run(api.app, host="127.0.0.1", port=8000)
except Exception as e:
    with open("crash_log.txt", "w") as f:
        traceback.print_exc(file=f)
    print(f"Failed: {e}")

import time
import requests

BASE = "http://localhost:8000"

def post(path: str):
    r = requests.post(BASE + path, timeout=60)
    r.raise_for_status()
    return r.json()

def get(path: str):
    r = requests.get(BASE + path, timeout=60)
    r.raise_for_status()
    return r.json()

def main():
    print("1) Reloading graph...")
    print(post("/reload-graph"))

    print("\n2) Running scoring...")
    print(post("/run-score"))

    print("\n3) Top risk wallets (limit=10)...")
    top = get("/scores/top?limit=10")
    for row in top:
        print(row)

    print("\n4) Ingestion status...")
    print(get("/ingestion/status"))

    print("\n✅ Demo complete.")

if __name__ == "__main__":
    main()

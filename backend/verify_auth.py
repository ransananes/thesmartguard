import requests
import sys

BASE_URL = "http://localhost:5000/api"

def test_login():
    print("Testing Login...")
    # Using the root user we know exists from seed_db
    try:
        response = requests.post(f"{BASE_URL}/login", json={
            "username": "root",
            "password": "root"
        })
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and "token" in data:
                print("[OK] Login Successful")
                return data["token"]
            else:
                print("[FAIL] Login Failed: Missing success or token")
        else:
            print(f"[FAIL] Login Failed: Status {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"[ERR] Connection Error: {e}")
    return None

def test_protected_route(token):
    print("\nTesting Protected Route (/cameras)...")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/cameras", headers=headers)
        
        if response.status_code == 200:
            print("[OK] Protected Route Access Successful")
            print(f"   Data: {str(response.json())[:100]}...")
        else:
            print(f"[FAIL] Protected Route Failed: Status {response.status_code}")
    except Exception as e:
        print(f"[ERR] Connection Error: {e}")

if __name__ == "__main__":
    token = test_login()
    if token:
        test_protected_route(token)
    else:
        sys.exit(1)

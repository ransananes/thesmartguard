import requests
import sys

BASE_URL = "http://localhost:5000/api"

def test_verify():
    print("Testing /verify endpoint...")
    try:
        login_res = requests.post(f"{BASE_URL}/login", json={
            "username": "root",
            "password": "root"
        })
        
        if login_res.status_code != 200:
            print(f"[FAIL] Login failed: {login_res.status_code}")
            return

        token = login_res.json().get("token")
        if not token:
            print("[FAIL] No token received")
            return

        headers = {"Authorization": f"Bearer {token}"}
        verify_res = requests.get(f"{BASE_URL}/verify", headers=headers)
        
        if verify_res.status_code == 200:
            print("[OK] Valid token verification successful")
        else:
            print(f"[FAIL] Valid token verification failed: {verify_res.status_code}")
            print(verify_res.text)

        headers_inv = {"Authorization": "Bearer invalid-token"}
        verify_inv_res = requests.get(f"{BASE_URL}/verify", headers=headers_inv)
        
        if verify_inv_res.status_code == 422 or verify_inv_res.status_code == 401:
            print("[OK] Invalid token correctly rejected")
        else:
             print(f"[FAIL] Invalid token NOT rejected (Status: {verify_inv_res.status_code})")

    except Exception as e:
        print(f"[ERR] Connection Error: {e}")

if __name__ == "__main__":
    test_verify()

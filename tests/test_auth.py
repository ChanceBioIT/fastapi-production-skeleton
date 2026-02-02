"""
Quick script to test auth flow.
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_auth_flow():
    """Test full auth flow (register, login, protected endpoint)."""
    
    print("=" * 50)
    print("1. Register tenant and admin")
    print("=" * 50)
    
    register_data = {
        "username": "test_admin",
        "password": "test123456",
        "tenant_name": "Test Org"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json=register_data
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        if response.status_code != 200:
            print("Registration failed (user may exist), continuing to login...")
    except Exception as e:
        print(f"Register request failed: {e}")
        print("Continuing to login (assuming user exists)...")
    
    print("\n" + "=" * 50)
    print("2. Login to get Token")
    print("=" * 50)
    
    login_data = {
        "username": "test_admin",
        "password": "test123456"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            json=login_data
        )
        print(f"Status: {response.status_code}")
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
        if response.status_code == 200 and result.get("code") == 200:
            token = result["data"]["access_token"]
            print(f"\nToken obtained: {token[:50]}...")
            
            print("\n" + "=" * 50)
            print("3. Access protected endpoint with Token")
            print("=" * 50)
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            task_data = {
                "task_type": "seq_toolkit",
                "params": {
                    "sequence": "ATCG",
                    "operation": "gc_content"
                },
                "is_sync": True
            }
            
            response = requests.post(
                f"{BASE_URL}/api/v1/tasks/submit",
                headers=headers,
                json=task_data
            )
            
            print(f"Status: {response.status_code}")
            print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
            
            if response.status_code == 200:
                print("\nAuth OK. Protected endpoint accessible.")
            else:
                print("\nAuth failed. Check token is passed correctly.")
        else:
            print("\nLogin failed. Check username and password.")
            
    except Exception as e:
        print(f"\nRequest failed: {e}")

if __name__ == "__main__":
    test_auth_flow()


import requests
import json

BASE_URL = "http://localhost:8000"

print("=== Testing Insurance AI API ===\n")

# Test 1: Health
print("1. Health Check:")
resp = requests.get(f"{BASE_URL}/health")
print(f"   Status: {resp.status_code}")
print(f"   Response: {resp.json()}\n")

# Test 2: Registration
print("2. User Registration:")
resp = requests.post(
    f"{BASE_URL}/auth/register",
    json={"email": "testuser123@example.com", "password": "test"}
)
print(f"   Status: {resp.status_code}")
data = resp.json()
print(f"   Response: {json.dumps(data, indent=2)[:300]}")

if "access_token" in data:
    token = data["access_token"]
    print(f"   Token: {token[:50]}...\n")
    
    # Test 3: Get current user
    print("3. Get Current User:")
    resp = requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"   Status: {resp.status_code}")
    print(f"   Response: {resp.json()}\n")
    
    # Test 4: List workspaces
    print("4. List Workspaces:")
    resp = requests.get(
        f"{BASE_URL}/workspaces",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"   Status: {resp.status_code}")
    print(f"   Response: {resp.json()}\n")
    
    # Test 5: Create workspace
    print("5. Create Workspace:")
    resp = requests.post(
        f"{BASE_URL}/workspaces",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "My Insurance Workspace", "description": "Test workspace"}
    )
    print(f"   Status: {resp.status_code}")
    workspace_data = resp.json()
    workspace_id = workspace_data.get("id")
    print(f"   Response: {json.dumps(workspace_data, indent=2)}\n")
    
    # Test 6: Search (empty)
    print("6. Search Knowledge:")
    resp = requests.post(
        f"{BASE_URL}/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "insurance", "workspace_id": workspace_id}
    )
    print(f"   Status: {resp.status_code}")
    print(f"   Response: {json.dumps(resp.json(), indent=2)[:500]}\n")
    
    # Test 7: Chat
    print("7. Chat:")
    resp = requests.post(
        f"{BASE_URL}/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"workspace_id": workspace_id, "message": "Hello, what is term life insurance?"}
    )
    print(f"   Status: {resp.status_code}")
    print(f"   Response: {json.dumps(resp.json(), indent=2)}\n")

print("=== All Tests Complete ===")
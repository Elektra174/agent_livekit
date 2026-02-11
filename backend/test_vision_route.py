
from server import app

with app.test_client() as client:
    print("Testing / route:")
    response = client.get('/')
    print(f"Status: {response.status_code}")
    print(f"Body snippet: {response.data.decode('utf-8')[:50]}...")
    print()
    
    print("Testing /voice-settings route:")
    response = client.get('/voice-settings')
    print(f"Status: {response.status_code}")
    print(f"Body snippet: {response.data.decode('utf-8')[:50]}...")
    print()
    
    print("Testing /vision-mode route:")
    response = client.get('/vision-mode')
    print(f"Status: {response.status_code}")
    print(f"Body snippet: {response.data.decode('utf-8')[:50]}...")
    print()
    
    print("Testing /health route:")
    response = client.get('/health')
    print(f"Status: {response.status_code}")
    print(f"Body: {response.data.decode('utf-8')}")

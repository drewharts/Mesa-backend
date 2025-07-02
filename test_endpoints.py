#!/usr/bin/env python3
"""Test the URL processing endpoints locally."""

import os
import sys
import time
import requests
import subprocess
import signal

def start_flask_app():
    """Start Flask app and return the process."""
    print("Starting Flask app...")
    env = os.environ.copy()
    process = subprocess.Popen(
        [sys.executable, "app.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for app to start
    time.sleep(3)
    
    # Check if app started
    try:
        response = requests.get("http://localhost:5002/health", timeout=2)
        if response.status_code == 200:
            print("✓ Flask app started successfully")
            return process
    except:
        pass
    
    # If not started, check logs
    stdout, stderr = process.communicate(timeout=1)
    print("Failed to start Flask app:")
    print("STDOUT:", stdout.decode())
    print("STDERR:", stderr.decode())
    return None

def test_endpoints():
    """Test the new endpoints."""
    base_url = "http://localhost:5002"
    
    # Test 1: Get supported platforms
    print("\n1. Testing GET /process-url/platforms")
    try:
        response = requests.get(f"{base_url}/process-url/platforms")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print(f"Response: {response.json()}")
            print("✓ Platforms endpoint working")
        else:
            print(f"✗ Error: {response.text}")
    except Exception as e:
        print(f"✗ Request failed: {e}")
    
    # Test 2: Process TikTok URL
    print("\n2. Testing POST /process-url with TikTok URL")
    try:
        payload = {"url": "https://www.tiktok.com/@test/video/123456789"}
        response = requests.post(
            f"{base_url}/process-url",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Processor type: {data.get('processor_type')}")
            print(f"Location info: {data.get('location_info')}")
            print("✓ URL processing endpoint working")
        else:
            print(f"✗ Error: {response.text}")
    except Exception as e:
        print(f"✗ Request failed: {e}")
    
    # Test 3: Invalid URL
    print("\n3. Testing POST /process-url with invalid URL")
    try:
        payload = {"url": "not-a-url"}
        response = requests.post(
            f"{base_url}/process-url",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 400:
            print(f"Response: {response.json()}")
            print("✓ Correctly rejected invalid URL")
        else:
            print(f"✗ Unexpected response: {response.text}")
    except Exception as e:
        print(f"✗ Request failed: {e}")

if __name__ == "__main__":
    # Start Flask app
    flask_process = start_flask_app()
    
    if flask_process:
        try:
            # Run tests
            test_endpoints()
        finally:
            # Clean up
            print("\nStopping Flask app...")
            flask_process.terminate()
            flask_process.wait(timeout=5)
            print("Done.")
    else:
        print("Failed to start Flask app")
        sys.exit(1)
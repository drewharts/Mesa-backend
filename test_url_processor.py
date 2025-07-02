#!/usr/bin/env python3
"""Test script for the URL processing endpoint."""

import requests
import json
import sys

# Base URL - adjust if running on different port
BASE_URL = "http://localhost:5002"

def test_supported_platforms():
    """Test getting supported platforms."""
    print("\n1. Testing supported platforms endpoint...")
    response = requests.get(f"{BASE_URL}/process-url/platforms")
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Supported platforms: {data['supported_platforms']}")
    else:
        print(f"✗ Error: {response.status_code} - {response.text}")

def test_tiktok_url(url):
    """Test processing a TikTok URL."""
    print(f"\n2. Testing TikTok URL processing...")
    print(f"   URL: {url}")
    
    payload = {"url": url}
    response = requests.post(
        f"{BASE_URL}/process-url",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Processor type: {data.get('processor_type')}")
        print(f"✓ Video data: {json.dumps(data.get('data', {}), indent=2)}")
        
        location_info = data.get('location_info')
        if location_info:
            print(f"✓ Location found:")
            print(f"  - Name: {location_info.get('location_name')}")
            print(f"  - Coordinates: {location_info.get('coordinates')}")
            print(f"  - Address: {location_info.get('formatted_address')}")
            print(f"  - Place ID: {location_info.get('place_id')}")
        else:
            print("✗ No location information extracted")
    else:
        print(f"✗ Error: {response.status_code} - {response.text}")

def test_invalid_url():
    """Test with invalid URL."""
    print("\n3. Testing invalid URL...")
    payload = {"url": "not-a-valid-url"}
    response = requests.post(
        f"{BASE_URL}/process-url",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code == 400:
        print(f"✓ Correctly rejected invalid URL: {response.json().get('error')}")
    else:
        print(f"✗ Unexpected response: {response.status_code} - {response.text}")

def test_unsupported_platform():
    """Test with unsupported platform URL."""
    print("\n4. Testing unsupported platform...")
    payload = {"url": "https://www.example.com/video/123"}
    response = requests.post(
        f"{BASE_URL}/process-url",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code == 400:
        print(f"✓ Correctly rejected unsupported platform: {response.json().get('error')}")
    else:
        print(f"✗ Unexpected response: {response.status_code} - {response.text}")

def test_missing_url():
    """Test with missing URL in request."""
    print("\n5. Testing missing URL in request...")
    payload = {}
    response = requests.post(
        f"{BASE_URL}/process-url",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code == 400:
        print(f"✓ Correctly rejected missing URL: {response.json().get('error')}")
    else:
        print(f"✗ Unexpected response: {response.status_code} - {response.text}")

if __name__ == "__main__":
    print("=== URL Processor Endpoint Tests ===")
    
    # Test all endpoints
    test_supported_platforms()
    test_missing_url()
    test_invalid_url()
    test_unsupported_platform()
    
    # Test with sample TikTok URLs
    sample_urls = [
        "https://www.tiktok.com/@user/video/123456789",
        "https://www.tiktok.com/t/ABC123",
        "https://vm.tiktok.com/ZM8abcdef/"
    ]
    
    for url in sample_urls:
        test_tiktok_url(url)
    
    print("\n=== Tests completed ===")
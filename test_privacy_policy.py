#!/usr/bin/env python3
"""Test the privacy policy endpoint."""

import requests
import subprocess
import sys
import time
import signal

def test_privacy_policy():
    """Test the privacy policy endpoint."""
    print("Testing privacy policy endpoint...")
    
    # Start Flask app
    process = subprocess.Popen(
        [sys.executable, "app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/Users/drewhartsfield/Desktop/mesa-backend-clean"
    )
    
    try:
        # Wait for app to start
        time.sleep(3)
        
        # Test the endpoint
        response = requests.get("http://localhost:5002/privacy-policy")
        
        print(f"Status Code: {response.status_code}")
        print(f"Content Type: {response.headers.get('Content-Type')}")
        print(f"Content Length: {len(response.text)} characters")
        
        # Check if it contains required sections
        content = response.text
        required_sections = [
            "Privacy Policy",
            "Information We Collect", 
            "TikTok Integration",
            "Contact Information",
            "Data Security"
        ]
        
        print("\nChecking required sections:")
        for section in required_sections:
            if section in content:
                print(f"✓ {section}")
            else:
                print(f"✗ {section}")
        
        # Check if it's valid HTML
        if "<!DOCTYPE html>" in content and "</html>" in content:
            print("✓ Valid HTML structure")
        else:
            print("✗ Invalid HTML structure")
            
        print(f"\nPrivacy Policy URL: http://localhost:5002/privacy-policy")
        
    finally:
        # Clean up
        process.terminate()
        process.wait(timeout=5)

if __name__ == "__main__":
    test_privacy_policy()
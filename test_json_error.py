#!/usr/bin/env python3
"""Test JSON parsing with control characters."""

import requests
import json

# Test data with control character (tab character in URL)
test_cases = [
    {
        "name": "Normal URL",
        "data": {"url": "https://www.tiktok.com/t/ZP8hJe4ym/"}
    },
    {
        "name": "URL with tab character",
        "data": {"url": "https://www.tiktok.com/t/ZP8\thJe4ym/"}
    },
    {
        "name": "URL with newline",
        "data": {"url": "https://www.tiktok.com/t/ZP8\nhJe4ym/"}
    }
]

print("Testing JSON parsing with various inputs...")

for test in test_cases:
    print(f"\nTest: {test['name']}")
    print(f"Data: {repr(test['data'])}")
    
    try:
        # Try to serialize to JSON
        json_str = json.dumps(test['data'])
        print(f"✓ JSON serialization successful")
        
        # Try to parse it back
        parsed = json.loads(json_str)
        print(f"✓ JSON parsing successful")
        
    except json.JSONDecodeError as e:
        print(f"✗ JSON error: {e}")
    except Exception as e:
        print(f"✗ Error: {e}")

# Test the actual endpoint would receive
print("\n\nSimulating request with control character:")
url_with_tab = "https://www.tiktok.com/t/ZP8\thJe4ym/"
print(f"URL: {repr(url_with_tab)}")

# The issue is likely that the frontend is sending the URL with actual control characters
# Let's test how to handle this
import re
cleaned_url = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', url_with_tab)
print(f"Cleaned URL: {repr(cleaned_url)}")
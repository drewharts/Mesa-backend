#!/usr/bin/env python3
"""Test TikTok API integration."""

import os
from url_processors.tiktok_processor import TikTokProcessor
import json

def test_tiktok_api():
    """Test the TikTok API integration."""
    processor = TikTokProcessor()
    
    # Test URL
    test_url = "https://www.tiktok.com/t/ZP8hJe4ym/"
    
    print("Testing TikTok API integration...")
    print(f"URL: {test_url}")
    print(f"Has API credentials: {bool(processor.access_token)}")
    
    try:
        # Extract data
        data = processor.extract_data(test_url)
        
        print("\n=== Extracted Data ===")
        print(json.dumps(data, indent=2, default=str))
        
        # Extract location info
        location_info = processor.extract_location_info(data)
        
        print("\n=== Location Info ===")
        if location_info:
            print(json.dumps(location_info, indent=2))
        else:
            print("No location information found")
            
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Show which API approach will be used
    has_token = bool(os.environ.get('TIKTOK_ACCESS_TOKEN'))
    print(f"TIKTOK_ACCESS_TOKEN configured: {has_token}")
    print("Will use: " + ("Official API" if has_token else "oEmbed API (public, limited data)"))
    print()
    
    test_tiktok_api()
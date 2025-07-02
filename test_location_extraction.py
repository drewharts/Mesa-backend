#!/usr/bin/env python3
"""Test location extraction from TikTok data."""

from url_processors.tiktok_processor import TikTokProcessor
import json

def test_location_extraction():
    """Test the location extraction logic with sample data."""
    processor = TikTokProcessor()
    
    # Test cases with different caption formats
    test_cases = [
        {
            "name": "Pin emoji location",
            "data": {
                "caption": "Amazing sunset views! 📍 Central Park, New York #travel #nyc",
                "location": None
            }
        },
        {
            "name": "At/In location",
            "data": {
                "caption": "Having lunch at Times Square today! #foodie #manhattan",
                "location": None
            }
        },
        {
            "name": "Direct location data",
            "data": {
                "caption": "Great day out!",
                "location": {
                    "name": "Brooklyn Bridge",
                    "latitude": 40.7061,
                    "longitude": -73.9969,
                    "address": "Brooklyn Bridge, New York, NY 10038"
                }
            }
        },
        {
            "name": "Location hashtag",
            "data": {
                "caption": "Exploring the city #newyorkcity #travel #fun",
                "location": None
            }
        },
        {
            "name": "No location",
            "data": {
                "caption": "Just dancing! #fyp #dance",
                "location": None
            }
        }
    ]
    
    print("Testing TikTok location extraction...\n")
    
    for test in test_cases:
        print(f"Test: {test['name']}")
        print(f"Caption: {test['data']['caption']}")
        
        location_info = processor.extract_location_info(test['data'])
        
        if location_info:
            print("✓ Location extracted:")
            print(f"  - Name: {location_info.get('location_name')}")
            print(f"  - Coordinates: {location_info.get('coordinates')}")
            print(f"  - Address: {location_info.get('address')}")
        else:
            print("✗ No location found")
        print()

if __name__ == "__main__":
    test_location_extraction()
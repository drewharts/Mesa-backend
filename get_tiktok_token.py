#!/usr/bin/env python3
"""
Script to get TikTok API access token using client credentials.
This implements the OAuth 2.0 client credentials flow for TikTok API.
"""

import requests
import os
import json
from urllib.parse import quote

# Your TikTok API credentials
CLIENT_KEY = "sbawkfvjp24kdv3yvb"
CLIENT_SECRET = "CWDskYOYbESB3zkUr5gFUPtPysPdFrxW"

def get_client_access_token():
    """Get access token using client credentials flow."""
    
    # TikTok OAuth 2.0 token endpoint
    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    
    # Prepare the request
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cache-Control": "no-cache"
    }
    
    data = {
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    
    try:
        print("Requesting TikTok API access token...")
        print(f"Client Key: {CLIENT_KEY}")
        print(f"Endpoint: {token_url}")
        
        response = requests.post(token_url, headers=headers, data=data)
        
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            token_data = response.json()
            print("\n✅ SUCCESS! Token retrieved:")
            print(json.dumps(token_data, indent=2))
            
            access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in")
            
            if access_token:
                print(f"\n🔑 Access Token: {access_token}")
                print(f"⏰ Expires in: {expires_in} seconds")
                
                # Save to .env file
                env_line = f"TIKTOK_ACCESS_TOKEN={access_token}"
                print(f"\n📝 Add this to your .env file:")
                print(f"TIKTOK_CLIENT_KEY={CLIENT_KEY}")
                print(f"TIKTOK_CLIENT_SECRET={CLIENT_SECRET}")
                print(f"{env_line}")
                
                return access_token
            else:
                print("❌ No access_token in response")
                
        else:
            print(f"\n❌ Error: {response.status_code}")
            print(f"Response: {response.text}")
            
            # Check for common error responses
            try:
                error_data = response.json()
                error_code = error_data.get("error")
                error_description = error_data.get("error_description")
                
                if error_code:
                    print(f"Error Code: {error_code}")
                    print(f"Error Description: {error_description}")
                    
                    if error_code == "invalid_client":
                        print("\n💡 Suggestions:")
                        print("- Verify your client_key and client_secret are correct")
                        print("- Ensure your app is approved for API access")
                        print("- Check if you need to apply for specific scopes")
                        
            except:
                pass
                
    except Exception as e:
        print(f"❌ Request failed: {str(e)}")
        
    return None

def test_token_with_api(access_token):
    """Test the access token with a simple API call."""
    if not access_token:
        return
        
    print(f"\n🧪 Testing token with TikTok API...")
    
    # Try to call a simple API endpoint to verify the token works
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # Note: This endpoint might not exist or might require different scopes
    # This is just to test if the token is valid
    test_url = "https://open.tiktokapis.com/v2/user/info/"
    
    try:
        response = requests.get(test_url, headers=headers)
        print(f"Test API Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Token appears to be valid!")
        else:
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"Test failed: {str(e)}")

if __name__ == "__main__":
    print("TikTok API Token Generator")
    print("=" * 30)
    
    # Get the access token
    token = get_client_access_token()
    
    # Test the token
    if token:
        test_token_with_api(token)
    
    print(f"\n📚 Next steps:")
    print("1. Add the environment variables to your .env file")
    print("2. Restart your Flask application")
    print("3. Test the /process-url endpoint with a TikTok URL")
    print("4. Check the logs to see if the official API is being used")
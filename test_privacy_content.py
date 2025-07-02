#!/usr/bin/env python3
"""Test privacy policy content generation."""

import time

def generate_privacy_policy():
    """Generate the privacy policy HTML content."""
    privacy_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Privacy Policy - Mesa Location Services</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                color: #333;
            }
            h1, h2 { color: #2c3e50; }
            .last-updated { color: #666; font-style: italic; }
            .section { margin-bottom: 2em; }
        </style>
    </head>
    <body>
        <h1>Privacy Policy</h1>
        <p class="last-updated">Last updated: """ + time.strftime("%B %d, %Y") + """</p>
        
        <div class="section">
            <h2>1. Information We Collect</h2>
            <p>Mesa Location Services ("we," "our," or "us") is a location-based content discovery service. We collect the following information:</p>
            <ul>
                <li><strong>URL Data:</strong> Social media URLs you submit for location extraction</li>
                <li><strong>Location Information:</strong> Geographic data extracted from social media content</li>
                <li><strong>Usage Data:</strong> API usage statistics and error logs for service improvement</li>
            </ul>
        </div>

        <div class="section">
            <h2>10. Platform-Specific Information</h2>
            <h3>TikTok Integration</h3>
            <p>When processing TikTok URLs, we:</p>
            <ul>
                <li>Access only publicly available video metadata</li>
                <li>Extract location information from video captions and metadata</li>
                <li>Do not access private account information</li>
                <li>Comply with TikTok's API terms of service</li>
            </ul>
        </div>

        <div class="section">
            <h2>9. Contact Information</h2>
            <p>If you have questions about this privacy policy or our data practices, please contact us at:</p>
            <p>
                <strong>Email:</strong> privacy@mesa-location-services.com<br>
                <strong>Service:</strong> Mesa Location Services API<br>
                <strong>Last Updated:</strong> """ + time.strftime("%B %d, %Y") + """
            </p>
        </div>
    </body>
    </html>
    """
    return privacy_content

def test_privacy_policy():
    """Test the privacy policy content."""
    print("Testing privacy policy content generation...")
    
    content = generate_privacy_policy()
    
    print(f"✓ Content generated: {len(content)} characters")
    
    # Check required sections
    required_sections = [
        "Privacy Policy",
        "Information We Collect", 
        "TikTok Integration",
        "Contact Information",
        "privacy@mesa-location-services.com"
    ]
    
    print("\nChecking required sections:")
    for section in required_sections:
        if section in content:
            print(f"✓ {section}")
        else:
            print(f"✗ {section}")
    
    # Check HTML structure
    if "<!DOCTYPE html>" in content and "</html>" in content:
        print("✓ Valid HTML structure")
    else:
        print("✗ Invalid HTML structure")
    
    # Show current date
    print(f"\nLast updated date: {time.strftime('%B %d, %Y')}")
    
    print("\n" + "="*50)
    print("PRIVACY POLICY URL FOR TIKTOK API:")
    print("https://your-domain.com/privacy-policy")
    print("(Replace with your actual domain)")
    print("="*50)

if __name__ == "__main__":
    test_privacy_policy()
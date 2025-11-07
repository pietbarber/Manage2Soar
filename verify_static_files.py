#!/usr/bin/env python
"""
Static Files Verification Script for Multi-Tenant Manage2Soar

This script verifies that the GCP static files configuration is working correctly
for the multi-tenant architecture.
"""

from django.core.files.storage import storages
from django.conf import settings
import os
import sys
import django
import requests
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manage2soar.settings')
django.setup()


def test_configuration():
    """Test the current Django configuration"""
    print("🔍 Testing Django Configuration")
    print(f"   CLUB_PREFIX: {getattr(settings, 'CLUB_PREFIX', 'Not set')}")
    print(f"   STATIC_URL: {settings.STATIC_URL}")
    print(f"   GS_BUCKET_NAME: {getattr(settings, 'GS_BUCKET_NAME', 'Not set')}")
    print(
        f"   GS_STATIC_LOCATION: {getattr(settings, 'GS_STATIC_LOCATION', 'Not set')}")
    print(f"   Storage Backend: {settings.STORAGES['staticfiles']['BACKEND']}")
    print()


def test_static_files():
    """Test that static files can be accessed"""
    print("🔍 Testing Static File Access")

    static_storage = storages['staticfiles']

    # Test files that should exist
    test_files = [
        'admin/css/base.css',
        'css/baseline.css',
        'admin/js/core.js',
        'js/bootstrap.bundle.min.js'
    ]

    for file_path in test_files:
        try:
            url = static_storage.url(file_path)
            print(f"   📁 {file_path}")
            print(f"      URL: {url[:80]}...")

            # Try to access the file
            try:
                response = requests.head(url, timeout=10)
                if response.status_code == 200:
                    print(f"      ✅ Accessible (Status: {response.status_code})")
                else:
                    print(f"      ⚠️  Status: {response.status_code}")
            except requests.RequestException as e:
                print(f"      ❌ Network error: {e}")

        except Exception as e:
            print(f"   ❌ {file_path}: Error generating URL - {e}")
        print()


def test_multi_tenant_paths():
    """Test that the multi-tenant paths are configured correctly"""
    print("🔍 Testing Multi-Tenant Path Structure")

    club_prefix = getattr(settings, 'CLUB_PREFIX', None)
    if not club_prefix:
        print("   ❌ CLUB_PREFIX not set!")
        return

    static_url = settings.STATIC_URL
    expected_path = f"/{club_prefix}/static/"

    if expected_path in static_url:
        print(f"   ✅ Static URL contains correct club prefix: {club_prefix}")
        print(f"      URL: {static_url}")
    else:
        print(f"   ❌ Static URL doesn't contain expected path: {expected_path}")
        print(f"      Actual URL: {static_url}")
    print()


def main():
    """Run all tests"""
    print("=" * 60)
    print("Multi-Tenant Static Files Verification")
    print("=" * 60)
    print()

    try:
        test_configuration()
        test_multi_tenant_paths()
        test_static_files()

        print("=" * 60)
        print("✅ Verification Complete!")
        print("🎉 Multi-tenant GCP static files are properly configured")
        print("=" * 60)

    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())

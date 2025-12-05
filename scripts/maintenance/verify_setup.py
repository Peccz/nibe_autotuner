#!/usr/bin/env python
"""
Verify that the development environment is set up correctly
"""
import sys

def check_imports():
    """Check if all critical packages can be imported"""
    packages = [
        ('myuplink', 'myUplink Python library'),
        ('aiohttp', 'Async HTTP client'),
        ('requests', 'HTTP library'),
        ('requests_oauthlib', 'OAuth2 for requests'),
        ('sqlalchemy', 'Database ORM'),
        ('pandas', 'Data analysis'),
        ('fastapi', 'API framework'),
        ('loguru', 'Logging'),
        ('dotenv', 'Environment variables'),
    ]

    print("=" * 60)
    print("Verifying Python Environment Setup")
    print("=" * 60)
    print(f"\nPython version: {sys.version}")
    print(f"Python executable: {sys.executable}\n")

    all_ok = True

    for package, description in packages:
        try:
            module = __import__(package)
            version = getattr(module, '__version__', 'unknown')
            print(f"✓ {package:20s} v{version:12s} - {description}")
        except ImportError as e:
            print(f"✗ {package:20s} - MISSING! {description}")
            all_ok = False

    print("\n" + "=" * 60)

    if all_ok:
        print("✓ All packages installed successfully!")
        print("\nNext steps:")
        print("1. Register app at https://dev.myuplink.com/")
        print("2. Create .env file with your credentials")
        print("3. Run: python src/auth.py")
        print("=" * 60)
        return 0
    else:
        print("✗ Some packages are missing!")
        print("\nTry running: pip install -r requirements.txt")
        print("=" * 60)
        return 1

if __name__ == '__main__':
    sys.exit(check_imports())

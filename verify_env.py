from dotenv import load_dotenv
import os

def check_env():
    print("Checking .env configuration...")
    # Load .env explicitly
    load_dotenv()
    
    # Check keys
    keys = ["TIBBER_API_TOKEN", "MYUPLINK_CLIENT_ID", "MYUPLINK_CLIENT_SECRET", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"]
    
    print(f"{ 'KEY':<25} | {'STATUS':<10}")
    print("-" * 40)
    
    all_good = True
    for key in keys:
        val = os.getenv(key)
        if val:
            masked = val[:4] + "..." + val[-4:] if len(val) > 8 else "****"
            print(f"{key:<25} | OK ({len(val)} chars)")
        else:
            print(f"{key:<25} | MISSING ❌")
            all_good = False
            
    if all_good:
        print("\n✅ All critical keys are present!")
    else:
        print("\n⚠️ Some keys are missing.")

if __name__ == "__main__":
    check_env()

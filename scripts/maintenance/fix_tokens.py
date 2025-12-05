#!/usr/bin/env python3
import json
import os

tokens = {
    "access_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6Ijg0Qzg3RkM0Q0Q3QzlBQTlCNDZDNkRGRDJCNDE5NUYwQjgyQkYxNzJSUzI1NiIsInR5cCI6ImF0K2p3dCIsIng1dCI6ImhNaF94TTE4bXFtMGJHMzlLMEdWOExncjhYSSJ9.eyJuYmYiOjE3NjQ1Nzg0OTEsImV4cCI6MTc2NDU4MjA5MSwiaXNzIjoiaHR0cHM6Ly9hcGkubXl1cGxpbmsuY29tIiwiYXVkIjoiQVBJLXYyIiwiY2xpZW50X2lkIjoiODc1NjhjNzAtMmViOC00YTdiLTljMmItMWIyMTY4NzIxODM2Iiwic3ViIjoiNzA0ODI0MGEtODQ5MS00YWJkLWQ3ZTQtMDhkYzIzMGUzYzk3IiwiYXV0aF90aW1lIjoxNzY0NTc4MjM1LCJpZHAiOiJsb2NhbCIsImlzZGVtbyI6IkZhbHNlIiwidW5pdHN5c3RlbSI6Ik1ldHJpYyIsImp0aSI6IkVGODgxQTJBMjdDRUVFNjU4NUIyQTNFNEZCQkVFMTQxIiwic2lkIjoiRjhEMDc0MkRDNEUxMTc0OEFGMjM2NkI4ODA4NkQ5OUUiLCJpYXQiOjE3NjQ1Nzg0OTEsInNjb3BlIjpbIlJFQURTWVNURU0iLCJXUklURVNZU1RFTSIsIm9mZmxpbmVfYWNjZXNzIl0sImFtciI6WyJwd2QiXX0.elqAogUh28GUypd0OKvtYvO2ABfASC--x7EHASFqe29VRM3diwNawPw-qX0QqPRFCpMPNKLIDZQ1MbUz_iBibRpwj0GzrK-BHYmyKBQ4yZffk2eRhDHnkKbHBn1rKFPzyNChRlYDQzDMa7IJ1zJp29zo6fzw9qwG43GYrMdZ02J2DwfpKNlsB-sUgLNWIE74ZP-BwUJMXazQk8cwFsxCaRv88nCXhOPO9aZcwajESi_D-EmS9YzmZWGaryZxylQXZqwG13O445GZzDldBitlmx80JvWJ5glGqhhFAVttdhvM_BhkoX2y06NqzIKwaMYcq8l_bR30M8FWmRVUHK_DAQ",
    "expires_in": 3600,
    "token_type": "Bearer",
    "refresh_token": "7AED264E8A8BD737ACAE48E039C3DD7CD11E084EDE75CBDE430BCDD213733F7A",
    "scope": "READSYSTEM WRITESYSTEM offline_access",
    "expires_at": 1764582091.5431485
}

token_path = os.path.expanduser("~/.myuplink_tokens.json")
with open(token_path, 'w') as f:
    json.dump(tokens, f, indent=2)

print(f"✓ Token file created at: {token_path}")
print(f"✓ File is valid JSON: {json.loads(open(token_path).read()) is not None}")
print(f"✓ Has refresh_token: {'refresh_token' in json.loads(open(token_path).read())}")

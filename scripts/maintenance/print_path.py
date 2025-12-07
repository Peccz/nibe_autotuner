import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, project_root)

print(f"Current working directory: {os.getcwd()}")
print(f"Project root added to path: {project_root}")
print("sys.path:")
for p in sys.path:
    print(f"  {p}")
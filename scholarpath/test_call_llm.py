import sys
import os

sys.path.append(r"c:\Users\venom\Desktop\scholarpath\ScholarPath")
from backend.agents.verification_agent import _call_llm

try:
    print("Calling LLM...")
    res = _call_llm("test")
    print("Response:", res)
except Exception as e:
    print("Exception:", e)

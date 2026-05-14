import sys
import os

try:
    import docx
    print("python-docx is installed")
except ImportError:
    print("python-docx is NOT installed")

try:
    from langchain.agents import create_agent
    print(f"create_agent found in {create_agent.__module__}")
    import inspect
    print(f"create_agent file: {inspect.getfile(create_agent)}")
except ImportError:
    print("langchain.agents.create_agent NOT found")
except Exception as e:
    print(f"Error checking create_agent: {e}")

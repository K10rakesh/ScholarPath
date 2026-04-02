# import sys
# import os

# sys.path.insert(0, os.path.dirname(__file__))
# scholarpath/conftest.py  ← already exists per your screenshot, check its content
import sys
import os

# This makes "from backend.xxx import ..." work during pytest
sys.path.insert(0, os.path.dirname(__file__))
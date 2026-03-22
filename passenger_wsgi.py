import sys
import os

# Path to the folder containing the bios_workbench package
project_home = os.path.dirname(__file__)

# Tell Python to look in that specific folder
sys.path.insert(0, project_home)

# Import the Flask app object
from bios_workbench.ui.app import app as application
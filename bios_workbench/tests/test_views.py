import pandas as pd
from bios_workbench.core.engine import BIOSProcessEngine
from bios_workbench.core import view_builders
import os


def test_role_handbook_not_empty(tmp_path):
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'sample_lead_to_order.csv'))
    engine = BIOSProcessEngine()
    engine.load(path)
    roles = view_builders.build_people_roles(engine)
    # choose a human role
    human_roles = [r for r in roles if not r.startswith('system:')]
    assert human_roles
    info = roles[human_roles[0]]
    assert info['steps']

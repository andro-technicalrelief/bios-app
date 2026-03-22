from bios_workbench.core.engine import BIOSProcessEngine
from bios_workbench.core.drawio_export import export_drawio_xml
import os

def test_drawio_contains_nodes_and_lanes():
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'sample_lead_to_order.csv'))
    engine = BIOSProcessEngine()
    engine.load(path)
    xml = export_drawio_xml(engine)
    # should contain at least one step uid and one lane label
    assert 'S1' in xml
    assert 'Sales Rep' in xml or 'Email' in xml

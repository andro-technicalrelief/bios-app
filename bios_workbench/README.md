# BIOS Workbench v1

A unified platform for building and browsing process flows, employee handbooks, system and metric catalogues.

## Getting Started

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run Streamlit UI:
   ```bash
   streamlit run ui/app.py
   ```

3. Use Flow Studio tab to create a flow from NL text or upload a PDF/TXT/DOCX. Export the BIOS Contract CSV.

4. Upload the CSV on the same tab and resolve any validation errors.

5. Browse other tabs to explore Process Architecture, People & Roles, System Catalogues, Metrics & KPIs.

6. On the Process Architecture tab you can copy Draw.io XML and paste into diagrams.net (Arrange → Insert → Advanced → XML) to see the flow diagram.

## Sample data

`data/sample_lead_to_order.csv` contains a minimal example with decisions, multiple roles, a system lane, metrics, KPIs and reports.

## Development

- Core logic lives in `bios_workbench/core` and is UI-agnostic.
- UI components are under `bios_workbench/ui` using Streamlit.
- Tests under `bios_workbench/tests` ensure contract validation and view generation.

Run tests with:
```bash
pytest
```

## Future

The core engine can be exposed via FastAPI, connected to a Postgres backend, and a React front end can replace Streamlit. The CSV contract may be extended to support more metadata.

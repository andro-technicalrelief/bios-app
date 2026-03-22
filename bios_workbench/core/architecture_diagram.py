from xml.sax.saxutils import escape

BOX_WIDTH = 220
BOX_HEIGHT = 60
X_GAP = 280
Y_GAP = 120


def export_value_chain_architecture_xml(engine):

    df = engine.get_dataframe()

    hierarchy = {}
    for _, row in df.iterrows():
        outcome = row["Outcome"]
        core = row["Core Process"]
        sub = row["Sub Process"]

        hierarchy.setdefault(outcome, {})
        hierarchy[outcome].setdefault(core, set())
        hierarchy[outcome][core].add(sub)

    cells = []
    edges = []

    vertex_id = 2
    y_offset = 50

    for outcome, cores in hierarchy.items():

        outcome_id = str(vertex_id)
        cells.append(
            f'<mxCell id="{outcome_id}" value="{escape(outcome)}" '
            f'style="rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;" '
            f'vertex="1" parent="1">'
            f'<mxGeometry x="50" y="{y_offset}" width="{BOX_WIDTH}" height="{BOX_HEIGHT}" as="geometry"/>'
            f'</mxCell>'
        )
        vertex_id += 1

        core_y = y_offset

        for core, subs in cores.items():

            core_id = str(vertex_id)
            cells.append(
                f'<mxCell id="{core_id}" value="{escape(core)}" '
                f'style="rounded=1;whiteSpace=wrap;html=1;fillColor=#d5e8d4;" '
                f'vertex="1" parent="1">'
                f'<mxGeometry x="{50 + X_GAP}" y="{core_y}" width="{BOX_WIDTH}" height="{BOX_HEIGHT}" as="geometry"/>'
                f'</mxCell>'
            )

            # 🔵 Arrow: Outcome → Core
            edges.append(
                f'<mxCell id="{vertex_id + 10000}" '
                f'style="endArrow=block;html=1;rounded=0;" '
                f'edge="1" parent="1" source="{outcome_id}" target="{core_id}">'
                f'<mxGeometry relative="1" as="geometry"/>'
                f'</mxCell>'
            )

            vertex_id += 1
            sub_y = core_y

            for sub in sorted(subs):
                sub_id = str(vertex_id)
                cells.append(
                    f'<mxCell id="{sub_id}" value="{escape(sub)}" '
                    f'style="rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;" '
                    f'vertex="1" parent="1">'
                    f'<mxGeometry x="{50 + 2 * X_GAP}" y="{sub_y}" width="{BOX_WIDTH}" height="{BOX_HEIGHT}" as="geometry"/>'
                    f'</mxCell>'
                )

                # 🔵 Arrow: Core → Sub
                edges.append(
                    f'<mxCell id="{vertex_id + 20000}" '
                    f'style="endArrow=block;html=1;rounded=0;" '
                    f'edge="1" parent="1" source="{core_id}" target="{sub_id}">'
                    f'<mxGeometry relative="1" as="geometry"/>'
                    f'</mxCell>'
                )

                vertex_id += 1
                sub_y += Y_GAP

            core_y = sub_y + 40

        y_offset = core_y + 80

    xml = (
        "<mxfile><diagram>"
        '<mxGraphModel dx="0" dy="0" grid="1" gridSize="10">'
        "<root>"
        '<mxCell id="0"/>'
        '<mxCell id="1" parent="0"/>'
        + "".join(cells)
        + "".join(edges)
        + "</root></mxGraphModel></diagram></mxfile>"
    )

    return xml
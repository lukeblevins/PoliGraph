import warnings

import networkx as nx

from poligrapher.document import SECTION_ELEMENTS, TEXT_CONTAINER_ELEMENTS
from poligrapher.graph_utils import yaml_dump_graph, yaml_load_graph


def test_networkx_node_link_format_is_explicit_and_round_trips():
    graph = nx.MultiDiGraph()
    graph.add_node("we", type="ACTOR")
    graph.add_node("email", type="DATA")
    graph.add_edge("we", "email", key="COLLECT", text=["We collect email."])

    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        serialized = yaml_dump_graph(graph)
        restored = yaml_load_graph(serialized)

    assert restored.has_edge("we", "email", "COLLECT")


def test_current_chromium_layout_roles_are_classified():
    assert {"LayoutTable", "LayoutTableRow"} <= SECTION_ELEMENTS
    assert {"LayoutTableCell", "code"} <= TEXT_CONTAINER_ELEMENTS

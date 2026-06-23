from app.workers.workflows import _topological_order


def test_topo_simple():
    steps = [
        {"id": "a", "next": ["b"]},
        {"id": "b", "next": ["c"]},
        {"id": "c", "next": []},
    ]
    order = [s["id"] for s in _topological_order(steps)]
    assert order == ["a", "b", "c"]


def test_topo_diamond():
    steps = [
        {"id": "a", "next": ["b", "c"]},
        {"id": "b", "next": ["d"]},
        {"id": "c", "next": ["d"]},
        {"id": "d", "next": []},
    ]
    order = [s["id"] for s in _topological_order(steps)]
    assert order[0] == "a"
    assert order[-1] == "d"
    assert set(order[1:3]) == {"b", "c"}

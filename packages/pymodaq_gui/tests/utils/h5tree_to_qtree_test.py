from pymodaq_gui.utils.utils import h5tree_to_QTree


class _Attrs:
    def __init__(self, attrs: dict):
        self._attrs = attrs
        self.attrs_name = list(attrs.keys())

    def __getitem__(self, key):
        return self._attrs[key]


class _Node:
    """Minimal stand-in for a pymodaq_data h5 node, enough for h5tree_to_QTree."""

    def __init__(self, name, path, attrs, children=None):
        self.name = name
        self.path = path
        self.title = ''
        self.attrs = _Attrs(attrs)
        self._children = children or {}

    def children(self):
        return self._children


def _make_root():
    pix_node = _Node('data', '/data', {'CLASS': 'CARRAY', 'pixmap': b''})
    return _Node('root', '/', {'CLASS': 'GROUP'}, {'data': pix_node})


def test_h5tree_to_QTree_default_pixmap_items_not_shared(qtbot):
    _, pixmap_items_first = h5tree_to_QTree(_make_root())
    _, pixmap_items_second = h5tree_to_QTree(_make_root())

    assert len(pixmap_items_first) == 1
    assert len(pixmap_items_second) == 1
    assert pixmap_items_first is not pixmap_items_second

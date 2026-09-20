"""Floating viewer window — one tab per computed variable.

Each computed variable that the user marks for display gets its own tab in a
``QTabWidget``.  The viewer type (Viewer0D / 1D / 2D / ND) is chosen
automatically from the data's dimension metadata.

Usage
-----
    window = DataViewerWindow()
    window.show_variable('my_result', dwa)   # creates tab + shows data
    window.update('my_result', new_dwa)      # refreshes existing tab
    window.remove_variable('my_result')      # closes the tab
"""
from __future__ import annotations

from typing import Optional

from qtpy.QtCore import Signal
from qtpy.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from pymodaq_data.data import DataWithAxes
from pymodaq_gui.plotting.data_viewers.base import ViewersEnum
from pymodaq_gui.plotting.data_viewers.viewer import viewer_factory
from pymodaq_utils.logger import set_logger, get_module_name

logger = set_logger(get_module_name(__file__))


class DataViewerWindow(QWidget):
    """Floating window holding one viewer tab per computed variable.

    Signals
    -------
    tab_closed_sig(name)
        Emitted when the user clicks the × on a tab so that the variable
        browser can uncheck the corresponding Display checkbox.
    """

    tab_closed_sig = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle('DataMixer — Viewers')
        self.resize(800, 600)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._on_tab_close)
        # name → ViewerBase
        self._viewers: dict[str, object] = {}
        # name → shape tuple of the DWA the viewer was created with
        self._viewer_shapes: dict[str, tuple] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tabs)

    # ── public API ─────────────────────────────────────────────────────────────

    def show_variable(self, name: str, dwa: DataWithAxes) -> None:
        """Create a tab for *name* if absent, then show *dwa*.

        Switches the tab widget to the new/existing tab.
        """
        if name not in self._viewers:
            self._create_tab(name, dwa)
        else:
            self._viewers[name].show_data(dwa)
        idx = self._tab_index(name)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def update(self, name: str, dwa: DataWithAxes) -> None:  # noqa: A003
        """Update an existing tab with new data.  No-op if the tab is absent.

        """
        if name not in self._viewers:
            return
        dwa = self._normalize_nav_indexes(dwa)
        if self._viewer_shapes.get(name) != dwa.shape:
            # Shape changed — recreate so the viewer sets up axes correctly.
            idx = self._tab_index(name)
            was_current = (idx >= 0 and self._tabs.currentIndex() == idx)
            self.remove_variable(name)
            self._create_tab(name, dwa)
            if was_current:
                new_idx = self._tab_index(name)
                if new_idx >= 0:
                    self._tabs.setCurrentIndex(new_idx)
        else:
            viewer = self._viewers[name]
            viewer.show_data(dwa)

    def remove_variable(self, name: str) -> None:
        """Remove the tab for *name* (no signal emitted)."""
        idx = self._tab_index(name)
        if idx >= 0:
            self._tabs.removeTab(idx)
        self._viewers.pop(name, None)
        self._viewer_shapes.pop(name, None)

    def clear(self) -> None:
        """Remove all tabs."""
        self._tabs.clear()
        self._viewers.clear()
        self._viewer_shapes.clear()

    def has_variable(self, name: str) -> bool:
        """Return True if a tab exists for *name*."""
        return name in self._viewers

    @property
    def variable_names(self) -> list[str]:
        """Names of all currently open tabs."""
        return list(self._viewers.keys())

    # ── internal ───────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_nav_indexes(dwa: DataWithAxes) -> DataWithAxes:
        """Ensure the DWA has at most 2 signal dimensions.

        All viewers enforce ``len(sig_indexes) <= 2``.  ``nav_indexes`` is now
        tracked by dimension name through xarray operations (see
        ``DataWithAxes.to_xarray``/``from_xarray``), so a formula result should
        normally already carry correct navigation info.  If a DWA still
        arrives with more than 2 signal dims and no navigation at all, it
        genuinely has none — e.g. a formula built a fresh array with
        ``np.zeros(...)`` with no axis metadata to inherit — so promoting
        leading dims to navigation here is a last-resort fallback to avoid a
        hard crash, not an expected code path. Log it so it stays visible.
        """
        if len(dwa.sig_indexes) <= 2:
            return dwa
        if len(dwa.nav_indexes) != 0:
            # nav_indexes is set but still leaves >2 signal dims: this is
            # genuinely >2D signal data, not a lost-metadata case. Don't
            # clobber correct info with a guess; let the viewer lookup fail
            # honestly instead.
            return dwa
        logger.warning(
            f'{dwa.name!r} has {len(dwa.shape)} dims with no navigation info; '
            f'guessing the leading dims are navigation so it can be displayed.')
        ndim = len(dwa.shape)
        n_nav = ndim - 2          # keep exactly 2 signal dims
        dwa.nav_indexes = tuple(range(n_nav))
        return dwa

    def _create_tab(self, name: str, dwa: DataWithAxes) -> None:
        """Instantiate the right viewer type inside a fresh container widget."""
        dwa = self._normalize_nav_indexes(dwa)
        container = QWidget()
        viewer_type = ViewersEnum.get_viewers_enum_from_data(dwa)
        viewer = viewer_factory.get(viewer_type.name, parent=container, title=name)
        viewer.show_data(dwa)
        self._viewers[name] = viewer
        self._viewer_shapes[name] = dwa.shape
        idx = self._tabs.addTab(container, name)
        self._tabs.setTabToolTip(idx, f'{viewer_type.name}  •  {dwa.dim.name}')

    def _tab_index(self, name: str) -> int:
        """Return the tab index for *name*, or -1 if absent."""
        for i in range(self._tabs.count()):
            if self._tabs.tabText(i) == name:
                return i
        return -1

    def _on_tab_close(self, index: int) -> None:
        name = self._tabs.tabText(index)
        self._tabs.removeTab(index)
        self._viewers.pop(name, None)
        self._viewer_shapes.pop(name, None)
        self.tab_closed_sig.emit(name)

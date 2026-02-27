"""Kept for backward-compatibility.

Use :class:`~pymodaq.extensions.data_mixer.gui.data_mixer_gui.DataMixerGUI`
directly instead.

Usage
-----
    python formula_debugger.py [path/to/scan.h5]
"""
from pymodaq.extensions.data_mixer.gui.data_mixer_gui import DataMixerGUI, main  # noqa: F401

if __name__ == '__main__':
    main()

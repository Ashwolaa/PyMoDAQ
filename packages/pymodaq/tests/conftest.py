"""Root conftest for pymodaq tests.

Sets QT_QPA_PLATFORM=offscreen before any Qt import so that Qt tests run
headlessly without a display server.  Must be at module level (not inside a
fixture) to take effect before pytest-qt creates the QApplication.
"""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

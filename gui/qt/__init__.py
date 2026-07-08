# This file is part of PLaSK (https://plask.app) by Photonics Group at TUL
# Copyright (c) 2022 Lodz University of Technology
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.


import sys
import os


def _setup_matplotlib(backend):
    try:
        import matplotlib
    except ImportError:
        pass
    else:
        os.environ['QT_API'] = backend.lower()
        try:
            matplotlib.use('QtAgg')
        except (ValueError, ImportError):
            if backend not in ('PyQt5', 'PySide2'):
                return False
            try:
                matplotlib.use('Qt5Agg')
            except (ValueError, ImportError):
                return False
            try:
                matplotlib.rcParams['backend.qt5'] = backend
            except (KeyError, ValueError):
                pass
    return True


QT_API = os.environ.get('PLASK_QT_API', os.environ.get('QT_API'))

if QT_API is not None:
    QT_API = dict(pyqt5='PyQt5', pyside2='PySide2', pyqt6='PyQt6', pyside6='PySide6').get(QT_API.lower())
    if QT_API is None:
        import warnings
        warnings.warn("Ignoring unknown QT_API environmental variable!")

if QT_API is None:
    try:
        import matplotlib

        matplotlib.use('QtAgg')

        from matplotlib.backends import qt_compat
        
        QT_API = dict(pyqt5='PyQt5', pyside2='PySide2', pyqt6='PyQt6', pyside6='PySide6').get(str(qt_compat.QT_API).lower())
    except (ImportError, AttributeError):
        pass

search_order = [QT_API] if QT_API else ['PyQt6', 'PySide6', 'PyQt5', 'PySide2']

for cand_api in search_order:
    if cand_api is None:
        continue
    elif cand_api == 'PyQt6':
        try: from PyQt6 import QtCore, QtWidgets, QtGui, QtHelp
        except ImportError as e:
            print(f"PyQt6 import failed with error: {e}")
            if 'PyQt6' in sys.modules: del sys.modules['PyQt6']
        else: 
            if _setup_matplotlib(cand_api):
                QT_API = cand_api
                break
    elif cand_api == 'PySide6':
        try: from PySide6 import QtCore, QtWidgets, QtGui, QtHelp
        except ImportError as e:
            print(f"PySide6 import failed with error: {e}")
            if 'PySide6' in sys.modules: del sys.modules['PySide6']
        else:
            if _setup_matplotlib(cand_api):
                QT_API = cand_api
                break
    elif cand_api == 'PyQt5':
        try: 
            from PyQt5 import QtCore, QtWidgets, QtGui, QtHelp
        except ImportError as e:
            print(f"PyQt5 import failed with error: {e}")
            if 'PyQt5' in sys.modules: del sys.modules['PyQt5']
        else:
            if _setup_matplotlib(cand_api):
                QT_API = cand_api
                break
    else:  # QT_API == 'PySide2':
        try: from PySide2 import QtCore, QtWidgets, QtGui, QtHelp
        except ImportError as e:
            print(f"PySide2 import failed with error: {e}")
            if 'PySide2' in sys.modules: del sys.modules['PySide2']
        else:
            if _setup_matplotlib(cand_api):
                QT_API = cand_api
                break

if QT_API in ('PyQt5', 'PyQt6'):
    QtSignal = QtCore.pyqtSignal
    QtSlot = QtCore.pyqtSlot
else:
    QtSignal = QtCore.Signal
    QtSlot = QtCore.Slot

if os.name == 'nt':
    QtWidgets.QApplication.addLibraryPath(os.path.join(sys.prefix, 'Library', 'plugins'))
    QtWidgets.QApplication.addLibraryPath(os.path.join(os.path.dirname(QtCore.__file__), 'plugins'))


if QT_API in ('PyQt5', 'PySide2'):
    def qt_exec(self, *args, **kwargs):
        return self.exec_(*args, **kwargs)
    if not hasattr(QtGui.QFontMetrics, 'horizontalAdvance'):
        QtGui.QFontMetrics.horizontalAdvance = lambda self, *args, **kwargs: self.width(*args, **kwargs)
else:
    def qt_exec(self, *args, **kwargs):
        return self.exec(*args, **kwargs)


os.environ['QT_API'] = QT_API.lower()

sys.modules['gui.qt.QtCore'] = QtCore
sys.modules['gui.qt.QtWidgets'] = QtWidgets
sys.modules['gui.qt.QtGui'] = QtGui
sys.modules['gui.qt.QtHelp'] = QtHelp
__all__ = ['QtCore', 'QtWidgets', 'QtGui', 'QtHelp', 'QT_API', 'QtSignal', 'QtSlot', 'qt_exec']

# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec file for Power Systems Monitoring Dashboard
#
# Build with: pyinstaller main.spec --clean
# Output:     dist/PowerTeamDashboard/PowerTeamDashboard.exe
#
# The .exe is fully self-contained — copy the entire dist/PowerTeamDashboard/
# folder to any Windows machine and launch PowerTeamDashboard.exe directly.
# No Python installation required on the target machine.
#
# config.json and logs/ are created beside the .exe on first run.

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # pyvisa-py backend — must be explicit or PyInstaller misses it
        'pyvisa_py',
        'pyvisa_py.protocols',
        'pyvisa_py.protocols.usbtmc',
        'pyvisa_py.protocols.usbutil',
        'pyvisa_py.tcpip',
        'pyvisa_py.usb',
        'pyvisa_py.serial',
        'pyvisa_py.gpib',
        # pyqtgraph internals
        'pyqtgraph',
        'pyqtgraph.exporters',
        'pyqtgraph.exporters.ImageExporter',
        'pyqtgraph.exporters.CSVExporter',
        'pyqtgraph.Qt',
        # PyQt6
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'notebook',
        'IPython',
        'scipy',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PowerTeamDashboard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # No terminal window — GUI application
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',  # App icon — see assets/README.md for generation
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PowerTeamDashboard',
)

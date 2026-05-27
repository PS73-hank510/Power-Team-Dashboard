# Assets

## icon.ico

The application icon bundled into `PowerTeamDashboard.exe` by PyInstaller.

The included `icon.ico` is a minimal placeholder. To replace it with a proper
icon:

1. Create or obtain a 256×256 PNG image
2. Convert to ICO with multiple sizes (16, 32, 48, 256):
   ```
   pip install Pillow
   python -c "
   from PIL import Image
   img = Image.open('your_icon.png')
   img.save('icon.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(256,256)])
   "
   ```
3. Place the result at `assets/icon.ico`
4. Rebuild: `build.bat`

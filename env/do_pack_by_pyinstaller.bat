pyinstaller.exe pyinstaller_pack_f.spec
copy .\dist\MCU-MemTestUtility.exe ..\bin
rd /q /s .\build
rd /q /s .\dist
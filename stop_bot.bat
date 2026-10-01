@echo off
echo Arret du bot WikiMasters...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *watchdog*" >nul 2>&1
wmic process where "name='python.exe' and commandline like '%%watchdog.py%%'" call terminate >nul 2>&1
wmic process where "name='python.exe' and commandline like '%%autobot.py%%'" call terminate >nul 2>&1
echo Fait. Vivaldi reste ouvert (seul le bot est arrete).
pause

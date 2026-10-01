@echo off
setlocal

REM Edit this path if Vivaldi is installed elsewhere on your machine.
set VIVALDI="%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe"
set PORT=9333
set PROJECT_DIR=%~dp0

echo ============================================
echo   WikiMasters Bot - Lancement
echo ============================================
echo.
echo Ceci va FERMER puis RELANCER Vivaldi (avec le
echo mode debug active) pour que le bot puisse s'y
echo connecter. Tes onglets se restaurent tout seuls.
echo.
pause

echo.
echo [1/3] Fermeture de Vivaldi...
taskkill /F /IM vivaldi.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2/3] Relance de Vivaldi (port debug %PORT%)...
start "" %VIVALDI% --remote-debugging-port=%PORT% --restore-last-session
timeout /t 6 /nobreak >nul

echo [3/3] Lancement du bot...
echo.
echo (Laisse cette fenetre ouverte : la fermer arrete le bot.
echo  Ne minimise pas Vivaldi, juste derriere d'autres fenetres.)
echo.
cd /d "%PROJECT_DIR%"
python watchdog.py --connect %PORT%

pause

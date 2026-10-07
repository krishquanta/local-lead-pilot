@echo off
setlocal EnableDelayedExpansion
title Tamil Nadu Shop Outreach Control Center
cd /d "%~dp0"

set "CLI_ARG=%~1"

:: Check for direct command-line arguments
if /i "%CLI_ARG%"=="whatsapp" goto do_whatsapp
if /i "%CLI_ARG%"=="wa" goto do_whatsapp
if /i "%CLI_ARG%"=="mailer" goto do_mailer
if /i "%CLI_ARG%"=="email" goto do_mailer
if /i "%CLI_ARG%"=="autopilot" goto do_autopilot
if /i "%CLI_ARG%"=="scraper" goto do_scraper
if /i "%CLI_ARG%"=="research" goto do_research
if /i "%CLI_ARG%"=="summary" goto do_summary
if /i "%CLI_ARG%"=="dashboard" goto do_dashboard
if /i "%CLI_ARG%"=="funnel" goto do_funnel_ab
if /i "%CLI_ARG%"=="ab" goto do_funnel_ab
if /i "%CLI_ARG%"=="start-docker" goto do_start_docker
if /i "%CLI_ARG%"=="stop-docker" goto do_stop_docker
if /i "%CLI_ARG%"=="config-email" goto do_config_email

:menu
cls
echo ========================================================================
echo   TAMIL NADU SHOP OUTREACH CONTROL CENTER
echo ========================================================================
echo.
echo   [1]  WhatsApp Outreach Bot - Anti-ban typing and follow-ups
echo   [2]  Auto Cold Emailer - Zero approval, safe human pacing
echo   [3]  AutoPilot Engine - Continuous scrape, filter, outreach loop
echo   [4]  Continuous Google Maps Scraper - Maps and website lookup
echo   [5]  Re-search All Shops for Gmail - Social bios and deep scan
echo   [6]  View Daily Operations Summary - Today's metrics and quotas
echo   [7]  Sales Funnel and AB Copy Performance Benchmarks
echo   [8]  Launch Local Web Dashboard - viewer.html on port 8521
echo   [9]  Start Docker Scraper Container - port 8001
echo   [10] Stop Docker Scraper Container - Free up RAM
echo   [11] Configure Gmail SMTP Credentials and Test
echo   [0]  Exit
echo.
echo ========================================================================
set /p choice="  Enter choice [0-11]: "

if "%choice%"=="1" goto do_whatsapp
if "%choice%"=="2" goto do_mailer
if "%choice%"=="3" goto do_autopilot
if "%choice%"=="4" goto do_scraper
if "%choice%"=="5" goto do_research
if "%choice%"=="6" goto do_summary
if "%choice%"=="7" goto do_funnel_ab
if "%choice%"=="8" goto do_dashboard
if "%choice%"=="9" goto do_start_docker
if "%choice%"=="10" goto do_stop_docker
if "%choice%"=="11" goto do_config_email
if "%choice%"=="0" goto do_exit

echo.
echo [!] Invalid option. Please select 0 to 11.
timeout /t 2 > nul
goto menu

:do_whatsapp
cls
echo ========================================================================
echo   WhatsApp Outreach Bot
echo ========================================================================
echo.
echo Starting initial outreach batch...
python main.py whatsapp --limit 10
echo.
echo ------------------------------------------------------------------------
echo   Checking for 48-Hour Follow-Up Nudges...
echo ------------------------------------------------------------------------
python main.py whatsapp --follow-up --limit 5
echo.
echo ------------------------------------------------------------------------
echo   Daily Operations Summary:
echo ------------------------------------------------------------------------
python main.py summary
echo.
if not "%CLI_ARG%"=="" exit /b 0
pause
goto menu

:do_mailer
cls
echo ========================================================================
echo   Autonomous Cold Emailer
echo ========================================================================
echo.
python main.py mailer --watch
echo.
python main.py summary
echo.
if not "%CLI_ARG%"=="" exit /b 0
pause
goto menu

:do_autopilot
cls
echo ========================================================================
echo   AutoPilot: Autonomous Shop Outreach Engine
echo ========================================================================
echo.
echo Safe Daily Limit: 20 messages with Anti-Ban Protection
echo.
python main.py autopilot --daily-limit 20
echo.
if not "%CLI_ARG%"=="" exit /b 0
pause
goto menu

:do_scraper
cls
echo ========================================================================
echo   Continuous Google Maps and Website Scraper
echo ========================================================================
echo.
python main.py scraper
echo.
if not "%CLI_ARG%"=="" exit /b 0
pause
goto menu

:do_research
cls
echo ========================================================================
echo   Deep Gmail Re-Search for Tamil Nadu Shops
echo ========================================================================
echo.
python main.py research
echo.
if not "%CLI_ARG%"=="" exit /b 0
pause
goto menu

:do_summary
cls
echo ========================================================================
echo   Daily Operations Summary
echo ========================================================================
echo.
python main.py summary
echo.
if not "%CLI_ARG%"=="" exit /b 0
pause
goto menu

:do_funnel_ab
cls
echo ========================================================================
echo   Conversion Pipeline and AB Copy Benchmark
echo ========================================================================
echo.
python main.py funnel
echo.
echo ------------------------------------------------------------------------
echo   AB Outreach Copy Performance Leaderboard:
echo ------------------------------------------------------------------------
python main.py ab
echo.
if not "%CLI_ARG%"=="" exit /b 0
pause
goto menu

:do_dashboard
cls
echo ========================================================================
echo   Launching Web Command Center Dashboard...
echo ========================================================================
echo.
echo Dashboard URL: http://localhost:8521/viewer.html
start http://localhost:8521/viewer.html
python main.py dashboard
echo.
if not "%CLI_ARG%"=="" exit /b 0
pause
goto menu

:do_start_docker
cls
echo ========================================================================
echo   Starting Docker Google Maps Scraper
echo ========================================================================
echo.
cd /d "%~dp0gmaps_scraper"
docker compose up -d
cd /d "%~dp0"
echo.
echo Scraper service started at http://localhost:8001
curl -s http://localhost:8001/ || echo Notice: Container is starting up.
echo.
if not "%CLI_ARG%"=="" exit /b 0
pause
goto menu

:do_stop_docker
cls
echo ========================================================================
echo   Stopping Docker Google Maps Scraper
echo ========================================================================
echo.
cd /d "%~dp0gmaps_scraper"
docker compose down
cd /d "%~dp0"
echo.
echo Scraper container stopped and RAM released!
echo.
if not "%CLI_ARG%"=="" exit /b 0
pause
goto menu

:do_config_email
cls
echo ========================================================================
echo   Configure Gmail SMTP Credentials
echo ========================================================================
echo.
python main.py config-email
echo.
if not "%CLI_ARG%"=="" exit /b 0
pause
goto menu

:do_exit
echo.
echo Exiting Control Center.
exit /b 0

@echo off
rem Piano B: esegue lo scraper sul PC (IP residenziale) e pubblica i JSON su GitHub.
rem Da schedulare con Utilita di pianificazione ogni 3 ore. Va lanciato dalla cartella della repo.
cd /d %~dp0
set HEADLESS=0
set BROWSER_CHANNEL=chrome
set OUT_DIR=output
python livesoccertv_scraper.py
git pull --rebase
git add output
git diff --cached --quiet || (git commit -m "LiveSoccerTV aggiornamento %date% %time%" && git push)

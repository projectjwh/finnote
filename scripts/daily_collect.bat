@echo off
REM finnote daily pipeline — orchestrated by pipeline_wrapper
REM Scheduled via Windows Task Scheduler at 5:00 PM daily

cd /d C:\Users\jwhyu\Desktop\claude_projects\finnote

REM Create timestamped run directory
for /f "tokens=1-4 delims=/ " %%a in ('date /t') do set DATESTAMP=%%d%%b%%c
for /f "tokens=1-2 delims=: " %%a in ('time /t') do set TIMESTAMP=%%a%%b
set RUN_DIR=.pw\data\runs\finnote_daily\%DATESTAMP%T%TIMESTAMP%

REM Execute pipeline through pw-run
pw-run --manifest pipeline\manifest.yaml --config pipeline\pw-config.yaml --output-dir %RUN_DIR% >> logs\daily_collect.log 2>&1

REM Post-run analysis
pw-review scan --log-dir %RUN_DIR% --trace %RUN_DIR%\execution_trace.json --output %RUN_DIR%\review.json >> logs\daily_collect.log 2>&1
pw-dag build --trace %RUN_DIR%\execution_trace.json --output %RUN_DIR%\dag.json >> logs\daily_collect.log 2>&1
pw-incident ingest --findings %RUN_DIR%\review.json --db .pw\data\incidents.db >> logs\daily_collect.log 2>&1

echo [%date% %time%] Pipeline complete >> logs\daily_collect.log

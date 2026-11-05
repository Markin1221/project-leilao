@echo off
rem Cria 2 tarefas no Agendador do Windows (rode uma vez).
cd /d "%~dp0"
schtasks /Create /F /TN "Leilao - atualizar lotes" /SC DAILY /ST 20:00 /TR "\"%~dp0atualizar_lotes.bat\""
schtasks /Create /F /TN "Leilao - leilao ao vivo" /SC WEEKLY /D THU /ST 08:15 /TR "\"%~dp0ao_vivo.bat\""
echo.
echo Pronto: lotes atualizados todo dia as 20h e o leilao de quinta acompanhado a partir das 8h15.
echo O PC precisa estar ligado nesses horarios. Log em robo.log
pause

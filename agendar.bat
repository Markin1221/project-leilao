@echo off
rem Cria 2 tarefas no Agendador do Windows (rode uma vez).
cd /d "%~dp0"
schtasks /Create /F /TN "Leilao - atualizar lotes" /SC DAILY /ST 20:00 /TR "\"%~dp0atualizar_lotes.bat\" auto"
schtasks /Create /F /TN "Leilao - leilao ao vivo" /SC WEEKLY /D THU,FRI /ST 08:15 /TR "\"%~dp0ao_vivo.bat\" auto"
echo.
echo Pronto: lotes atualizados todo dia as 20h e os leiloes de quinta e sexta acompanhados a partir das 8h15.
echo O PC precisa estar ligado nesses horarios. Log em robo.log
pause

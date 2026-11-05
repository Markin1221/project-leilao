# project-leilao

Análise e gestão de compra/venda de motos de leilão (Copart – Vitória de Santo Antão, pátio 92).

## Rodar
Precisa do Python 3.10+ (python.org, marque "Add to PATH").
- `iniciar.bat` → abre o site. PC: http://localhost:5000 · Celular (mesma Wi-Fi): http://IP-DO-PC:5000
- `atualizar_lotes.bat` → puxa as motos dos próximos leilões do pátio e manda alertas
- `ao_vivo.bat` → acompanha o leilão de hoje e grava por quanto cada moto saiu
- `agendar.bat` → (uma vez) agenda o atualizar todo dia 20h e o ao vivo toda quinta 8h15

## Configurar (`config.json`, criado na 1ª execução)
- `taxas_padrao`, `documentacao_padrao`, `frete_local`, `frete_outro_patio`: custos usados nas sugestões
- `interesses`: motos que geram alerta, ex. `{"modelo": "CG 160", "ano_min": 2020, "lance_ate": 12000}`
- `telegram_token` / `telegram_chat_id`: pra receber alertas no celular (crie um bot com o @BotFather)
- `navegador_visivel`: `true` se a Copart bloquear o robô

## Telas
Painel · Sugestões (lotes + lance máximo) · Calculadora · Histórico (valores de arremate)

Dados em `leilao.db` (fora do git).

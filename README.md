# Monitor de passagens saindo de Confins

Roda sozinho todo dia no GitHub (de graça) e avisa no Telegram quando:

- **RJ, SP ou Vitória**: algum fim de semana ou feriado tem **ida e volta, cada trecho até R$ 240**
  (ida na sexta ou na véspera do feriado; volta no último dia de folga ou no dia seguinte), a partir de jan/2027.
- **Ida e volta** (avisa quando aparece um **novo menor preço**, com o top 5 de datas):
  - Buenos Aires e Santiago: 5 a 10 dias, ida entre abril e setembro de 2027
  - Cuiabá ↔ Confins (saindo de Cuiabá): 5 a 10 dias, a partir de janeiro de 2027
  - Confins → Sinop ou Cuiabá: ida 18, 19 ou 20/12/2026 e volta 24, 25 ou 26/12/2026

Toda **segunda-feira** chega um resumo completo, mesmo sem novidade.

Os preços vêm do Google Flights, que reúne Azul, GOL, LATAM e agências. Sempre confira o valor final
no site antes de comprar. Ida e volta são somadas trecho a trecho (podem ser companhias diferentes).

## Como configurar (uma vez só)

### 1. Criar o bot do Telegram
1. No Telegram, abra o **@BotFather** e mande `/newbot`.
2. Escolha um nome e um usuário (precisa terminar em `bot`). Ele responde com um **token**
   parecido com `123456789:AAH...`. Guarde.
3. Abra o seu bot novo e mande qualquer mensagem (ex.: "oi").
4. No navegador, abra `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates`
   (troque `<SEU_TOKEN>` pelo token). Procure `"chat":{"id":` — esse número é o seu **chat id**.

### 2. Colocar as chaves no GitHub
No repositório: **Settings → Secrets and variables → Actions → New repository secret**
- `TELEGRAM_TOKEN` = o token do bot
- `TELEGRAM_CHAT_ID` = o número do chat id

### 3. Testar
**Actions → Monitor de passagens → Run workflow** (modo `teste`). Em 1–2 minutos chega uma
mensagem de teste no Telegram com 4 preços.

Pronto. A partir daí roda todo dia por volta das 6h40. Nos primeiros ~4 dias ele vai preenchendo
todas as datas (são ~2.300 buscas, feitas aos poucos para não ser bloqueado).

## Links de compra
Cada preço vem com links já preenchidos (rota + data) para **Google Flights, Kayak e Skyscanner**.

**Opcional – link direto de compra (🛒):** crie uma conta em ignav.com, copie a API key e crie o
secret `IGNAV_API_KEY` no GitHub. O monitor passa a mostrar o preço em reais do mercado brasileiro e um
link para comprar direto na companhia (ou na agência mais barata) para os voos que aparecem na mensagem.
1.000 consultas grátis; depois US$ 2 a cada 1.000 (limite de 25 trechos por dia em `config.py`).

## Como mudar algo
Tudo fica em `config.py`: limite de R$ 240, aeroportos, meses, duração da viagem, feriados de BH.
Para uma rota nova de ida e volta, copie um bloco da lista `IDA_E_VOLTA` e troque aeroportos e datas.

## Se parar de funcionar
O Google Flights não tem API oficial; o monitor usa a biblioteca `fast-flights`, que pode quebrar
se o Google mudar o site. Nesse caso você recebe um aviso de erro no Telegram.

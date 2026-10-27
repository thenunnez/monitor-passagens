# Monitor de passagens saindo de Confins

Roda sozinho todo dia no GitHub (de graça) e avisa no Telegram quando:

- **RJ, SP ou Vitória**: algum fim de semana ou feriado tem **ida e volta, cada trecho até R$ 240**
  (ida na sexta ou na véspera do feriado; volta no último dia de folga ou no dia seguinte).
- **Buenos Aires e Santiago**: aparece um **novo menor preço** de ida e volta de 5 a 10 dias,
  com ida entre abril e setembro de 2027.

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
todas as datas (são ~1.600 buscas, feitas aos poucos para não ser bloqueado).

## Como mudar algo
Tudo fica em `config.py`: limite de R$ 240, aeroportos, meses, duração da viagem, feriados de BH.
Por exemplo, para incluir Bariloche, acrescente `"Argentina (Bariloche)": ["BRC"],` em `INTERNACIONAL`.

## Se parar de funcionar
O Google Flights não tem API oficial; o monitor usa a biblioteca `fast-flights`, que pode quebrar
se o Google mudar o site. Nesse caso você recebe um aviso de erro no Telegram.

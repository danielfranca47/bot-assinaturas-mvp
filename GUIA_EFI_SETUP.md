# Guia de Setup EFI Bank — Bot de Assinaturas Telegram

Guia completo e didático para configurar credenciais, certificado mTLS, chave Pix e webhook da EFI Bank (Gerencianet) em um bot Python. Baseado em erros e soluções reais durante a implementação deste projeto.

---

## Índice

1. [Pré-requisitos](#1-pré-requisitos)
2. [Criar aplicação na EFI](#2-criar-aplicação-na-efi)
3. [Obter credenciais (Client ID e Secret)](#3-obter-credenciais-client-id-e-secret)
4. [Baixar e converter o certificado mTLS](#4-baixar-e-converter-o-certificado-mtls)
5. [Configurar a chave Pix](#5-configurar-a-chave-Pix)
6. [Preencher variáveis de ambiente](#6-preencher-variáveis-de-ambiente)
7. [Registrar o webhook](#7-registrar-o-webhook)
8. [Testar o fluxo completo](#8-testar-o-fluxo-completo)
9. [Migrar de homologação para produção](#9-migrar-de-homologação-para-produção)
10. [Erros comuns e soluções](#10-erros-comuns-e-soluções)

---

## 1. Pré-requisitos

- Conta ativa na [EFI Bank](https://sejaefi.com.br) com cadastro aprovado
- Python 3.11+ com `efipay` e `cryptography` instalados
- Ngrok (para testes locais) ou URL pública fixa (Railway, etc.)
- Bot do Telegram criado via @BotFather com token em mãos

---

## 2. Criar aplicação na EFI

1. Acesse **API > Aplicações** no painel da EFI
2. Clique em **Criar nova aplicação**
3. Dê um nome (ex: `bot-assinaturas`)
4. Marque o escopo **API Pix** (obrigatório para cobranças Pix)
5. Salve

> Você precisará criar **duas aplicações separadas**: uma para homologação (sandbox) e outra para produção. As credenciais são diferentes e não intercambiáveis.

---

## 3. Obter credenciais (Client ID e Secret)

Para cada aplicação (homologação e produção):

1. Acesse **API > Aplicações** e clique na aplicação criada
2. Copie o **Client ID** e o **Client Secret**
3. Guarde em um local seguro — o Client Secret não é exibido novamente após a criação

> **Importante:** As credenciais de homologação (`EFI_SANDBOX=true`) só funcionam com o servidor sandbox da EFI (`pix-h.api.efipay.com.br`). As de produção só funcionam com o servidor real (`pix.api.efipay.com.br`). Misturar as duas causa `UnauthorizedError`.

---

## 4. Baixar e converter o certificado mTLS

A API Pix da EFI exige autenticação mútua TLS (mTLS). O certificado é necessário tanto para criar cobranças quanto para receber webhooks.

### 4.1 Baixar o certificado

1. No painel EFI, acesse **API > Certificados**
2. Baixe o certificado da aplicação correspondente (homologação ou produção)
3. O arquivo virá no formato `.p12` (PKCS12)

> Cada ambiente tem seu próprio certificado. Não use o certificado de homologação com credenciais de produção.

### 4.2 Converter de .p12 para .pem

O SDK `efipay` usa a biblioteca `requests`, que aceita apenas arquivos `.pem`. O arquivo `.p12` precisa ser convertido.

**Passo 1:** Copie o arquivo `certificado.p12` para a raiz do projeto.

**Passo 2:** Execute o script de conversão já presente no projeto:

```bash
python fix_cert.py
```

Saída esperada:
```
certificado.pem gerado com senha=b''
Validando o PEM gerado...
PEM VALIDO — pronto para uso
```

Se aparecer `PEM INVALIDO`, o certificado pode ter senha. Edite `fix_cert.py` e adicione a senha em bytes na lista `for senha in [b"", None]`.

### 4.3 Ordem dos blocos no PEM

O `requests`/`ssl` exige que o arquivo `.pem` tenha o **certificado público primeiro**, seguido da **chave privada**. O `fix_cert.py` já garante essa ordem:

```
-----BEGIN CERTIFICATE-----
(certificado público)
-----END CERTIFICATE-----
-----BEGIN RSA PRIVATE KEY-----
(chave privada)
-----END RSA PRIVATE KEY-----
```

Se a ordem estiver invertida (chave antes do cert), o SSL lança `SSL_CTX_use_certificate` errors.

### 4.4 Adicionar ao controle de versão

O arquivo `certificado.pem` **pode ser commitado** (contém apenas chave privada do ambiente específico, sem segredos de acesso). O `certificado.p12` original fica no `.gitignore`.

Para Railway (deploy em produção), o `.pem` precisa estar no repositório ou ser configurado como variável de ambiente.

---

## 5. Configurar a chave Pix

1. No painel EFI, acesse **Minha conta > Chaves Pix**
2. Cadastre uma chave (CNPJ, e-mail, telefone ou aleatória)
3. Copie o valor exato da chave cadastrada — será usado em `EFI_PIX_KEY`

> A chave Pix usada no código (`EFI_PIX_KEY`) deve ser exatamente igual à cadastrada na conta EFI. Uma chave de homologação e uma de produção são contas diferentes.

---

## 6. Preencher variáveis de ambiente

No arquivo `.env` do projeto:

```env
# Credenciais da aplicação EFI Bank
EFI_CLIENT_ID=seu_client_id_aqui
EFI_CLIENT_SECRET=seu_client_secret_aqui

# Chave Pix cadastrada na conta EFI
EFI_PIX_KEY=sua_chave_pix_aqui

# Caminho para o certificado PEM convertido
EFI_CERT_PATH=./certificado.pem

# true = usa servidor de homologação | false = usa produção real
EFI_SANDBOX=false

# URL pública do servidor (Railway, ngrok etc.)
WEBHOOK_BASE_URL=https://sua-url-publica.com
```

> **`EFI_SANDBOX`**: use `true` durante desenvolvimento (sandbox da EFI) e `false` em produção. Esta flag troca automaticamente o host da API usada pelo SDK.

---

## 7. Registrar o webhook

O webhook informa à EFI para qual URL enviar notificações de pagamento confirmado.

### 7.1 Como a EFI valida o webhook

Ao registrar o webhook, a EFI faz um `POST` para a URL base (`/webhook/efi`) para confirmar que o servidor está online. Depois, os eventos de Pix chegam em `/webhook/efi/pix` (a EFI acrescenta `/pix` automaticamente).

Por isso, o servidor precisa ter **dois endpoints ativos**:

| Endpoint | Função |
|---|---|
| `POST /webhook/efi` | Validação na hora do registro — retorna 200 OK |
| `POST /webhook/efi/pix` | Recebe as notificações de pagamento confirmado |

### 7.2 Executar o registro

Com o servidor rodando (`python main.py`), execute em outro terminal:

```bash
python setup_webhook.py
```

Saída esperada (sucesso):
```
Registrando webhook: https://sua-url/webhook/efi
Webhook registrado: {'webhookUrl': 'https://sua-url/webhook/efi'}
Webhook ativo: {'webhookUrl': '...', 'chave': '...', 'criacao': '...'}
```

### 7.3 Quando re-registrar o webhook

Sempre que a URL pública mudar (novo deploy no Railway, novo túnel ngrok, novo domínio), é necessário rodar `setup_webhook.py` novamente.

### 7.4 mTLS e o header x-skip-mtls-checking

A EFI exige mTLS para validar o webhook em produção plena. O header `x-skip-mtls-checking: true` (já incluído no `setup_webhook.py`) pula essa verificação, funcionando tanto em homologação quanto em produção para bots simples sem infraestrutura própria de TLS mútuo.

---

## 8. Testar o fluxo completo

### Em homologação (sandbox)

1. Configure `EFI_SANDBOX=true` e credenciais de homologação
2. Inicie o servidor: `python main.py`
3. Inicie o ngrok: `ngrok http 8000`
4. Atualize `WEBHOOK_BASE_URL` com a URL do ngrok e registre o webhook
5. No Telegram, envie `/assinar` e escolha um plano
6. Copie o código Pix gerado
7. No painel EFI (homologação), acesse **API Pix > Cobranças imediatas** e simule o pagamento
8. Aguarde a mensagem de confirmação no Telegram

### Em produção

1. Configure `EFI_SANDBOX=false` e credenciais de produção
2. Use o certificado `.pem` de produção
3. Inicie o servidor e registre o webhook com a URL pública
4. Realize um pagamento Pix real pelo app do banco
5. Confirme que a mensagem de acesso chegou no Telegram

---

## 9. Migrar de homologação para produção

Checklist completo para troca de ambiente:

- [ ] Criar nova aplicação EFI em **produção** (não homologação)
- [ ] Copiar novo `EFI_CLIENT_ID` e `EFI_CLIENT_SECRET` de produção
- [ ] Baixar novo `certificado.p12` de produção
- [ ] Rodar `python fix_cert.py` para gerar novo `certificado.pem`
- [ ] Atualizar `EFI_PIX_KEY` com chave Pix da conta de produção
- [ ] Setar `EFI_SANDBOX=false` no `.env`
- [ ] Verificar que `WEBHOOK_BASE_URL` aponta para URL pública ativa
- [ ] Reiniciar `main.py`
- [ ] Rodar `python setup_webhook.py` e confirmar sucesso
- [ ] Fazer um pagamento de teste real e confirmar recebimento no Telegram

> Misturar credenciais de homologação com `EFI_SANDBOX=false` (ou vice-versa) causa `UnauthorizedError` imediatamente.

---

## 10. Erros comuns e soluções

### `SSL: PEM lib` ao iniciar pagamento

**Causa:** `EFI_CERT_PATH` aponta para um `.p12` em vez de `.pem`, ou o `.pem` tem a ordem errada (chave antes do cert).

**Solução:** Execute `python fix_cert.py` e certifique-se de que `EFI_CERT_PATH=./certificado.pem`.

---

### `RemoteDisconnected` ou `ConnectionError`

**Causa:** `EFI_SANDBOX=false` com credenciais de homologação, tentando conectar no servidor de produção.

**Solução:** Verifique se o valor de `EFI_SANDBOX` está alinhado com as credenciais. Homologação → `true`. Produção → `false`.

---

### `webhook_invalido — URL respondeu com HTTP 404`

**Causa:** O servidor não está respondendo em `/webhook/efi` (a EFI bate nessa rota ao registrar).

**Solução:** Certifique-se de que `main.py` está em execução e que o endpoint `POST /webhook/efi` existe no `webhook.py`.

---

### `webhook_invalido — A autenticação de TLS mútuo não está configurada`

**Causa:** O header `x-skip-mtls-checking: true` não foi enviado no registro.

**Solução:** Confirme que `setup_webhook.py` inclui `headers = {"x-skip-mtls-checking": "true"}` na chamada `pix_config_webhook`.

---

### `webhook_invalido — URL respondeu com HTTP 502`

**Causa:** O servidor não está rodando ou o ngrok não está ativo quando `setup_webhook.py` é executado.

**Solução:** Inicie `python main.py` e confirme que o ngrok está ativo antes de registrar o webhook.

---

### `UnauthorizedError` ao criar cobrança Pix

**Causa:** Client ID ou Secret incorretos, ou ambiente errado (`EFI_SANDBOX`).

**Solução:** O SDK EFI retorna objetos de erro em vez de levantar exceções. O código verifica `isinstance(response, dict)` — se não for dict, as credenciais são inválidas. Verifique o `.env`.

---

### Pagamento confirmado no banco mas mensagem não chegou no Telegram

**Causa 1:** Webhook não registrado (ou registrou com URL diferente da atual).

**Solução:** Rodar `setup_webhook.py` novamente com a URL correta e ativa.

**Causa 2:** Ngrok URL mudou (ngrok free gera nova URL a cada reinício).

**Solução:** Sempre atualizar `WEBHOOK_BASE_URL` e re-registrar o webhook após reiniciar o ngrok. Em produção, use Railway ou outro serviço com URL fixa.

---

## Referências

- [Documentação oficial EFI Bank — API Pix](https://dev.efipay.com.br/docs/api-pix/credenciais)
- [SDK efipay no PyPI](https://pypi.org/project/efipay/)
- [Repositório SDK efipay](https://github.com/efipay/sdk-python-apis-efi)

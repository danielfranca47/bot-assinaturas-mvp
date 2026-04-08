# SPEC: Migração de Gateway — Mercado Pago → EFI Bank (Gerencianet)

**Data:** 2026-04-08  
**Objetivo:** Substituir completamente o Mercado Pago pelo EFI Bank como gateway de pagamento Pix, mantendo o mesmo fluxo de negócio e a mesma interface do bot para o usuário final.

---

## Pendências identificadas no que já foi feito

Antes de iniciar a implementação, dois itens precisam ser resolvidos:

**Pendência 1 — Certificado .p12 ausente do projeto**  
O certificado foi baixado, mas o arquivo `.p12` não está no diretório do projeto. Deve ser copiado manualmente para `bot-assinaturas-mvp/` com o nome `certificado.p12` antes de prosseguir.

**Pendência 2 — `config.py` ainda exige `MP_ACCESS_TOKEN`**  
O `.env.example` já não documenta a variável, mas `config.py` ainda chama `_require("MP_ACCESS_TOKEN")`. Enquanto isso não for resolvido na Etapa 1, o projeto não inicializa sem a variável do MP.

---

## Visão geral das mudanças

| Arquivo | Ação |
|---|---|
| `config.py` | Substituir `MP_ACCESS_TOKEN` pelas 5 variáveis EFI |
| `payments.py` | Reescrever — remover SDK MP, implementar SDK EFI |
| `webhook.py` | Reescrever — novo endpoint, novo formato de payload |
| `database.py` | Renomear coluna `mp_payment_id` → `efi_txid` |
| `bot.py` | Atualizar chamada de `update_mp_payment_id` |
| `main.py` | Nenhuma mudança necessária |
| `requirements.txt` | Verificar que `mercadopago` não está listado |
| `.env.example` | Finalizar documentação das variáveis EFI |
| `certificado.p12` | Adicionar ao projeto (arquivo binário) |
| `setup_webhook.py` | Criar — script avulso para registrar webhook na EFI |

---

## Etapa 1 — Configuração de variáveis (`config.py` e `.env.example`)

### O que será alterado

Remover a dependência de `MP_ACCESS_TOKEN` e introduzir as 5 variáveis EFI. O `config.py` deve falhar com mensagem clara se qualquer variável obrigatória estiver ausente.

### Arquivo modificado: `config.py`

- Remover: `MP_ACCESS_TOKEN = _require("MP_ACCESS_TOKEN")`
- Adicionar:
  ```python
  EFI_CLIENT_ID     = _require("EFI_CLIENT_ID")
  EFI_CLIENT_SECRET = _require("EFI_CLIENT_SECRET")
  EFI_PIX_KEY       = _require("EFI_PIX_KEY")
  EFI_CERT_PATH     = os.getenv("EFI_CERT_PATH", "./certificado.p12")
  EFI_SANDBOX       = os.getenv("EFI_SANDBOX", "false").lower() == "true"
  ```

### Arquivo modificado: `.env.example`

- Remover qualquer referência a `MP_ACCESS_TOKEN`
- Garantir que todas as 5 variáveis EFI estão documentadas com comentários explicativos
- Adicionar `ADMIN_TELEGRAM_ID` (atualmente ausente do `.env.example`)

### Critério de conclusão

`python -c "import config"` executa sem erro com as variáveis EFI preenchidas no `.env`. A ausência de qualquer variável EFI obrigatória lança `EnvironmentError` com nome da variável.

---

## Etapa 2 — Banco de dados (`database.py`)

### O que será alterado

A coluna `mp_payment_id` tem nome semanticamente acoplado ao Mercado Pago. Será renomeada para `efi_txid`, que é o identificador nativo do EFI Bank. As funções que fazem referência ao nome antigo também serão renomeadas.

### Arquivo modificado: `database.py`

**Schema:** Alterar o `CREATE TABLE` para usar `efi_txid` no lugar de `mp_payment_id`:

```sql
efi_txid TEXT UNIQUE,   -- txid da cobrança no EFI Bank
```

**Funções renomeadas:**
- `update_mp_payment_id(row_id, mp_payment_id)` → `update_efi_txid(row_id, efi_txid)`
- `mark_as_paid(mp_payment_id)` → `mark_as_paid(efi_txid)` (assinatura mantida, apenas o parâmetro interno muda)

**Migration:** O banco em disco (`payments.db`) tem a coluna com o nome antigo. Para o MVP, a solução é deletar `payments.db` antes da primeira execução após a migração — o `init_db()` recriará a tabela com o nome correto. Não há dados de produção a preservar.

### Critério de conclusão

`python -c "from database import init_db; init_db()"` cria o banco sem erros. A coluna `efi_txid` aparece em `.schema payments` no SQLite. As funções `update_efi_txid` e `mark_as_paid` estão exportadas e funcionais.

---

## Etapa 3 — Geração de cobrança Pix (`payments.py`)

### O que será alterado

Reescrever completamente o arquivo. O contrato externo da função `create_pix_payment` é mantido: recebe `(telegram_user_id, amount_cents, plan)` e retorna `(pix_copia_cola, txid)`. Apenas a implementação interna muda.

### Arquivo modificado: `payments.py`

- Remover: `import mercadopago` e `sdk = mercadopago.SDK(...)`
- Adicionar: `from efipay import EfiPay`
- Inicializar SDK EFI com as credenciais do `config.py`:
  ```python
  _efi_options = {
      "client_id": EFI_CLIENT_ID,
      "client_secret": EFI_CLIENT_SECRET,
      "sandbox": EFI_SANDBOX,
      "certificate": EFI_CERT_PATH,
  }
  ```

**Fluxo dentro de `create_pix_payment`:**

1. Chamar `pixCreateImmediateCharge` com:
   - `calendario.expiracao`: 1800 (30 minutos)
   - `valor.original`: valor em reais com 2 casas decimais (string, ex: `"29.90"`)
   - `chave`: `EFI_PIX_KEY`
   - `solicitacaoPagador`: label do plano (ex: `"Acesso mensal — Canal [Nome]"`)
   - `infoAdicionais`: `[{"nome": "telegram_user_id", "valor": str(telegram_user_id)}]`
   - **Não usar** `devedor` — não coletamos CPF no MVP

2. Extrair `txid` e o `loc.id` da resposta

3. Chamar `pixGenerateQrcode(params={"id": loc_id})` para obter o `qrcode` (copia e cola)

4. Retornar `(qrcode, txid)`

**Tratamento de erros:** Se qualquer chamada ao SDK levantar exceção, relançar como `RuntimeError` com mensagem descritiva (mesmo padrão do código MP atual).

### Critério de conclusão

Chamada manual a `create_pix_payment(123456789, 2990, "monthly")` retorna uma string Pix válida (começa com `00020126`) e um `txid` alfanumérico. Nenhum import do `mercadopago` permanece no arquivo.

---

## Etapa 4 — Recebimento de webhook (`webhook.py`)

### O que será alterado

Reescrever completamente o arquivo. O endpoint muda de `/webhook/mercadopago` para `/webhook/efi`. O formato do payload recebido é diferente do MP.

### Arquivo modificado: `webhook.py`

- Remover: `import mercadopago` e `sdk = mercadopago.SDK(...)`
- Adicionar: `from efipay import EfiPay` (para verificação opcional via API)
- Renomear rota: `@router.post("/webhook/efi")`

**Formato do payload EFI recebido:**
```json
{
  "pix": [
    {
      "endToEndId": "E...",
      "txid": "abc123...",
      "chave": "sua-chave-pix",
      "valor": "29.90",
      "horario": "2026-04-08T19:00:00.000-03:00"
    }
  ]
}
```

**Fluxo do handler:**

1. Checar se `"pix"` está no body — caso contrário, retornar `{"status": "ignored"}`
2. Iterar sobre `data["pix"]` (pode haver mais de um na mesma notificação)
3. Para cada item, extrair `txid`
4. Chamar `mark_as_paid(txid)` — se retornar `None`, pular (já processado)
5. Enviar mensagem ao membro com o link do canal
6. Enviar notificação ao admin (manter o mesmo formato atual)

**Verificação via API EFI (opcional mas recomendada):**  
Antes do `mark_as_paid`, chamar `pixDetailCharge(params={"txid": txid})` e confirmar que `status == "CONCLUIDA"`. Isso evita processar notificações forjadas. Em sandbox, pode-se pular esta etapa durante o desenvolvimento.

**Validação de origem da requisição:**  
Em produção, o EFI entrega webhooks via mTLS — o servidor recebe um certificado de cliente que pode ser validado. Para o MVP, é suficiente aceitar qualquer POST e depender da verificação de status via API.

### Critério de conclusão

Endpoint `/webhook/efi` responde `{"status": "ok"}` quando recebe payload EFI simulado com `txid` existente no banco com status `pending`. Mensagem é enviada ao usuário e ao admin. Nenhum import do `mercadopago` permanece no arquivo.

---

## Etapa 5 — Registro do webhook na EFI (`setup_webhook.py`)

### O que será alterado

O EFI Bank exige que a URL do webhook seja registrada explicitamente via API — diferente do MP, que aceita a `notification_url` diretamente na criação do pagamento. Esse registro é feito uma única vez por ambiente (sandbox ou produção).

### Arquivo criado: `setup_webhook.py`

Script avulso para rodar manualmente após o deploy ou quando a URL pública mudar:

```python
# Uso: python setup_webhook.py
from efipay import EfiPay
from config import EFI_CLIENT_ID, EFI_CLIENT_SECRET, EFI_CERT_PATH, EFI_SANDBOX, EFI_PIX_KEY, WEBHOOK_BASE_URL

efi = EfiPay({
    "client_id": EFI_CLIENT_ID,
    "client_secret": EFI_CLIENT_SECRET,
    "sandbox": EFI_SANDBOX,
    "certificate": EFI_CERT_PATH,
})

body = {"webhookUrl": f"{WEBHOOK_BASE_URL}/webhook/efi"}
response = efi.pix_config_webhook(params={"chave": EFI_PIX_KEY}, body=body)
print("Webhook registrado:", response)
```

**Quando rodar:** Sempre que `WEBHOOK_BASE_URL` mudar (novo deploy no Railway, novo túnel ngrok etc.).

### Critério de conclusão

Script executa sem erro e imprime confirmação de registro. Chamada `pixDetailWebhook(params={"chave": EFI_PIX_KEY})` confirma a URL registrada.

---

## Etapa 6 — Atualização dos consumidores (`bot.py`)

### O que será alterado

`bot.py` chama `update_mp_payment_id` (que será renomeada na Etapa 2). Única alteração necessária.

### Arquivo modificado: `bot.py`

- Linha de import: `from database import insert_pending, update_mp_payment_id` → `from database import insert_pending, update_efi_txid`
- Variável local: `mp_payment_id` → `efi_txid`
- Chamada: `update_mp_payment_id(row_id, mp_payment_id)` → `update_efi_txid(row_id, efi_txid)`
- Chamada ao `payments.py`: `pix_code, mp_payment_id = create_pix_payment(...)` → `pix_code, efi_txid = create_pix_payment(...)`

Nenhuma mudança na lógica ou na experiência do usuário.

### Critério de conclusão

`python -c "from bot import build_application"` importa sem erros. Nenhuma referência a `mp_payment_id` permanece no arquivo.

---

## Etapa 7 — Dependências (`requirements.txt`)

### O que será alterado

Verificar e limpar dependências.

- `mercadopago` **não estava listado** no `requirements.txt` (confirmado), mas o pacote pode estar instalado no `.venv`. Remover do ambiente com `pip uninstall mercadopago -y` após a migração.
- `efipay` já está listado ✓
- Nenhuma adição necessária.

### Critério de conclusão

`pip freeze | grep mercadopago` retorna vazio. `python -c "import efipay"` importa sem erro.

---

## Etapa 8 — Validação end-to-end (sandbox)

### O que será feito

Teste completo do fluxo com credenciais sandbox da EFI:

1. Garantir que `EFI_SANDBOX=true` no `.env`
2. Rodar `python setup_webhook.py` com URL ngrok como `WEBHOOK_BASE_URL`
3. No Telegram, enviar `/assinar` → escolher plano → copiar código Pix
4. Simular pagamento no painel sandbox da EFI (ou via API EFI)
5. Confirmar que webhook chega em `/webhook/efi`
6. Confirmar que usuário recebe mensagem com link do canal
7. Confirmar que admin recebe notificação
8. Verificar no banco que o registro tem `status = 'paid'` e `efi_txid` preenchido

### Critério de conclusão

Fluxo completo executado sem erros manuais. Logs mostram webhook recebido e processado. Banco atualizado corretamente.

---

## Etapa 9 — Deploy em produção (Railway)

### O que será feito

1. Remover `MP_ACCESS_TOKEN` das variáveis de ambiente no painel Railway
2. Adicionar as 5 variáveis EFI no painel Railway
3. Fazer upload do `certificado.p12` — por ser binário, deve ser incluído no repositório (não é um segredo público; a segurança real está no Client Secret) **ou** codificado em base64 como variável de ambiente
4. Trocar `EFI_SANDBOX=false` no Railway
5. Fazer `git push` para disparar novo deploy
6. Rodar `python setup_webhook.py` com a URL pública do Railway
7. Repetir teste end-to-end com pagamento real de valor mínimo

### Critério de conclusão

Bot em produção processa pagamento Pix real via EFI. Nenhuma referência ao Mercado Pago permanece ativa no sistema.

---

## Referências

- [EFI Bank — Documentação API Pix](https://dev.efipay.com.br/docs/api-pix/cobrancas-imediatas)
- [efipay SDK Python — GitHub](https://github.com/efipay/sdk-python-apis-efi)
- Método de criação de cobrança: `pixCreateImmediateCharge`
- Método de QR Code: `pixGenerateQrcode`
- Método de registro de webhook: `pixConfigWebhook`
- Método de consulta de cobrança: `pixDetailCharge`

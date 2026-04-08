# Plano: Split de Pagamento Pix — EFI Bank

## O que é

Split de pagamento é uma funcionalidade da API Pix da EFI Bank que permite dividir automaticamente o valor recebido em uma cobrança entre múltiplas contas EFI. No contexto do autodigital-pay, isso viabiliza o repasse automático de comissões — por exemplo, a plataforma retém uma parte do pagamento e repassa o restante para o criador de conteúdo, sem intervenção manual.

---

## Restrições importantes

| Restrição | Detalhe |
|---|---|
| Contas EFI apenas | O split só funciona entre contas da EFI Bank |
| Máximo 20 destinatários | Limite por configuração de split |
| Sem devolução | Cobranças já repassadas não podem ser estornadas |
| Sem auto-repasse | Não é possível fazer split para a própria conta originadora |
| Soma deve ser 100% | Se usar tipo `porcentagem`, `minhaParte` + todos os `repasses` = 100% |

---

## Como funciona (fluxo)

```
1. Criar uma "split config" → define percentuais/valores fixos entre as contas
2. Criar a cobrança Pix normalmente (cob ou cobv)
3. Vincular o txid da cobrança ao splitConfigId
4. Cliente paga → EFI distribui automaticamente conforme a config
```

---

## Endpoints da API

### Split Config

| Ação | Método | Endpoint |
|---|---|---|
| Criar (ID automático) | `POST` | `/v2/gn/split/config` |
| Criar/atualizar (ID próprio) | `PUT` | `/v2/gn/split/config/:id` |
| Consultar config | `GET` | `/v2/gn/split/config/:id` |

### Vincular Split a Cobrança Imediata (COB)

| Ação | Método | Endpoint |
|---|---|---|
| Vincular | `PUT` | `/v2/gn/split/cob/:txid/vinculo/:splitConfigId` |
| Consultar vínculo | `GET` | `/v2/gn/split/cob/:txid` |
| Desvincular | `DELETE` | `/v2/gn/split/cob/:txid/vinculo` |

### Vincular Split a Cobrança com Vencimento (COBV)

| Ação | Método | Endpoint |
|---|---|---|
| Vincular | `PUT` | `/v2/gn/split/cobv/:txid/vinculo/:splitConfigId` |
| Consultar vínculo | `GET` | `/v2/gn/split/cobv/:txid` |
| Desvincular | `DELETE` | `/v2/gn/split/cobv/:txid/vinculo` |

---

## Escopos OAuth necessários

```
gn.split.write   → criar e modificar split configs, vincular cobranças
gn.split.read    → consultar split configs e vínculos
cob.write        → criar cobranças (já necessário no fluxo atual)
```

---

## Estrutura do payload: criar split config

```json
POST /v2/gn/split/config

{
  "descricao": "Comissão autodigital-pay - plano mensal",
  "lancamento": {
    "imediato": true
  },
  "split": {
    "divisaoTarifa": "assumir_total",
    "minhaParte": {
      "tipo": "porcentagem",
      "valor": "20.00"
    },
    "repasses": [
      {
        "tipo": "porcentagem",
        "valor": "80.00",
        "favorecido": {
          "cpf": "12345678909",
          "conta": "1234567"
        }
      }
    ]
  }
}
```

### Campos explicados

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `descricao` | string | Sim | Nome da configuração (identificação interna) |
| `lancamento.imediato` | boolean | Sim | Deve ser sempre `true` |
| `split.divisaoTarifa` | string | Sim | `"assumir_total"` — quem criou o split paga todas as tarifas |
| `split.minhaParte.tipo` | string | Sim | `"porcentagem"` ou `"fixo"` |
| `split.minhaParte.valor` | string | Sim | Valor numérico como string (ex: `"20.00"`) |
| `split.repasses[].tipo` | string | Sim | `"porcentagem"` ou `"fixo"` |
| `split.repasses[].valor` | string | Sim | Valor a repassar |
| `split.repasses[].favorecido.cpf` | string | Sim | CPF do destinatário |
| `split.repasses[].favorecido.conta` | string | Sim | Número da conta EFI do destinatário |

### Resposta de sucesso

```json
{
  "id": "abc123splitConfigId",
  "status": "ATIVA",
  "descricao": "Comissão autodigital-pay - plano mensal",
  ...
}
```

---

## Vincular split a uma cobrança

```
PUT /v2/gn/split/cob/:txid/vinculo/:splitConfigId
```

- Sem corpo na requisição — tudo vai pela URL
- Resposta de sucesso: **HTTP 204** (sem conteúdo)
- A cobrança Pix deve existir previamente com o `txid` informado

---

## Tipos de distribuição

### Porcentagem (`tipo: "porcentagem"`)

- `minhaParte` + soma de todos os `repasses` deve ser exatamente `100.00`
- Exemplo: plataforma fica com 20%, criadora recebe 80%

### Fixo (`tipo: "fixo"`)

- Define valores absolutos em reais
- A soma dos fixos não pode ultrapassar o valor da cobrança
- Útil quando a comissão é um valor fixo independente do plano

---

## Modelo de implementação para o projeto

### Variáveis de ambiente a adicionar

```env
SPLIT_ENABLED=false                  # feature flag — ativa/desativa split
SPLIT_CONFIG_ID=                     # ID da split config criada na EFI (reusar entre cobranças)
SPLIT_CREATOR_ACCOUNT=               # número da conta EFI do criador de conteúdo
SPLIT_CREATOR_CPF=                   # CPF do criador (exigido pela API)
SPLIT_PLATFORM_PCT=20.00             # percentual da plataforma (autodigital-pay)
SPLIT_CREATOR_PCT=80.00              # percentual do criador
```

### Fluxo de código (pseudocódigo)

```python
# 1. Na inicialização (ou configuração do cliente), criar a split config UMA vez
# e salvar o splitConfigId gerado

# 2. Em payments.py — ao criar a cobrança:
txid = gerar_txid()
criar_cobrança_pix(txid, valor, ...)

if SPLIT_ENABLED:
    vincular_split(txid, SPLIT_CONFIG_ID)
    # PUT /v2/gn/split/cob/{txid}/vinculo/{SPLIT_CONFIG_ID}
```

### Onde alterar no projeto atual

| Arquivo | Alteração |
|---|---|
| `payments.py` | Adicionar chamada para vincular split após criar cobrança |
| `config.py` | Ler novas variáveis `SPLIT_*` do `.env` |
| `.env.example` | Documentar novas variáveis |
| `database.py` | Opcional: salvar `split_config_id` na tabela `payments` |

---

## Considerações para produção

- A split config pode (e deve) ser **reutilizada** entre cobranças — criar uma vez por configuração de comissão, não a cada pagamento
- O `splitConfigId` pode ser gerado pela EFI ou definido por nós com `PUT /v2/gn/split/config/:id` (mais simples para gerenciar)
- O campo `divisaoTarifa: "assumir_total"` faz a plataforma (nossa conta EFI) absorver as tarifas — isso deve ser considerado na precificação
- A feature flag `SPLIT_ENABLED` permite ativar o split por cliente sem alterar código

---

## Limitações do MVP atual

O split **não está implementado** ainda. Este documento é o plano de referência. A implementação está fora do escopo do MVP inicial e só deve ser ativada quando:

1. A criadora de conteúdo tiver conta EFI Bank ativa
2. A plataforma tiver sua própria conta EFI Bank para receber a comissão
3. CPF e número de conta do criador estiverem disponíveis para configuração

---

## Referências

- Documentação oficial: https://dev.efipay.com.br/docs/api-pix/split-de-pagamento-pix
- Escopos OAuth EFI: https://dev.efipay.com.br/docs/api-pix/credenciais

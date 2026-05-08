# AECO Consolidador

Automação da consolidação mensal do Extrato AECO Anual.

Ingere os 4 extratos brutos (Sicoob xlsx, BS2 csv, Conta Simples xlsx, C6 xlsx/csv),
classifica linha-a-linha em 4 dimensões gerenciais (Descrição, Observações, Fluxo de
Caixa, Empresa) usando regras determinísticas + LLM como fallback, e exporta um xlsx
com 5 abas (AECO/SEC/TECH/Conta Simples/C6) + Validação prontas para colar no master.

**Não modifica o `Extrato AECO - Anual.xlsx` original.**

## Setup em uma máquina nova

**Pré-requisitos:** Python 3.10+ (ideal 3.12) e git. No Windows, marcar "Add Python to PATH" durante a instalação.

### Linux / macOS / WSL

```bash
git clone <repo-url> aeco-consolidador
cd aeco-consolidador

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env   # opcional: preencher ANTHROPIC_API_KEY pra ativar o LLM
```

> Se `python3 -m venv` reclamar de pacote ausente: `sudo apt install python3-venv` (Debian/Ubuntu).
> Alternativa zero-config: `uv venv && uv pip install -r requirements.txt`.

### Windows (PowerShell)

```powershell
git clone <repo-url> aeco-consolidador
cd aeco-consolidador

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt

copy .env.example .env   # opcional: preencher ANTHROPIC_API_KEY pra ativar o LLM
```

> Se `Activate.ps1` der erro de execution policy, rode uma vez:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`
> e responda `Y`. Em `cmd` use `.\.venv\Scripts\activate.bat`.

### Configurar a chave da API (opcional)

Sem chave, a app funciona em modo "rules-only" (regras determinísticas via dicionário). Com chave, casos vermelhos/ambíguos podem ser refinados via Claude.

- Linux/macOS: `export ANTHROPIC_API_KEY=sk-ant-...` (ou colocar em `.env`)
- Windows PowerShell: `$env:ANTHROPIC_API_KEY = "sk-ant-..."`

## Validação inicial — rodar testes

Antes de usar pela primeira vez, confirme que tudo roda:

```bash
pytest tests/ -v
```

Esperado: **38 passed**. Os testes leem fixtures em `data/fixtures/` com nomes canônicos (`sicoob_032026.xlsx`, `bs2_032026.csv`, `conta_simples_032026.xlsx`). Se você for substituir os fixtures de exemplo por dados reais de outro mês, mantenha esses nomes (ou crie cópias com esses nomes).

## Workflow

1. **Construir o dicionário a partir do master** (uma vez, e depois quando quiser incorporar correções):

   ```bash
   python scripts/build_dictionary.py "data/fixtures/Extrato AECO - Anual.xlsx" data/dictionary.json
   ```

   Ajuste o caminho do master se ele estiver em outro lugar. O dicionário gerado fica em `data/dictionary.json` e é o que alimenta o classifier.

2. **Rodar o app Streamlit** (uso normal da contadora):

   ```bash
   streamlit run app.py
   ```

   Faz upload dos 4 extratos, revisa amarelos+vermelhos no editor, resolve, e baixa o xlsx consolidado. **O extrato C6 é opcional** — se você não anexar, a app processa só Sicoob/BS2/Conta Simples.

3. **Ou rodar a CLI v0** (sem UI, útil pra validação):

   ```bash
   python scripts/run_v0_cli.py \
       --sicoob "data/fixtures/sicoob_032026.xlsx" \
       --bs2 "data/fixtures/bs2_032026.csv" \
       --cs "data/fixtures/conta_simples_032026.xlsx" \
       --master "data/fixtures/Extrato AECO - Anual.xlsx" \
       --out out_032026.xlsx \
       --report report.txt
   ```

## Notas e troubleshooting

- **Extrato C6 vem criptografado** pelo banco (.xls OLE2 com `EncryptedPackage`). Antes de usar: abrir no Excel, digitar a senha, remover criptografia (`Arquivo → Informações → Proteger pasta de trabalho → Criptografar com senha → apagar`), e salvar como `.xlsx` desprotegido. Sem isso o parser falha — é a única razão pela qual o C6 ainda está como stub.
- **`python: command not found` no Linux**: use `python3` em vez de `python`, ou crie um alias.
- **Windows, símbolos especiais nos nomes de arquivos**: o WSL preserva NFD/NFC de Unicode de forma diferente do NTFS — se for mover fixtures entre os dois, prefira **copiar** em vez de symlink, ou renomeie pra ASCII puro.
- **`.venv/` no `.gitignore`**: já está, mas se você criou um nome diferente (ex.: `.venv-win`), adicione manualmente.

## Status do MVP

- Parsers Sicoob, BS2, Conta Simples — implementados
- Parser C6 — **stub**, precisa de 1 arquivo C6 representativo pra implementar
- Dictionary builder com 3 modos (exact / value_brackets / ambiguous)
- Classifier híbrido: regras + fuzzy/prefix match + LLM fallback (Sonnet 4.6 com prompt caching)
- Política "REVISAR EXTERNO" pra ambíguos (não chama LLM, deixa pra contadora)
- Streamlit UI com data_editor (Selectbox em fluxo/empresa, TextColumn em descr/obs com confirmação)
- Validação de saldos + duplicatas vs master
- Exporter com roteamento por empresa+source, header `Entrada` no C6
- Feedback loop (`data/feedback.jsonl`)

Validação contra mar/2026 (rule-only, 104 transações):
- 62 verdes / 15 amarelas / 27 vermelhas
- Saldo Sicoob: OK (R$ 20.369,68)
- Saldo BS2: discrepância de R$ 178,31 no extrato bruto (sinalizado)
- Acurácia vs ground truth do master: ~85% empresa, ~85% fluxo, ~88% descrição, ~80% observações

## Estrutura

```
aeco/                       # core
  schema.py                 # Transaction dataclass
  normalize.py              # parse_pt_money, normalize_text, normalize_key, normalize_tipo
  parsers/                  # 1 módulo por banco
  classifier/               # rules.py + llm.py + prompts.py
  dictionary.py             # build/load/save
  validate.py               # check_saldos + duplicates
  exporter.py               # to_xlsx
  feedback.py               # append_corrections
app.py                      # Streamlit
scripts/                    # build_dictionary, run_v0_cli
tests/                      # 38 testes (parsers, normalize, rules, validate, exporter)
data/                       # dictionary.json, feedback.jsonl, fixtures/
```

## Testes

```bash
pytest tests/ -v
```

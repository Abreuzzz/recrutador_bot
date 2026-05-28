# Recruitment Telegram Bot com Ollama Local

Bot local em Python para apoiar triagem de candidatos via Telegram. Ele permite cadastrar vagas, adicionar candidatos por texto ou arquivos PDF/DOCX/TXT, analisar aderência com IA local via Ollama e salvar histórico completo em SQLite.

O MVP não faz scraping, não aborda candidatos e não envia mensagens externas. É uma ferramenta interna de apoio à decisão humana em Recrutamento e Seleção.

## Arquitetura

- `app/bot`: handlers, mensagens, botões e controle de acesso do Telegram.
- `app/database`: conexão SQLite, criação automática de tabelas e repositório.
- `app/files`: armazenamento local e extração de PDF, DOCX e TXT.
- `app/llm`: cliente Ollama, prompts versionados e schemas Pydantic.
- `app/services`: regras de vaga, candidato, análise e histórico.
- `examples`: dados fictícios para testes manuais.
- `tests`: suíte Pytest do núcleo do MVP.

## Requisitos

- Python 3.11+
- Telegram Bot Token
- Ollama instalado e rodando localmente
- Modelo `qwen2.5:7b`

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
```

## Configuração

Crie um arquivo `.env` a partir de `.env.example`:

```env
TELEGRAM_BOT_TOKEN=seu_token
AUTHORIZED_TELEGRAM_USER_IDS=123456789,987654321
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
DATABASE_PATH=./data/recruitment_bot.db
UPLOADS_DIR=./data/uploads
LOG_FILE=./logs/app.log
MAX_CANDIDATES_PER_ANALYSIS=5
MAX_FILE_SIZE_MB=20
LOG_LEVEL=INFO
```

`AUTHORIZED_TELEGRAM_USER_IDS` aceita múltiplos IDs separados por vírgula. Usuários fora dessa lista recebem `Acesso não autorizado.`

## Criar Bot no Telegram

1. Abra o Telegram e fale com `@BotFather`.
2. Use `/newbot`.
3. Escolha nome e username.
4. Copie o token gerado para `TELEGRAM_BOT_TOKEN`.

Para obter seu `telegram_user_id`, fale com bots como `@userinfobot` ou consulte o ID por outro método de confiança.

## Ollama

```bash
ollama pull qwen2.5:7b
ollama serve
```

## Execução

```bash
python -m app.main
```

Na primeira execução, o SQLite é criado automaticamente em `data/recruitment_bot.db`, os uploads ficam em `data/uploads/` e logs em `logs/app.log`.

## Comandos

- `/start`
- `/help`
- `/vaga`
- `/candidato`
- `/listar`
- `/analisar`
- `/limpar`
- `/historico`
- `/resultado ID`
- `/vagas`
- `/selecionar ID`
- `/remover_candidato ID`
- `/editar_candidato ID`
- `/remover_vaga ID`
- `/reprocessar_candidato ID`
- `/reprocessar_falhas`

## Exemplos de uso

Cadastrar vaga:

```text
/vaga Título: Analista de RH...
```

Cadastrar candidato:

```text
/candidato Nome: João Silva...
```

Cadastrar múltiplos candidatos:

```text
Nome: João Silva
Experiência...

---

Nome: Maria Santos
Experiência...
```

Também é possível enviar arquivos PDF, DOCX ou TXT como documento no Telegram. PDFs escaneados ou imagens não fazem parte do MVP.

## Testes e lint

```bash
pytest
```

```bash
ruff check .
ruff format .
```

## Etapas implementadas

- Estrutura de projeto com `pyproject.toml`, `.env.example`, logs e exemplos.
- SQLite com criação automática de tabelas.
- Controle de acesso por Telegram ID.
- Cadastro, seleção, listagem e remoção lógica de vagas.
- Cadastro, edição, remoção lógica, duplicidade e reprocessamento de candidatos.
- Upload local de arquivos e extração TXT/DOCX/PDF.
- Integração com Ollama local, prompts versionados, retry e validação Pydantic.
- Análise de aderência com score, classificação, prioridade, parecer e ranking.
- Histórico de análises e recuperação por `/resultado ID`.
- Testes automatizados do núcleo do MVP.

## Limitações do MVP

- Não faz OCR de PDF escaneado.
- Não processa imagens, fotos ou prints.
- Não integra LinkedIn, ATS, WhatsApp ou e-mail.
- Não faz scraping nem automação de navegador.
- Não há dashboard web.
- A qualidade da análise depende do texto fornecido e do modelo local configurado.

## Próximos passos sugeridos

- Adicionar camada `CandidateSourceProvider` para fontes futuras aprovadas.
- Criar exportação de ranking.
- Adicionar migrações versionadas quando o schema evoluir.
- Melhorar observabilidade com IDs de correlação por análise.
- Adicionar testes integrados com um Ollama real em ambiente controlado.

# Preparação do Projeto para GitHub

Este documento descreve as etapas necessárias para preparar o projeto para upload no GitHub, removendo dados sensíveis e personalizados.

## Status Atual

- Data de criação: 08/03/2026
- Status: Planejamento em andamento

## Checklist de Preparação

### Etapa 1: Limpeza de Arquivos Sensíveis

- [ ] Remover `.env` (contém API keys reais)
- [ ] Remover diretório `.terminal_agent/` inteiro (contém config.json com API keys e rag_index.json com dados indexados)
- [ ] Remover `Manual_Motokao.md` (documento pessoal específico do usuário)
- [ ] Remover `.tmp_fastmcp_497.html` (arquivo temporário)
- [ ] Remover `.vscode/launch.json` (configuração de IDE específica do usuário)

### Etapa 2: Verificação do .gitignore

- [ ] Verificar se `.terminal_agent/` está no `.gitignore` (já está ✓)
- [ ] Verificar se `.env` está no `.gitignore` (já está ✓)
- [ ] Verificar se `.venv/` e `.venv312/` estão no `.gitignore` (já está ✓)
- [ ] Verificar se `*.log` está no `.gitignore` (já está ✓)
- [ ] Verificar se `__pycache__/` está no `.gitignore` (já está ✓)

### Etapa 3: Atualização de Documentação

- [ ] Atualizar README.md para remover referências pessoais
- [ ] Verificar se há menções a arquivos específicos do usuário no README
- [ ] Garantir que `.env.example` está completo e descreve todas as variáveis necessárias
- [ ] Criar DOCUMENTATION.md ou CONTRIBUTING.md se necessário

### Etapa 4: Verificação de Configurações

- [ ] Verificar se há configurações hardcoded nos scripts PowerShell
- [ ] Verificar se há caminhos absolutos que devem ser relativos
- [ ] Verificar se os scripts funcionam em diferentes sistemas operacionais (principalmente Windows vs Linux/Mac)

### Etapa 5: Verificação de Código Fonte

- [ ] Verificar se há API keys ou credenciais hardcoded no código fonte
- [ ] Verificar se há informações pessoais em comentários
- [ ] Verificar se há URLs específicas do usuário no código
- [ ] Garantir que o código segue boas práticas de segurança

### Etapa 6: Testes

- [ ] Testar instalação do zero em um ambiente limpo
- [ ] Testar scripts de inicialização (run.ps1, iniciar.ps1, iniciar.cmd)
- [ ] Testar scripts de finalização (stop.ps1, finalizar.ps1, finalizar.cmd)
- [ ] Verificar se o projeto funciona corretamente após a limpeza
- [ ] Testar funcionalidades principais (chat, RAG, comandos)

### Etapa 7: Preparação para Git

- [ ] Remover todos os arquivos listados na Etapa 1
- [ ] Verificar se há arquivos não rastreados que deveriam ser ignorados
- [ ] Criar um commit inicial limpo
- [ ] Não incluir dados de testes ou sessões anteriores

### Etapa 8: Configuração do Repositório

- [ ] Criar LICENSE.md (se desejado)
- [ ] Adicionar CONTRIBUTING.md com instruções para contribuidores
- [ ] Configurar GitHub Actions para CI/CD (se desejado)
- [ ] Criar .github/ISSUE_TEMPLATE/ se necessário
- [ ] Criar .github/PULL_REQUEST_TEMPLATE.md se necessário

## Observações Importantes

### Arquivos SENSÍVEIS a Remover

1. `.env` - Contém `OPENAI_API_KEY` real
2. `.terminal_agent/config.json` - Contém API key e configurações personalizadas
3. `.terminal_agent/rag_index.json` - Contém dados indexados do usuário
4. `.terminal_agent/traces.jsonl` - Logs de tracing (se existir)

### Arquivos PESSOAIS a Remover

1. `Manual_Motokao.md` - Documento específico sobre empresa de motos
2. `.vscode/launch.json` - Configuração de IDE específica
3. `.tmp_fastmcp_497.html` - Arquivo temporário

### Diretórios a Ignorar

1. `.venv/` - Ambiente virtual Python
2. `.venv312/` - Ambiente virtual Python específico
3. `__pycache__/` - Cache de compilação Python
4. `.pytest_cache/` - Cache de testes
5. `.terminal_agent/` - Dados de runtime do aplicativo
6. `.ruff_cache/` - Cache de linting
7. `.mypy_cache/` - Cache de type checking

### Scripts a Manter

- `run.ps1` - Script principal de execução
- `stop.ps1` - Script de parada
- `iniciar.ps1` - Script alternativo em português
- `finalizar.ps1` - Script alternativo de parada em português
- `iniciar.cmd` - Script batch para execução
- `finalizar.cmd` - Script batch para parada

### Documentação a Manter

- `README.md` - Documentação principal (após atualização)
- `AGENTS.md` - Instruções para agentes de desenvolvimento
- `.env.example` - Exemplo de configuração

### Código Fonte a Manter

- Todo o diretório `src/` com o código fonte
- Todo o diretório `plugins/` com exemplos de plugins
- Todo o diretório `tests/` com testes
- `pyproject.toml` - Dependências do projeto
- `.gitignore` - Configuração do Git

## Passos de Execução

### Passo 1: Backup (OPCIONAL)

```bash
# Criar backup dos arquivos que serão removidos
mkdir .backup_personal
cp .env .backup_personal/
cp -r .terminal_agent .backup_personal/
cp Manual_Motokao.md .backup_personal/
cp .vscode/launch.json .backup_personal/
```

### Passo 2: Remoção de Arquivos Sensíveis e Pessoais

```powershell
# Remover arquivo .env
Remove-Item .env -Force

# Remover diretório .terminal_agent
Remove-Item .terminal_agent -Recurse -Force

# Remover documento pessoal
Remove-Item Manual_Motokao.md -Force

# Remover arquivos temporários
Remove-Item .tmp_fastmcp_497.html -Force

# Remover configuração de VSCode específica
Remove-Item .vscode/launch.json -Force
```

### Passo 3: Atualização do README.md

- Remover referências a documentos pessoais
- Garantir que todas as instruções de instalação estão corretas
- Adicionar aviso sobre não commitar `.env`
- Adicionar instruções de configuração inicial

### Passo 4: Verificação do Código

```bash
# Buscar por possíveis credenciais no código
grep -r "sk-" src/
grep -r "api_key" src/
grep -r "password" src/

# Buscar por informações pessoais
grep -r "Motokao" src/
grep -r "gabri" src/
```

### Passo 5: Teste de Instalação Limpa

```powershell
# Testar instalação do zero
py -3.12 -m venv .venv_test
.venv_test\Scripts\python.exe -m pip install -e .
.venv_test\Scripts\python.exe -m langgraph_terminal.main
```

### Passo 6: Inicialização do Git

```bash
# Inicializar repositório (se ainda não estiver)
git init

# Adicionar arquivos
git add .

# Verificar o que será commitado
git status

# Criar commit inicial
git commit -m "Initial commit: LangGraph Terminal UI"
```

## Perguntas para o Usuário

1. Deseja adicionar uma licença ao projeto? (MIT, Apache 2.0, etc.)
2. Deseja configurar GitHub Actions para CI/CD?
3. Deseja adicionar templates de Issues e Pull Requests?
4. Deseja manter os scripts em português (iniciar.ps1, finalizar.ps1) ou apenas em inglês (run.ps1, stop.ps1)?
5. Deseja adicionar uma seção de "Contribuindo" no README.md?
6. Há algum outro arquivo específico que você quer manter ou remover?

## Verificação Final

Antes de fazer o upload, verificar:

- [ ] Não há arquivos `.env` ou `.env.local` no repositório
- [ ] Não há arquivos com credenciais ou API keys
- [ ] Não há documentos pessoais ou informações sensíveis
- [ ] O `.gitignore` está completo
- [ ] O README.md está atualizado
- [ ] Os scripts funcionam corretamente
- [ ] O projeto pode ser instalado e configurado facilmente por qualquer pessoa
- [ ] Todas as dependências estão declaradas no `pyproject.toml`
- [ ] Os testes passam (se existirem)

## Próximos Passos Após Upload

1. Criar repositório no GitHub
2. Adicionar descrição e tags apropriadas
3. Configurar branch protection (main)
4. Adicionar collaborators se necessário
5. Configurar webhooks ou integrações se necessário
6. Publicar anúncio sobre o projeto (se desejado)

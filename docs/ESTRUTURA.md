# Mapa do projeto

## Pastas

| Caminho | Responsabilidade |
| --- | --- |
| `app/` | Aplicação Python, serviços locais, adaptadores e instalação |
| `app/web/` | Interface, renderização do mundo e tutorial integrado |
| `app/web/brand/` | Logo, ícone e recursos da identidade visual |
| `tests/` | Testes Python e JavaScript |
| `docs/` | Guias e mídia da demonstração |
| `examples/` | Exemplos pequenos para experimentar ferramentas |
| `.github/workflows/` | Verificação automática e compilação Windows |
| `.github/ISSUE_TEMPLATE/` | Formulários de relatos e sugestões |

## Backend

| Arquivo em `app/` | Responsabilidade |
| --- | --- |
| `server.py` | Inicialização, persistência e serviços compartilhados |
| `http_api.py` | Rotas do servidor local |
| `task_engine.py` | Contexto, execução e revisão de tarefas |
| `delegation.py` | Validação das delegações do gerente |
| `staff_service.py` | Regras de cadastro e retirada da equipe |
| `runtime_context.py` | Acesso ao estado compartilhado da aplicação |
| `integrations.py` | Integração das ferramentas com a execução |
| `text_budget.py` | Fila compartilhada de chamadas de IA |
| `desktop.py` | Janela nativa do aplicativo |
| `build_windows.py` | Compilação e montagem da distribuição Windows |

Os arquivos `.bat` da raiz são pontos de entrada para o usuário e encaminham para `app/`. Não são cópias descartáveis. Nomes legados usados na instalação e atualização também são mantidos por compatibilidade.

## Dados e distribuição

`dados/`, configurações privadas e caches são criados localmente e ficam fora do Git. O caminho efetivo dos dados depende de como o aplicativo é iniciado; preserve os dados existentes ao atualizar.

`empacotar.py` seleciona os arquivos distribuíveis e mantém a estrutura dentro da pasta `EscritorIA/` no ZIP. O instalador Windows é gerado pelo workflow separado. Documentos históricos e arquivos de execução pessoais não pertencem ao pacote de fontes.

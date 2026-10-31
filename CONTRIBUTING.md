# Contribuir com o EscritorIA

## Preparar o ambiente

Use Python 3.10 ou superior e Node.js 22 para os testes da interface. Na raiz do repositório:

```bash
python -m venv .venv
```

No PowerShell, ative com `.venv\Scripts\Activate.ps1`; no Linux ou macOS, use `source .venv/bin/activate`. Depois:

```bash
python -m pip install -r requirements-dev.txt
python app/server.py
```

As integrações opcionais têm dependências próprias, descritas em [Integrações](docs/INTEGRACOES.md). Nenhuma chave real é necessária para executar os testes automatizados.

## Onde alterar

Consulte o [mapa do projeto](docs/ESTRUTURA.md). Preserve os caminhos de entrada e os nomes de compatibilidade usados pelos atalhos, instalador e atualizador.

Crie uma branch para cada mudança. Descreva o problema, o comportamento esperado e como conferir o resultado. Inclua testes quando a mudança afeta regras, persistência ou integrações.

## Verificar antes de enviar

Execute na raiz:

```bash
python -m ruff format app tests empacotar.py
python -m ruff check app tests empacotar.py
python -m unittest discover -s tests
node --test tests/*.test.cjs
```

No PowerShell, o último comando pode ser substituído por:

```powershell
node --test (Get-ChildItem tests/*.test.cjs).FullName
```

Para mudanças visuais, confira a interface no aplicativo e descreva o que foi validado. Os testes com respostas simuladas não substituem uma verificação com o provedor real quando a integração muda.

## Arquivos locais

Não versione `dados/`, bancos, chaves, `.env`, logs pessoais, ambientes virtuais ou executáveis gerados. Configure as credenciais pela interface local. Antes de enviar, confira `git status` e `git diff --cached`.

## Distribuição

As instruções para gerar instalador, publicar uma versão e preservar os dados estão em [Windows](docs/WINDOWS.md). O script `empacotar.py` gera um ZIP dos fontes; ele não compila o EXE.

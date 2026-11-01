# Aplicativo e release Windows

## Compilar no GitHub Actions

1. No [repositório EscritorIA](https://github.com/LucasNobreS/EscritorIA), confira se as alterações desejadas já estão na branch que será compilada. Para uma cópia própria, envie os fontes, incluindo `.github/` e `.gitignore`, não apenas o ZIP.
2. Abra **Actions → Gerar instalador Windows → Run workflow**. A execução manual gera um artefato para baixar; não publica uma release.
3. Para publicar, crie a tag `v0.45.0` no mesmo commit. A versão da tag deve coincidir com a do app.
4. O workflow testa Python e JavaScript, gera o EXE com PyInstaller, cria o instalador Inno Setup e anexa `EscritorIA-Setup.exe` e `SHA256SUMS.txt` à release. O alias antigo é mantido para atualizadores anteriores.
5. A release é publicada somente se os testes e a compilação terminarem com sucesso.

O job usa o `GITHUB_TOKEN` da própria Actions com permissão `contents: write`. Não cadastre chaves de IA como secrets do repositório: elas pertencem a cada instalação local.

## Compilar no computador

Windows x64, Python 3.10+ e Inno Setup 6. Execute `Gerar-instalador-Windows.bat`. Saída: `app/release/EscritorIA-Setup.exe`. O log fica em `app/gerar-app.log`. O pacote inclui Chromium para a ferramenta de navegação e precisa do Edge WebView2 Runtime para a janela nativa.

O ícone aprovado é incorporado ao executável e ao instalador. Atalhos do EXE usam esse ícone. Para a edição de fontes, execute `Primeiro-acesso.bat` na pasta definitiva; o script preserva atalhos antigos e cria um novo.

## Atualizar e preservar dados

Na edição de fontes, extraia em pasta nova e copie `dados/` e `config.json` da versão anterior para a raiz. No aplicativo instalado, os dados ficam em `%LOCALAPPDATA%/AtelieIA/`; esse caminho e o identificador do instalador são mantidos por compatibilidade. Não renomeie essa pasta para mudar a marca.

Este pacote contém fontes. O EXE só existe após a compilação no Windows ou na Actions. O aplicativo não possui assinatura digital incluída; o Windows pode exibir a verificação de reputação do instalador.

## Enviar pelo terminal do VS Code

Abra a pasta extraída no VS Code e use o terminal. Substitua a URL pelo repositório que você criou:

```bash
git init
git add .
git status --short
git commit -m "Organiza aplicação e fluxo de delegação"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/SEU-REPOSITORIO.git
git push -u origin main
```

Confira a lista de arquivos antes do commit: dados, config.json e credenciais não devem aparecer. Depois de uma compilação manual bem-sucedida, publique a versão:

```bash
git tag v0.45.0
git push origin v0.45.0
```

Acompanhe a execução em Actions e baixe o instalador em Releases quando terminar. Não declare o EXE disponível antes de o job finalizar.

Para critérios de validação, tags e notas de publicação, siga [Versionamento e releases](VERSOES.md). Para preservação de dados, veja [Dados e backup](DADOS.md).

# Versionamento e releases

## O que guardar em cada lugar

| Conteúdo | Local |
| --- | --- |
| Código e documentação atuais | Git |
| Alterações pequenas e rastreáveis | Commits |
| Identificação de uma versão publicada | Tag `vX.Y.Z` |
| Mudanças para o usuário | [CHANGELOG](CHANGELOG.md) |
| Instaladores e checksums | GitHub Releases |
| Pacotes anteriores ao Git | Arquivo histórico separado |
| Dados e credenciais de usuários | Backup privado, nunca no repositório |

Os pacotes antigos não foram convertidos em commits retroativos. O [histórico anterior ao Git](HISTORICO.md) registra o que foi possível confirmar. Não crie tags antigas apontando para o código atual: isso daria uma identidade incorreta às versões.

## Fluxo de publicação

1. Termine as mudanças e atualize documentação e changelog.
2. Atualize a versão em `app/server.py` e a verificação correspondente em `app/web/boot.js`; procure também referências de versão nos guias.
3. Execute as verificações de [CONTRIBUTING.md](../CONTRIBUTING.md) e confira os resultados no Actions.
4. Execute manualmente **Gerar instalador Windows**. Baixe o artefato e teste instalação, inicialização e atualização com dados preservados.
5. Só depois crie uma tag correspondente à versão do aplicativo e envie ao GitHub.
6. O workflow da tag executa os testes e a compilação antes de publicar o instalador. Confira arquivos e checksum na release.
7. Edite as notas com mudanças, requisitos, migrações e limitações conhecidas.

Exemplo para quando a versão interna for 0.45.0 e essa tag ainda não existir:

```bash
git tag -a v0.45.0 -m "EscritorIA 0.45.0"
git push origin v0.45.0
```

Não mova uma tag publicada para outro código. Faça uma versão corretiva. Uma alteração apenas documental pode ficar em “Não publicado”, sem incrementar a versão do aplicativo.

## Modelo de notas

```markdown
## Mudanças
- Descreva o comportamento novo ou corrigido.

## Instalação e atualização
- Requisitos e arquivo a baixar.
- Necessidade de backup ou migração.

## Validação
- Testes automatizados e verificações manuais realizadas.

## Limitações conhecidas
- Fluxos ainda não verificados e dependências externas.
```

## Critérios antes de anunciar o download

- Instalador gerado com sucesso e arquivos presentes na release.
- Instalação em Windows limpo, abertura e atalho conferidos.
- Atualização preservando dados conferida.
- Fluxo real de conversa, delegação e entrega validado com provedor configurado.
- Dependências opcionais e limitações explicitadas.

A presença de um workflow não comprova que esses critérios foram cumpridos. Este documento define o processo; não declara o EXE validado ou publicado.

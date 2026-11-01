# Changelog

## Não publicado

- Documentação de uso, arquitetura, dados e backup, diagnóstico, segurança e processo de releases.
- Inventário dos pacotes anteriores ao Git, com lacunas e arquivos incompletos identificados.

## Revisões posteriores à importação 0.45.0

- `92bc143`: organização de guias, modelos de issues e PRs, regras de arquivos e inclusão da licença/configurações no pacote de fontes.
- `8e2439f`: correção do teste de conversa dos NPCs para controlar o relógio monotônico, com cobertura do intervalo de espera. Sem alteração da regra de execução do aplicativo.
- [Execução aprovada de testes](https://github.com/LucasNobreS/EscritorIA/actions/runs/41242912107). Isso não equivale a uma release Windows validada.

## 0.45.0 — fontes

- Gerente distribui a execução na etapa inicial e revisa as contribuições. Respostas sem delegação recebem uma correção; persistindo o erro, a tarefa pausa sem entrega prematura.
- Cargos livres com sugestões de várias áreas. A equipe inicial é opcional; retirada preserva pelo menos um gerente e bloqueia profissionais com demandas pendentes.
- Rotas HTTP e motor de tarefas extraídos de server.py. Python formatado com Ruff.
- Logo e ícone aplicados à interface e às configurações do build Windows.
- README com arquitetura, decisões técnicas, GIF e vídeo de 20 segundos da interface com dados fictícios.
- Guias atuais em docs/, exemplo pequeno em examples/. Históricos e capturas antigas fora da pasta de publicação.
- Actions de testes e compilação Windows. Tags publicam a release após testes e build; execução manual gera artefatos.

A geração e a validação do instalador Windows são etapas separadas da aprovação dos testes dos fontes. Provedores reais dependem das chaves, permissões e cotas locais.

## Versões anteriores

Consulte o [histórico reconstruído](HISTORICO.md). Os pacotes anteriores ao Git não têm changelogs detalhados verificados para cada revisão; o inventário informa a evidência disponível sem inventar datas ou tags.

Para as próximas versões, registre adições, correções, incompatibilidades e validações e siga [Versionamento e releases](VERSOES.md).

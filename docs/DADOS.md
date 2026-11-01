# Dados, backup e atualização

## Onde ficam os dados

| Execução | Local |
| --- | --- |
| Fontes pelos atalhos da raiz | `dados/` e configuração na pasta do projeto |
| Aplicativo instalado | `%LOCALAPPDATA%/AtelieIA/` |
| Execução personalizada | Pode usar `ATELIE_STATE_ROOT`; confira o ambiente de inicialização |

O caminho antigo `AtelieIA` é mantido por compatibilidade. Não renomeie a pasta manualmente para acompanhar a marca EscritorIA. Veja `office_backup.py` e `windows_install.py` para a implementação.

## Antes de atualizar

1. Conclua ou pause as tarefas e confira operações externas pendentes.
2. Use o recurso de backup disponível no aplicativo. Para uma cópia manual, feche o app antes de copiar a pasta de dados e a configuração.
3. Guarde a cópia fora da pasta que será substituída.
4. Instale ou extraia a nova edição seguindo [Windows](WINDOWS.md).
5. Confira funcionários, configurações, histórico, anexos e entregas antes de retomar projetos.

Não copie apenas o arquivo principal de SQLite enquanto o aplicativo estiver escrevendo: podem existir arquivos WAL associados. Backups podem conter informações privadas e credenciais; não publique o arquivo no GitHub.

## Restaurar

Use `Restaurar-backup.bat` e selecione um backup compatível criado pelo aplicativo. Preserve uma cópia do estado atual antes de restaurar. O histórico de versões dos fontes não substitui o backup dos dados pessoais.

Não tente abrir um banco atualizado com uma versão antiga sem uma cópia de segurança. Voltar o código não desfaz automaticamente migrações ou efeitos realizados em serviços externos.

## Interrupção inesperada

Ao reabrir, confira **Alertas** e tarefas pausadas. Uma tarefa interrompida pode já ter criado arquivos ou solicitado uma ação externa. Confira o resultado antes de repetir. Retentativas automáticas são limitadas e não abrangem indiscriminadamente todas as operações.

## O que fica fora do Git

Dados de uso, configurações privadas, `.env`, bancos, logs pessoais, ambientes virtuais e executáveis de desenvolvimento ficam fora do versionamento. `.gitignore` evita novos envios acidentais, mas não remove segredos que já tenham sido publicados. Nesse caso, revogue a credencial e trate o histórico.

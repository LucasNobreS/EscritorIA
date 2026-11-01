# Solução de problemas

Comece pela versão aberta, pelo estado do serviço local e pela Central de alertas. Atualizar os fontes não altera um EXE antigo já instalado.

| Sintoma | Verificação e ação |
| --- | --- |
| App não abre | Execute pela pasta completa; confira Python na edição de fontes e WebView2 na edição nativa. Consulte o terminal ou log do iniciador. |
| Interface incompleta ou botões parados | Feche cópias antigas e inicie a pasta correta. Não misture arquivos de versões diferentes. Confira se `app/web/` foi extraída por inteiro. |
| Não conecta à FreeLLMAPI | Abra o painel em `http://127.0.0.1:3001`. O roteador precisa estar em execução separadamente. |
| HTTP 401 | Confira a chave unificada do roteador; não cole uma chave Gemini no campo FreeLLMAPI. |
| HTTP 404 | Confira endereço-base, versão do app e rota suportada pelo roteador. O endereço padrão FreeLLMAPI no app termina em `/v1`. |
| HTTP 429 | Verifique cotas e limites no provedor; mais funcionários não criam mais cota. |
| HTTP 502 ou timeout | Consulte o registro da requisição no roteador. Pode ser indisponibilidade ou demora do provedor, mesmo com o serviço local funcionando. |
| Tarefa permanece aguardando | Confira a fila, outras tarefas do funcionário, permissões e eventual necessidade de retornar à mesa. |
| Gerente não delega | Mantenha especialistas ativos com contexto adequado e use Novo projeto. Confira a mensagem da tarefa pausada. |
| Imagem falha com texto funcionando | Verifique modelo de geração de imagens e permissão; visão e geração de imagens são capacidades diferentes. |
| Navegador indisponível | Instale o componente pela rotina indicada em Integrações ou confira se o build incluiu Chromium. |
| Vídeo local falha | Confira FFmpeg e Pillow; geração remota exige uma integração de vídeo compatível. |
| Publicação com resultado incerto | Confira o perfil ou painel externo antes de repetir. Não reenvie automaticamente. |

## Diagnóstico de demora

Diferencie três tempos: espera na fila do EscritorIA, processamento no roteador e processamento no provedor. Aumentar o timeout local não altera o limite de tempo do serviço remoto. Reduza o pedido para um teste curto, confirme o modelo e depois retome o projeto completo.

## Como relatar

Abra uma [issue de problema](https://github.com/LucasNobreS/EscritorIA/issues/new?template=bug_report.md) com versão, sistema, forma de execução, passos e resultado esperado. Inclua a mensagem completa relevante, removendo chaves, tokens, senhas e dados pessoais. Falhas de segurança devem seguir [SECURITY.md](../SECURITY.md).

## GitHub Actions vermelho

Abra a execução e a primeira etapa que falhou. Falha de formatação, teste, compilação e publicação são problemas diferentes. Execuções antigas continuam vermelhas mesmo após a correção; confira a execução correspondente ao commit mais recente.

O teste de NPCs corrigido em `8e2439f` dependia do relógio monotônico do computador. O teste agora controla esse relógio, incluindo o limite de espera, sem alterar a regra de funcionamento do aplicativo.

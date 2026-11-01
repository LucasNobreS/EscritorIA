# Integrações — v0.45.0

## Conexão principal: FreeLLMAPI

No app, abra Configurar IA → Tutorial em vídeo e lista de APIs. O guia completo também está em app/web/tutorial-freellm.html. Instale o roteador oficial: https://github.com/tashfeenahmed/freellmapi/releases . Painel local: http://127.0.0.1:3001 . O EscritorIA usa `http://127.0.0.1:3001/v1`, modelo `auto` e a chave unificada do painel. Cadastre as chaves reais dos provedores **nesse painel**, sem ativar serviços pagos. Não é necessário comprar Premium.

Para texto, é suficiente cadastrar um provedor gratuito com um modelo disponível. Para enxergar capturas e fotos, habilite um modelo **Vision**. Para gerar imagem, habilite um modelo da categoria **Image**. São capacidades diferentes. Se um recurso não estiver disponível, o escritório deve informar a falha; não há garantia de todos os modelos estarem acessíveis com a sua conta.

Em Configurar IA → Começar, marque equipe inteira e, se desejado, geração de imagens. O botão testa apenas texto, antes de salvar. Em Artes e código, gere uma imagem real para confirmar. Imagens usam sempre FreeLLMAPI; a conexão direta FLUX foi removida. Endpoints pagos personalizados no roteador não são bloqueados pelo EscritorIA: não os configure para manter custo zero. A mesma chave não substitui tokens de redes sociais.

## Onde obter cada credencial opcional

| Serviço | Link oficial / finalidade |
|---|---|
| Gemini | https://aistudio.google.com/apikey — chave de texto/visão; cadastre no roteador ou use conexão direta alternativa |
| Groq | https://console.groq.com/keys — alternativa de texto/código no roteador ou direta |
| OpenRouter | https://openrouter.ai/settings/keys — somente rotas gratuitas compatíveis; observe as regras da conta |
| Cloudflare, dentro da FreeLLMAPI | https://dash.cloudflare.com/ — Workers AI → Use REST API; copie Account ID e crie token Workers AI. Cadastre no roteador como account_id:token; preserve a conexão existente. Confira acesso gratuito ao modelo de imagem escolhido. |
| YouTube | https://console.cloud.google.com/apis/library/youtube.googleapis.com — habilite YouTube Data API v3 no projeto, depois APIs e serviços → Credenciais → Criar chave de API; restrinja a chave à API necessária |
| Instagram | https://developers.facebook.com/apps/ — configure o aplicativo e acesso oficial ao Instagram; não forneça sua senha à IA |
| Supabase, opcional | https://supabase.com/dashboard — projeto e bucket público autorizados para mídias que o Instagram precisa baixar |

A gratuidade depende do plano, cota e configuração de cada conta. O aplicativo não ativa faturamento e não comprova remotamente que suas contas estão sem cobrança. RSS, Open Library e TVmaze não exigem uma chave no EscritorIA, mas têm disponibilidade e condições próprias. Open Library oferece metadados e conteúdo aberto disponível; TVmaze oferece informações de séries, não reprodução livre de filmes.

## Publicar no Instagram

1. Prepare a conta profissional e o aplicativo Meta com as permissões necessárias para o fluxo suportado.
2. Em Configurar IA → Instagram, cadastre o token oficial e o ID da conta. Use Testar Instagram.
3. Crie uma imagem; a rede social precisa de uma URL pública HTTPS de JPEG/MP4. Localhost não é acessível pelo Instagram. Configure o armazenamento opcional ou uma URL pública autorizada.
4. Crie um rascunho, confira legenda e mídia e aprove. O padrão é revisão pelo dono. Automático é uma opção explícita separada.
5. Se a publicação tiver resultado incerto, confira o perfil antes de repetir. Não inventamos confirmação de publicação nem teste com conta real.

## Erros comuns

- **Não conecta à porta 3001:** abra a FreeLLMAPI e confira seu painel. O EscritorIA não a inicia automaticamente.
- **401:** a chave unificada não foi aceita; uma chave Gemini colada nesse campo não serve.
- **422 / sem visão:** habilite um modelo com visão no roteador. PDFs/áudio/vídeo não são enviados como documentos binários por esta integração.
- **429:** cota ou limite temporário; verifique o roteador e aguarde. Criar funcionários não cria cotas novas.
- **Imagem sem base64:** esta integração aceita PNG/JPEG em `data[].b64_json`; ela não baixa uma URL arbitrária enviada pelo roteador.
- **Funcionário sem acesso:** habilite o recurso na matriz Minha equipe e retome a tarefa. A resposta rejeitada não vira entrega.
- **Navegador ausente:** no fonte, execute Instalar-navegador.bat; no EXE, o Chromium precisa ter sido incluído durante a compilação.

## Documentação primária consultada

- https://github.com/tashfeenahmed/freellmapi — projeto e instalação.
- https://github.com/tashfeenahmed/freellmapi/blob/main/docs/en/api/01-rest-api.md — chat, visão e geração de mídia.
- https://tashfeenahmed.github.io/freellmapi/ — edição gratuita e oferta Premium.

Os testes automatizados usam respostas controladas, sem suas chaves. A conexão real com provedores, geração real, Instagram e o EXE Windows precisam ser confirmados no ambiente configurado do usuário. Não há conta de serviço ou saldo fornecido dentro do ZIP.

## Vídeos e motion SaaS

**Motion e edição locais:** use FFmpeg e Pillow. A criação de telas, textos e gráficos animados não precisa de uma API de vídeo. O roteiro pode ser criado pelo funcionário com a IA geral. Use o estúdio de vídeo em Artes e código; exemplos estão em examples/.

**Geração de cenas por IA:** o EscritorIA agora atende a rota `/v1/videos/generations` da FreeLLMAPI, separada do editor local. Habilite a opção no estúdio e a permissão Vídeo por IA na matriz. A chave continua sendo a unificada. No roteador, habilite um provedor de Video compatível, por exemplo:

- Pollinations: https://enter.pollinations.ai/ — confira como obter a chave e os créditos disponíveis na sua conta. Vídeo não é coberto pela promessa de imagens/texto anônimos da API Classic.
- Hugging Face: https://huggingface.co/settings/tokens — token com a permissão de usar Inference Providers. Confira cota/créditos em https://huggingface.co/docs/inference-providers/pricing ; a pequena cota de teste pode não pagar uma geração de vídeo.

A existência de um modelo no catálogo não confirma que a sua conta pode executá-lo gratuitamente. O EscritorIA não cadastra cartão, compra saldo ou assina planos. Falta de saldo/cota gera erro; não há fallback para a rota paga. Uma resposta incerta precisa ser conferida no painel antes de novo pedido.

Vídeos por descrição são diferentes dos layouts motion: para texto exato, marca e interface legível, use o motor local com capturas reais. Depois você pode misturar uma cena gerada remotamente ao vídeo local.

## Se aparecia “serviço desconectado” após a primeira solicitação

Use a versão atual do aplicativo (a correção foi introduzida na v0.37.1) e reinicie pela pasta atualizada. Foi corrigida uma falha na rota de atualização do histórico, que recebia parâmetros e retornava 404 indevidamente. Não é necessário gerar outra chave FreeLLMAPI nem apagar seus dados para resolver essa falha.

Confira a versão do EscritorIA aberto: trocar arquivos do código-fonte não atualiza uma cópia EXE antiga. Falta real de conexão com o roteador na porta 3001 e erros de chave/cota ainda devem ser conferidos no painel FreeLLMAPI.

## Falhas e novas tentativas

A Central de alertas reúne falhas dos funcionários no botão Alertas do ambiente. Erros temporários seguros de texto e pesquisa podem receber até duas repetições automáticas, com espera mínima de 15 e 45 s. Cota, chave inválida, publicações, mídia gerada e operações incertas não são repetidas automaticamente.

A repetição não cria cota nova: chamadas contam nos limites existentes. Desligue a opção na central se preferir controlar tudo manualmente. Falhas de configuração ainda exigem ajustar o serviço correspondente. O histórico anterior não é executado de novo ao atualizar.

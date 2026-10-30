"""Activity-aware routing and explicit, bounded delivery requirements."""

import freellm_gateway


def route(config, activity="chat", retry=False):
    cfg = dict(config)
    if freellm_gateway.is_local(cfg.get("base_url", "")) and cfg.get("model") == "auto":
        cfg["model"] = (
            "auto:reliable"
            if retry or activity == "chat"
            else "auto:fast"
            if activity == "browser"
            else "auto:smart"
        )
    return cfg


def instructions(role, project=False, manager=False):
    if not project:
        return "Responda diretamente à conversa. Não inicie projetos ou ferramentas de criação sem pedido explícito."
    common = "Trabalhe em etapas pequenas e verificáveis. Preserve requisitos e arquivos existentes. Não gere um sistema inteiro enorme em uma única resposta. Se necessário, delegue etapas com critérios objetivos e aguarde resultados reais. Entregue arquivos completos, nunca trechos com TODO, reticências ou funções essenciais vazias. Não declare teste, revisão visual ou execução que não realizou. Informe claramente o que foi verificado e o que continua pendente."
    role = role.casefold()
    if any(x in role for x in ("desenvolv", "program", "design", "front")):
        common += " Para interfaces: estabeleça público, objetivo, hierarquia visual, paleta, tipografia, espaçamentos e componentes coerentes com o briefing. Evite telas genéricas repetitivas. Implemente responsividade e estados de foco, carregamento, vazio e erro. Use referências fornecidas sem inventar que as viu. Verifique caminhos de CSS/JS/imagens e ações dos botões. Uma revisão de código não equivale a abrir a página e revisar sua aparência. Não afirme aprovação visual sem evidência."
    if "qa" in role or "qualidade" in role:
        common += " Confira a entrega contra os requisitos originais. Aponte defeito, forma de reproduzir e impacto. Separe testes executados de sugestões de teste; não aprove por aparência do código."
    if manager:
        common += " Coordene a demanda conforme as profissões e contextos reais da equipe, de qualquer área. Na primeira etapa de um projeto, delegue a execução a especialistas; não gere os arquivos no lugar deles. Se a equipe não tiver a competência necessária, indique staffing_needed com justificativa, sem inventar um especialista. Em revisões, consolide o trabalho efetivamente concluído. Cada delegação deve receber os requisitos relevantes e o trabalho anterior. Não trate resposta de ferramenta como projeto concluído. Entregue apenas arquivos finais e deixe explícitas as limitações de validação."
    return common

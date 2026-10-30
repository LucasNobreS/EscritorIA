"""Validate coordination before accepting a manager's initial project response."""


def is_planning(employee, task):
    return (
        bool(employee["manager"])
        and task.get("intent") == "project"
        and task.get("kind", "task") == "task"
        and not task.get("parent")
    )


def specialists(connection, manager_id):
    return [
        dict(row)
        for row in connection.execute(
            "SELECT id,name,role,context,background,skills,expectations FROM employees WHERE active=1 AND manager=0 AND id!=? ORDER BY slot",
            (manager_id,),
        )
    ]


def validate_plan(answer, team):
    if (
        answer.get("staffing_needed")
        and not answer.get("files")
        and not answer.get("actions")
    ):
        return None
    allowed = {employee["id"] for employee in team}
    actions = answer.get("actions", [])
    if answer.get("files"):
        return "A etapa inicial é de distribuição; arquivos devem vir dos especialistas antes da revisão."
    if not actions or len(actions) > 3:
        return "Envie entre uma e três delegações com briefings completos."
    delegated = False
    for action in actions:
        if not isinstance(action, dict):
            return "Ação de delegação inválida."
        if action.get("type") == "delegate":
            if (
                type(action.get("employee_id")) is not int
                or action["employee_id"] not in allowed
            ):
                return "Escolha um especialista ativo da equipe; não delegue para si ou outro gerente."
            if not isinstance(action.get("task"), str) or not action["task"].strip():
                return "Inclua o briefing da tarefa."
            delegated = True
        elif action.get("type") not in ("message", "move"):
            return "O gerente deve delegar a execução nesta etapa, sem executar ferramentas."
    return None if delegated else "Nenhuma delegação foi enviada."

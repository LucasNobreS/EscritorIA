"""Team membership rules. Job titles remain unrestricted user text."""


def validate_manager(connection, employee_id, manager):
    if employee_id is None or manager:
        return
    row = connection.execute(
        "SELECT manager FROM employees WHERE id=? AND active=1", (int(employee_id),)
    ).fetchone()
    if (
        row
        and row["manager"]
        and not connection.execute(
            "SELECT id FROM employees WHERE active=1 AND manager=1 AND id!=?",
            (int(employee_id),),
        ).fetchone()
    ):
        raise ValueError(
            "Mantenha pelo menos um gerente. Defina outro gerente antes de alterar este funcionário."
        )


def archive(connection, employee_id):
    validate_manager(connection, employee_id, False)
    if not connection.execute(
        "SELECT id FROM employees WHERE id=? AND active=1", (employee_id,)
    ).fetchone():
        raise ValueError("Funcionário não encontrado.")
    if (
        connection.execute(
            "SELECT id FROM tasks WHERE root IN (SELECT root FROM tasks WHERE employee=?) AND status!='concluida'",
            (employee_id,),
        ).fetchone()
        or connection.execute(
            "SELECT id FROM tool_jobs WHERE employee=? AND status IN ('queued','running','waiting')",
            (employee_id,),
        ).fetchone()
    ):
        raise ValueError(
            "Conclua as tarefas pendentes antes de retirar este funcionário."
        )
    if connection.execute(
        "SELECT id FROM deliveries WHERE manager=? AND status IN ('pending','in_transit')",
        (employee_id,),
    ).fetchone():
        raise ValueError("Aguarde a entrega do gerente.")
    connection.execute(
        "UPDATE employees SET active=0,slot=NULL WHERE id=?", (employee_id,)
    )

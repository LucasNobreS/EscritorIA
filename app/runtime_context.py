"""Live service registry shared by the HTTP layer and task workers.

The application owns connections, locks and mutable process flags. This adapter
keeps those dependencies in one place while preserving the server module's public
entry points used by the desktop launcher and integrations.
"""


class RuntimeContext:
    def __init__(self, namespace):
        object.__setattr__(self, "_namespace", namespace)

    def __getattr__(self, name):
        try:
            return self._namespace[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name, value):
        self._namespace[name] = value

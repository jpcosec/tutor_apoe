"""Config de pytest para los paquetes vendoreados de runtime/.

Los tests que dependen del modulo `data` (SqlStore, Privacy, Vault, ...) de AntonIA
no se vendorearon: se omiten de la coleccion. Quitar de aqui cuando exista un
sustrato de datos equivalente en este repo.
"""
import importlib.util

collect_ignore = []
if importlib.util.find_spec("data") is None:
    collect_ignore += [
        "context/tests/test_context.py",
        "context/tests/test_context_rebuild.py",
        "context/tests/test_substrate_projection.py",
        "context/tests/projection_support.py",
        "tools/tests/test_operations.py",
    ]


def pytest_configure(config):
    config.addinivalue_line("markers", "spec(id): referencia a la spec de origen")

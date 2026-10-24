from apps.kb_agent.runtime.compiler import MesaCompiler as RuntimeMesaCompiler
from apps.kb_agent.runtime.pack_loader import load_pack
from apps.kb_chat_ui.table_compiler import MesaCompiler as LegacyMesaCompiler


def test_apos_pack_matches_legacy_compiler_for_reference_query():
    query = '¿Qué dice la base sobre encapsulación en APOS?'
    runtime = RuntimeMesaCompiler(load_pack('apos'))
    legacy = LegacyMesaCompiler()

    runtime_compiled = runtime.compile(query)
    legacy_compiled = legacy.compile(query)

    runtime_mesa = runtime_compiled['mesa']
    legacy_mesa = legacy_compiled['mesa']

    assert runtime_mesa['include_tags'] == legacy_mesa['include_tags']
    assert runtime_mesa['expanded_tags'] == legacy_mesa['expanded_tags']
    assert runtime_mesa['atom_ids'] == legacy_mesa['atom_ids']
    assert [item['score'] for item in runtime_mesa['items']] == [item['score'] for item in legacy_mesa['items']]

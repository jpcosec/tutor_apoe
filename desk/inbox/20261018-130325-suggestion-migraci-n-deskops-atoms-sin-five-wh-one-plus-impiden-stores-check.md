---
# unclear | suggestion
kind: suggestion
# e.g., other_repo
sender_project: deskops
# e.g., target_repo
target_project: tutor_apoe
# ISO 8601 timestamp
created_at: '2026-10-18T13:03:25'
# open | closed
status: open
# project identity that acknowledged the note
# ISO 8601 timestamp, set when acknowledged
---

# Migración deskops: atoms sin five_wh_one_plus impiden stores check

_Describe the incoming message with enough evidence to triage._

La migración de ciclo de vida de deskops (desk update --apply, autorizada por el dueño el 2026-10-18) no pudo completarse: sldb stores check falla porque atoms de desk/atoms/branches/ no tienen five_wh_one_plus (what/why/how/how_not/when/where/for_whom), que AtomDoc exige. Hay ediciones sin commit en esos atoms; no las toqué. Arreglo: completar five_wh_one_plus en cada atom y correr 'deskops desk update --root . --apply'. Respaldo previo a la migración en /tmp/rw/mig/backup/. Enviado por deskops-6e.

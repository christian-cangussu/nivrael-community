"""QoL-relatos - Peso do Oficio + Uma Masmorra de Cada Vez: injetor i18n (SO-ADICOES).

Roda: python -X utf8 scripts/inject_qol_relatos_i18n.py

Padrao inject_tec2_i18n: adiciona apenas keys AUSENTES (nunca sobrescreve),
json.dump(ensure_ascii=False, indent=4, sort_keys=True) + newline="\\n" +
newline final (sem o newline="\\n" o Windows converte tudo para CRLF e o diff
vira o ficheiro inteiro).

CHAT (locales/*) = a linha do resumo de craft/forja que agora EXPLICA o peso
(prf_xp_gain_line_tier - a antiga prf_xp_gain_line fica intacta, e e o
fallback quando o tier e desconhecido) + as duas recusas de "uma masmorra de
cada vez" (a que voce esta em outra / a que voce esta nesta) + o botao de ir
para a run. O botao Retirar-se reusa a key dng_btn_retreat, que ja existe.

MINI (miniapp/i18n/*) = as 2 keys do painel admin (feature_masmorra_unica
[_desc], que se auto-documenta - Lei S6) + o espelho das duas recusas + o
botao de retirada com nome+andar + a linha do peso no resumo do craft.

PT-BR estrito (voce/seu, nunca tu/teu); ES usa tuteo (a es.json viva tem 554
strings com tu contra 9 com usted); placeholders {tok} un-accented e com o
MESMO conjunto de tokens nas 3 linguas.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("pt", "en", "es")

CHAT = {
 "pt": {
  # Item A - o peso VISIVEL (Lei S10: o numero sobe e o jogador sabe porque).
  "prf_xp_gain_line_tier": "🏮 +{xp} XP de ofício · tier {tier} (peso ×{w})",
  # Item B - as recusas, sempre com nome + andar (Lei S1).
  "dng_run_elsewhere": "🚪 *Você já está dentro de outra masmorra.*\n\n{emoji} *{name}* — andar *{floor}*\n\nUm cultivador não caminha por dois portais ao mesmo tempo. Retire-se de lá primeiro (o saco volta inteiro com você) ou retome a expedição onde ela parou.",
  "dng_run_here": "🚪 *Você está dentro desta masmorra agora.*\n\n{emoji} *{name}* — andar *{floor}*\n\nNão dá para varrer o caminho enquanto você ainda o percorre. Retire-se para reclamar o saco e a varredura fica livre outra vez.",
  "dng_btn_go_to_run": "➡️ Voltar à expedição",
 },
 "en": {
  "prf_xp_gain_line_tier": "🏮 +{xp} craft XP · tier {tier} (weight ×{w})",
  "dng_run_elsewhere": "🚪 *You are already inside another dungeon.*\n\n{emoji} *{name}* — floor *{floor}*\n\nA cultivator does not walk two gates at once. Retreat from there first (your bag comes back whole) or resume the expedition where it stopped.",
  "dng_run_here": "🚪 *You are inside this dungeon right now.*\n\n{emoji} *{name}* — floor *{floor}*\n\nYou cannot sweep a path while still walking it. Retreat to claim your bag and the sweep opens up again.",
  "dng_btn_go_to_run": "➡️ Back to the expedition",
 },
 "es": {
  "prf_xp_gain_line_tier": "🏮 +{xp} XP de oficio · tier {tier} (peso ×{w})",
  "dng_run_elsewhere": "🚪 *Ya estás dentro de otra mazmorra.*\n\n{emoji} *{name}* — piso *{floor}*\n\nUn cultivador no camina por dos portales a la vez. Retírate de allí primero (el saco vuelve entero contigo) o retoma la expedición donde quedó.",
  "dng_run_here": "🚪 *Estás dentro de esta mazmorra ahora mismo.*\n\n{emoji} *{name}* — piso *{floor}*\n\nNo se puede barrer un camino mientras todavía lo recorres. Retírate para reclamar el saco y el barrido vuelve a quedar libre.",
  "dng_btn_go_to_run": "➡️ Volver a la expedición",
 },
}

MINIAPP = {
 "pt": {
  "feature_masmorra_unica": "Uma Masmorra de Cada Vez (QoL-relatos)",
  "feature_masmorra_unica_desc": "⚠️ LAUNCH-SERVER-BOUND: ligar em um mundo vivo pega quem já está no meio de uma run (em 27/07 havia 15 runs abertas e 2 jogadores com 2 simultâneas) — eles verão a recusa na próxima entrada, com o botão Retirar-se para sair sem perder o saco. Com uma run aberta (andar > 0) em qualquer masmorra, ENTRAR em outra é recusado dizendo o nome e o andar da run em curso e oferecendo a saída ali mesmo. Varrer OUTRA masmorra já concluída continua livre (a varredura é revisitar o que você dominou, não uma expedição); varrer justamente aquela onde você está dentro é recusado, porque hoje isso paga duas vezes — a varredura entrega uma limpeza inteira enquanto a run manual guarda o próprio saco. Honra a geografia do MV-1: cada portal está ancorado a um continente e viajar tem cooldown de 4h, então estar dentro de três masmorras em três continentes desmentia o mundo. Sem knobs env: a regra é binária e a masmorra em curso é sempre a de menor id (determinística, para o botão de saída não dançar entre pedidos). Recomendado ligar junto com dungeons_regionais.",
  "dungeon_run_elsewhere": "Você já está dentro de {emoji} {name}, no andar {floor}. Um cultivador não caminha por dois portais ao mesmo tempo.",
  "dungeon_run_here": "Você está dentro de {emoji} {name} agora, no andar {floor}. Não dá para varrer o caminho enquanto você ainda o percorre.",
  "dungeon_btn_retreat_from": "🔙 Retirar-se de {emoji} {name} (andar {floor})",
  "prf_mini_xp_gain_tier": "+{n} XP de ofício · tier {tier} (peso ×{w})",
 },
 "en": {
  "feature_masmorra_unica": "One Dungeon at a Time (QoL-relatos)",
  "feature_masmorra_unica_desc": "⚠️ LAUNCH-SERVER-BOUND: enabling this on a live world catches players already mid-run (on 27/07 there were 15 open runs and 2 players with 2 simultaneous ones) — they will meet the refusal on their next entry, with a Retreat button to leave without losing the bag. With an open run (floor > 0) in any dungeon, ENTERING another is refused, naming the dungeon and floor of the run in progress and offering the way out right there. Sweeping ANOTHER already-cleared dungeon stays free (a sweep is revisiting what you mastered, not an expedition); sweeping the very one you are inside is refused, because today that pays twice — the sweep hands over a full clear while the manual run keeps its own bag. It honours MV-1 geography: each gate is anchored to a continent and travel has a 4h cooldown, so being inside three dungeons on three continents contradicted the world. No env knobs: the rule is binary and the run in progress is always the lowest id (deterministic, so the exit button does not dance between requests). Best enabled alongside dungeons_regionais.",
  "dungeon_run_elsewhere": "You are already inside {emoji} {name}, on floor {floor}. A cultivator does not walk two gates at once.",
  "dungeon_run_here": "You are inside {emoji} {name} right now, on floor {floor}. You cannot sweep a path while still walking it.",
  "dungeon_btn_retreat_from": "🔙 Retreat from {emoji} {name} (floor {floor})",
  "prf_mini_xp_gain_tier": "+{n} craft XP · tier {tier} (weight ×{w})",
 },
 "es": {
  "feature_masmorra_unica": "Una Mazmorra a la Vez (QoL-relatos)",
  "feature_masmorra_unica_desc": "⚠️ LAUNCH-SERVER-BOUND: encenderlo en un mundo vivo atrapa a quien ya está a mitad de una run (el 27/07 había 15 runs abiertas y 2 jugadores con 2 simultáneas) — verán el rechazo en la próxima entrada, con el botón Retirarse para salir sin perder el saco. Con una run abierta (piso > 0) en cualquier mazmorra, ENTRAR en otra queda rechazado diciendo el nombre y el piso de la run en curso y ofreciendo la salida allí mismo. Barrer OTRA mazmorra ya completada sigue libre (el barrido es revisitar lo que dominaste, no una expedición); barrer justo aquella donde estás dentro queda rechazado, porque hoy eso paga dos veces — el barrido entrega una limpieza entera mientras la run manual guarda su propio saco. Honra la geografía del MV-1: cada portal está anclado a un continente y viajar tiene cooldown de 4h, así que estar dentro de tres mazmorras en tres continentes desmentía el mundo. Sin knobs env: la regla es binaria y la mazmorra en curso es siempre la de menor id (determinística, para que el botón de salida no baile entre pedidos). Conviene encenderlo junto con dungeons_regionais.",
  "dungeon_run_elsewhere": "Ya estás dentro de {emoji} {name}, en el piso {floor}. Un cultivador no camina por dos portales a la vez.",
  "dungeon_run_here": "Estás dentro de {emoji} {name} ahora, en el piso {floor}. No se puede barrer un camino mientras todavía lo recorres.",
  "dungeon_btn_retreat_from": "🔙 Retirarse de {emoji} {name} (piso {floor})",
  "prf_mini_xp_gain_tier": "+{n} XP de oficio · tier {tier} (peso ×{w})",
 },
}


def _apply(path: str, additions: dict) -> tuple:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    before = len(data)
    for k, v in additions.items():
        if k not in data:
            data[k] = v
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=4, sort_keys=True)
        f.write("\n")
    return before, len(data)


def main() -> None:
    for lang in LANGS:
        b, a = _apply(os.path.join(ROOT, "locales", lang + ".json"), CHAT[lang])
        print("chat " + lang + ": " + str(b) + " -> " + str(a) + " (+" + str(a - b) + ")")
    for lang in LANGS:
        b, a = _apply(os.path.join(ROOT, "miniapp", "i18n", lang + ".json"), MINIAPP[lang])
        print("mini " + lang + ": " + str(b) + " -> " + str(a) + " (+" + str(a - b) + ")")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""🩸 A BATERIA DE SABOTAGEM de 一 a senha dos mundos tem um dono (2026-10-24).

Mesmo contrato das outras (`_sabota_a_decisao`, `_sabota_varredor`, …): cada
entrada estraga UMA coisa no código de produção, corre
`scripts/_test_senha_dos_mundos.py`, e exige que ela fique VERMELHA **a dizer o
que é** — nunca a rebentar, e nunca por um motivo diferente do esperado.

O que esta bateria guarda, e porque cada ataque existe:

  · O motor de um mundo pede o login ao env (1) — sem isso, uma linha limpa liga
    sem utilizador e o mundo cai.
  · Nenhuma senha volta à tabela: nem a do `main` no arranque (2), nem a de um
    mundo novo (6).
  · A limpeza só tira o que o env devolve IGUAL (3, 8) e nunca passa por cima de
    um login que a linha escolheu (7) — um mundo noutro servidor, ou uma senha
    antiga que o env já não tem, ficam como estavam.
  · A senha do env só vai para o servidor do env (9): uma linha sem login que
    aponte a outro host nunca a recebe — um servidor alheio que pedisse a senha
    em claro ficava com ela.
  · A limpeza corre a cada arranque (5), num passo PRÓPRIO (4): se ela falhar, o
    registo e o `main` arrancam na mesma, com as linhas como estavam.

Uso:  python scripts/_sabota_a_senha_dos_mundos.py
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "database", "db.py")
CDB = os.path.join(ROOT, "database", "control_db.py")
WP = os.path.join(ROOT, "core", "world_provision.py")
SUITE = os.path.join(ROOT, "scripts", "_test_senha_dos_mundos.py")

_LIMPEZA = (
    "    # A senha dos mundos sai da tabela (fica só no env) — passo próprio: falhar\n"
    "    # aqui deixa as linhas como estavam, e elas continuam a ligar.\n"
    "    try:\n"
    "        from database.control_db import strip_registry_credentials\n"
    "        await strip_registry_credentials()\n"
    "    except Exception:\n"
    "        logger.warning(\"registry credential cleanup failed — rows keep their logins\", exc_info=True)\n"
)

# (rótulo, ficheiro, de, para, pedaço que TEM de aparecer na linha vermelha)
SABOTAGENS = [
    ("1 o motor deixa de pedir o login ao env", DB,
     '    db_url = _normalize_asyncpg(with_env_credentials(row.get("db_url") or ""))',
     '    db_url = _normalize_asyncpg(row.get("db_url") or "")',
     "2/a linha sem login liga com o utilizador do env"),
    ("2 o arranque volta a gravar a senha do main", CDB,
     # (sem a chaveta: na cópia pública o exportador acrescenta a flag a esta linha)
     '"db_url": strip_credentials(DATABASE_URL)',
     '"db_url": DATABASE_URL',
     "3/…sem utilizador nem senha"),
    ("3 a limpeza tira o login de QUALQUER linha", CDB,
     "            if sem != url and with_env_credentials(sem) == url:",
     "            if sem != url:",
     "4/uma linha com outro login não é tocada"),
    ("4 a falha da limpeza volta a parar o arranque", DB,
     _LIMPEZA,
     "    from database.control_db import strip_registry_credentials\n"
     "    await strip_registry_credentials()\n",
     "não impede o registo nem o main"),
    ("5 a limpeza deixa de correr no arranque", DB,
     _LIMPEZA,
     "",
     "4/o init_db limpa DEPOIS do arranque"),
    ("6 o aprovisionamento volta a guardar a senha", WP,
     '            {"key": key, "name": name, "db_url": stored_url, "rc": requires_code,',
     '            {"key": key, "name": name, "db_url": db_url, "rc": requires_code,',
     "5/o registo guarda o endereço SEM login"),
    ("7 o login do env passa por cima do da linha", CDB,
     '    if not parts.netloc or "@" in parts.netloc or "@" not in env.netloc:',
     '    if not parts.netloc or "@" not in env.netloc:',
     # (a de OUTRO servidor fica a salvo pela verificação do host — ataque 9; quem
     #  apanha esta é a linha com o seu login no MESMO servidor)
     "1/uma linha com a senha antiga fica como foi escrita"),
    ("8 um mundo noutro servidor perde o seu login", WP,
     "    if with_env_credentials(stored_url) != db_url:\n        stored_url = db_url\n",
     "",
     "5/um db_url com OUTRO login fica guardado como foi dado"),
    ("9 a senha do env vai para qualquer servidor", CDB,
     "    if (parts.hostname, parts.port or 5432) != (env.hostname, env.port or 5432):\n        return url\n",
     "",
     "1/o login do env NUNCA vai para outro servidor"),
]


def _repor(path: str, conteudo: str, copia: str) -> None:
    """Escreve e CONFIRMA. Medido a 24/10: no Windows, um ficheiro acabado de escrever
    pode estar preso (o antivírus a lê-lo) e o `open('w')` da reposição falhou com
    Errno 22 — o código de produção ficou sabotado. Tenta de novo e lê o que ficou."""
    for _ in range(40):
        try:
            with io.open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(conteudo)
            if io.open(path, encoding="utf-8", newline="").read() == conteudo:
                return
        except OSError:
            pass
        time.sleep(0.5)
    raise SystemExit(f"⚠️ NÃO consegui repor {path} — o original está em {copia}; repor À MÃO antes de mais nada")


def run():
    falhas = []
    guarda = tempfile.mkdtemp(prefix="nv_sabota_senha_")  # os originais, antes de estragar
    print("=" * 78)
    print("  \U0001fa78 SABOTAGEM de 一 a senha dos mundos — %d ataques" % len(SABOTAGENS))
    print("=" * 78)
    for rot, path, de, para, agulha in SABOTAGENS:
        orig = io.open(path, encoding="utf-8", newline="").read()
        # O alvo é verificado ANTES: uma sabotagem que não acha o que estragar
        # dava-se por boa, e um "8/8 mordem" assim é um falso verde.
        if orig.count(de) != 1:
            falhas.append("%-50s ALVO NÃO ENCONTRADO (%d ocorrências)" % (rot, orig.count(de)))
            print("  !!  " + falhas[-1])
            continue
        copia = os.path.join(guarda, os.path.basename(path))
        io.open(copia, "w", encoding="utf-8", newline="").write(orig)
        sabotado = orig.replace(de, para, 1)
        _repor(path, sabotado, copia)
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run([sys.executable, "-X", "utf8", SUITE], capture_output=True, text=True,
                               env=env, cwd=ROOT, timeout=300, encoding="utf-8", errors="replace")
            saida = r.stdout or ""
            vermelhos = [l for l in saida.split("\n") if l.strip().startswith("FAIL:")]
            rebentou = " passed · " not in saida
            mordeu = r.returncode == 1 and vermelhos and not rebentou
            if mordeu and any(agulha in l for l in vermelhos):
                print("  ok  %-50s mordeu (%d vermelhos)" % (rot, len(vermelhos)))
            elif rebentou:
                falhas.append("%-50s REBENTOU — uma guarda que rebenta não é uma guarda "
                              "vermelha\n%s" % (rot, (r.stderr or "")[-600:]))
                print("  XX  " + falhas[-1])
            elif not mordeu:
                falhas.append("%-50s FICOU VERDE" % rot)
                print("  XX  " + falhas[-1])
            else:
                falhas.append("%-50s vermelha pelo motivo ERRADO (esperava %r; veio %r)"
                              % (rot, agulha, (vermelhos[:1] or [""])[0][:90]))
                print("  XX  " + falhas[-1])
        finally:
            _repor(path, orig, copia)
    # tudo reposto e confirmado (o `_repor` pára o programa antes de chegar aqui se
    # não conseguir): a cópia de segurança já não guarda nada que falte
    shutil.rmtree(guarda, ignore_errors=True)
    print()
    print("%d/%d sabotagens mordem" % (len(SABOTAGENS) - len(falhas), len(SABOTAGENS)))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(run())

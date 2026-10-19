#!/usr/bin/env python3
"""Genera el README del catálogo a partir de las estrellas de GitHub.

Uso:
    GITHUB_TOKEN=... python scripts/generar.py
    python scripts/generar.py --input repos.json   # sin red, para pruebas

Lee las estrellas de las cuentas configuradas en CUENTAS, conserva la
categoría ya asignada a cada repo en data/asignaciones.json y clasifica los
repos nuevos por palabras clave según data/categorias.json. Escribe README.md
y actualiza data/asignaciones.json con los repos nuevos.

Solo usa la librería estándar de Python.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

CUENTAS = ["AgustinBouzonn", "AgustinBouzon"]
REPO = "AgustinBouzonn/github-stars"
WORKFLOW = "actualizar.yml"
DIAS_RECIENTES = 30
UMBRAL_FUEGO = 10_000

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_CATEGORIAS = RAIZ / "data" / "categorias.json"
ARCHIVO_ASIGNACIONES = RAIZ / "data" / "asignaciones.json"
ARCHIVO_README = RAIZ / "README.md"


# --------------------------------------------------------------------------- datos


def _get(url: str, token: str | None) -> tuple[list, str | None]:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.star+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "github-stars-generator")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        datos = json.load(resp)
        link = resp.headers.get("Link", "")
    siguiente = None
    for parte in link.split(","):
        if 'rel="next"' in parte:
            siguiente = parte[parte.index("<") + 1 : parte.index(">")]
    return datos, siguiente


def descargar_estrellas(token: str | None) -> list[dict]:
    repos: dict[str, dict] = {}
    for cuenta in CUENTAS:
        url: str | None = f"https://api.github.com/users/{cuenta}/starred?per_page=100"
        total = 0
        while url:
            pagina, url = _get(url, token)
            for item in pagina:
                r = item["repo"]
                clave = r["full_name"].lower()
                previo = repos.get(clave)
                if previo is None or item["starred_at"] < previo["starred_at"]:
                    repos[clave] = {
                        "full_name": r["full_name"],
                        "owner": r["owner"]["login"],
                        "description": r.get("description") or "",
                        "language": r.get("language") or "",
                        "stars": r.get("stargazers_count", 0),
                        "pushed_at": r.get("pushed_at") or "",
                        "topics": r.get("topics") or [],
                        "archived": r.get("archived", False),
                        "starred_at": item["starred_at"],
                    }
                total += 1
        print(f"{cuenta}: {total} estrellas", file=sys.stderr)
    return list(repos.values())


# ---------------------------------------------------------------- clasificación


def _patron(palabra: str) -> re.Pattern:
    return re.compile(r"(?<![\w-])" + re.escape(palabra.lower()) + r"(?![\w-])")


def clasificar(repo: dict, config: dict) -> str:
    if repo["owner"].lower() in {c.lower() for c in CUENTAS}:
        return "personales"
    nombre = repo["full_name"].split("/", 1)[1].replace("-", " ").replace("_", " ")
    texto = " ".join([nombre, repo["description"], " ".join(repo["topics"])]).lower()
    por_id = {c["id"]: c for c in config["categorias"]}
    for cid in config["orden_clasificacion"]:
        for palabra in por_id[cid]["palabras_clave"]:
            if _patron(palabra).search(texto):
                return cid
    return "misc"


# ------------------------------------------------------------------- formato


def slug(titulo: str) -> str:
    """Ancla de GitHub para un encabezado."""
    t = titulo.strip().lower()
    t = re.sub(r"[^\w\- ]", "", t)
    return t.replace(" ", "-")


def recortar(texto: str, largo: int) -> str:
    texto = " ".join(texto.split()).replace("|", "\\|")
    if not texto:
        return "—"
    return texto if len(texto) <= largo else texto[: largo - 3] + "..."


def estrellas(n: int, fuego: bool = False) -> str:
    s = f"{n:,}"
    return f"{s} 🔥" if fuego and n >= UMBRAL_FUEGO else s


def lenguaje(repo: dict) -> str:
    return repo["language"] or "Sin especificar"


def enlace(repo: dict) -> str:
    return f"[{repo['full_name']}](https://github.com/{repo['full_name']})"


def generar_readme(repos: list[dict], asig: dict, config: dict, ahora: datetime) -> str:
    cats = config["categorias"]
    por_id = {c["id"]: c for c in cats}
    nombre_cat = {c["id"]: f"{c['emoji']} {c['titulo']}" for c in cats}
    for r in repos:
        r["cat"] = asig[r["full_name"]]
    repos.sort(key=lambda r: (-r["stars"], r["full_name"].lower()))
    total = len(repos)
    fecha = ahora.strftime("%Y-%m-%d")
    lenguajes = Counter(lenguaje(r) for r in repos)
    por_cat = {c["id"]: [r for r in repos if r["cat"] == c["id"]] for c in cats}
    activas = [c for c in cats if por_cat[c["id"]]]
    top = repos[0]

    o: list[str] = []
    w = o.append
    w('<div align="center">\n')
    w("# ⭐ GitHub Stars\n")
    w(f"**Catálogo de {total} repositorios destacados, organizados en {len(activas)} categorías.**\n")
    w(f"![Repos](https://img.shields.io/badge/repos-{total}-7aa2f7?style=flat-square)")
    w(f"![Categorías](https://img.shields.io/badge/categor%C3%ADas-{len(activas)}-7aa2f7?style=flat-square)")
    w(f"![Actualizado](https://img.shields.io/badge/actualizado-{fecha.replace('-', '--')}-565f89?style=flat-square)")
    w(f"[![Actualizar catálogo](https://github.com/{REPO}/actions/workflows/{WORKFLOW}/badge.svg)](https://github.com/{REPO}/actions/workflows/{WORKFLOW})\n")
    w("</div>\n")

    w("## Qué es\n")
    cuentas = " y ".join(f"[{c}](https://github.com/{c})" for c in CUENTAS)
    w(f"Un índice de los repositorios que marqué con estrella desde mis dos cuentas de GitHub, {cuentas}. "
      "Cada repo está clasificado por temática para encontrar rápido herramientas, librerías y referencias.\n")
    w("> [!NOTE]")
    w("> Se actualiza solo todos los lunes con GitHub Actions. "
      f"Las estrellas, descripciones y fechas reflejan el **{fecha}**.\n")

    w("## 📌 Resumen\n")
    w("| Campo | Valor |")
    w("|-------|-------|")
    w(f"| 📅 Última actualización | {ahora.strftime('%Y-%m-%d %H:%M')} UTC |")
    w(f"| 👤 Cuentas | {' · '.join(f'[{c}](https://github.com/{c})' for c in CUENTAS)} |")
    w(f"| 📦 Repositorios | **{total}** |")
    w(f"| 🗂️ Categorías | **{len(activas)}** |")
    w(f"| 🏆 Más estrellado | {enlace(top)} · ⭐ {top['stars']:,} |")
    w(f"| 🔤 Top 5 lenguajes | {' · '.join(f'**{l}** ({n})' for l, n in lenguajes.most_common(5))} |\n")

    t_top, t_rec, t_est, t_cat = ("🏆 Top 20 Repos por Estrellas", "🆕 Actualizados Recientemente",
                                  "📊 Estadísticas & Lenguajes", "📑 Categorías")
    w("## 📋 Índice\n")
    for t, etiqueta in [(t_top, "🏆 Top 20 por estrellas"), (t_rec, "🆕 Actualizados recientemente"),
                        (t_est, "📊 Estadísticas y lenguajes"), (t_cat, "📑 Categorías")]:
        w(f"- [{etiqueta}](#{slug(t)})")
    w("")
    w("| | | |")
    w("|---|---|---|")
    celdas = [f"[{nombre_cat[c['id']]}](#{slug(nombre_cat[c['id']])}) · {len(por_cat[c['id']])}" for c in activas]
    while len(celdas) % 3:
        celdas.append("")
    for i in range(0, len(celdas), 3):
        w("| " + " | ".join(celdas[i : i + 3]) + " |")
    w("\n---\n")

    w(f"## {t_top}\n")
    w("Los 20 repositorios con más estrellas de toda la colección.\n")
    w("| # | Repo | Categoría | ⭐ Estrellas | Descripción |")
    w("|---|------|-----------|---------|-------------|")
    for i, r in enumerate(repos[:20], 1):
        w(f"| {i} | {enlace(r)} | {por_id[r['cat']]['emoji']} | {estrellas(r['stars'], True)} | {recortar(r['description'], 100)} |")
    w("\n---\n")

    recientes = []
    for r in repos:
        if not r["pushed_at"]:
            continue
        dias = (ahora - datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00"))).days
        if 0 <= dias <= DIAS_RECIENTES:
            recientes.append((r, dias))
    w(f"## {t_rec}\n")
    w(f"Repositorios con actividad en los últimos {DIAS_RECIENTES} días. Total: **{len(recientes)}**\n")
    if recientes:
        w("| Repo | Categoría | ⭐ Estrellas | Días atrás | Descripción |")
        w("|------|-----------|---------|-----------|-------------|")
        for r, dias in recientes:
            w(f"| {enlace(r)} | {por_id[r['cat']]['emoji']} | {estrellas(r['stars'])} | {dias}d | {recortar(r['description'], 80)} |")
    w("")

    w(f"## {t_est}\n")
    w("### 🔤 Distribución por Lenguaje (Top 15)\n")
    w("| Lenguaje | Repos | % | Barra |")
    w("|----------|-------|---|-------|")
    for l, n in lenguajes.most_common(15):
        pct = n * 100 / total
        llenos = int(pct * 30 / 100)
        w(f"| {l} | {n} | {pct:.1f}% | `{'█' * llenos}{'░' * (30 - llenos)}` |")
    w("")
    w("### 🗂️ Repos por Categoría\n")
    w("| Categoría | Repos | % del Total |")
    w("|-----------|-------|-------------|")
    for c in activas:
        n = len(por_cat[c["id"]])
        w(f"| {nombre_cat[c['id']]} | {n} | {n * 100 / total:.1f}% |")
    w(f"| **TOTAL** | **{total}** | **100%** |")
    w("\n---\n")

    w(f"## {t_cat}\n")
    w("_Cada categoría lista sus repos ordenados por estrellas._\n")
    for c in activas:
        lista = por_cat[c["id"]]
        w(f"### {nombre_cat[c['id']]}\n")
        w(f"_{c['descripcion']}_\n")
        langs = Counter(lenguaje(r) for r in lista).most_common(5)
        w(f"**{len(lista)} repos** · Lenguajes: {' · '.join(f'{l} ({n})' for l, n in langs)}\n")
        w("| Repo | Descripción | Lenguaje | ⭐ Estrellas |")
        w("|------|-------------|----------|---------|")
        for r in lista:
            w(f"| {enlace(r)} | {recortar(r['description'], 120)} | {r['language'] or '—'} | {estrellas(r['stars'], True)} |")
        w("")
        w(f'<p align="right"><a href="#{slug("📋 Índice")}">↑ Volver al índice</a></p>\n')
        w("---\n")

    w("## 📝 Cómo se genera\n")
    w(f"- El workflow [`{WORKFLOW}`](.github/workflows/{WORKFLOW}) corre todos los lunes y se puede lanzar a mano desde Actions.")
    w("- [`scripts/generar.py`](scripts/generar.py) descarga las estrellas de ambas cuentas desde la API de GitHub y escribe este README.")
    w("- Cada repo conserva la categoría guardada en [`data/asignaciones.json`](data/asignaciones.json). "
      "Los repos nuevos se clasifican por palabras clave de [`data/categorias.json`](data/categorias.json) "
      "usando nombre, descripción y topics.")
    w("- Para mover un repo de categoría, editá su entrada en `data/asignaciones.json`.")
    return "\n".join(o) + "\n"


# ------------------------------------------------------------------------ main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--input", help="JSON con la lista de repos, en lugar de llamar a la API")
    ap.add_argument("--fecha", help="fecha de referencia ISO, por defecto ahora (UTC)")
    args = ap.parse_args()

    config = json.loads(ARCHIVO_CATEGORIAS.read_text(encoding="utf-8"))
    asig = json.loads(ARCHIVO_ASIGNACIONES.read_text(encoding="utf-8"))

    if args.input:
        repos = json.loads(Path(args.input).read_text(encoding="utf-8"))
    else:
        repos = descargar_estrellas(os.environ.get("GITHUB_TOKEN"))
    if not repos:
        print("No se obtuvo ningún repo; no se modifica nada.", file=sys.stderr)
        return 1

    ahora = datetime.fromisoformat(args.fecha) if args.fecha else datetime.now(timezone.utc)
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=timezone.utc)

    asig_lower = {k.lower(): v for k, v in asig.items()}
    nuevos = 0
    for r in repos:
        previa = asig_lower.get(r["full_name"].lower())
        if previa:
            asig.pop(next(k for k in asig if k.lower() == r["full_name"].lower()))
            asig[r["full_name"]] = previa
        else:
            asig[r["full_name"]] = clasificar(r, config)
            nuevos += 1

    ARCHIVO_README.write_text(generar_readme(repos, asig, config, ahora), encoding="utf-8")
    ARCHIVO_ASIGNACIONES.write_text(
        json.dumps(dict(sorted(asig.items(), key=lambda x: x[0].lower())), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"{len(repos)} repos, {nuevos} nuevos clasificados.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

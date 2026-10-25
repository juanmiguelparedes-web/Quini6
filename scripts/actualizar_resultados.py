#!/usr/bin/env python3
"""Actualiza resultados de Quini 6 desde Caja de Acción Social (Santa Fe)."""
import datetime as dt
import json
import pathlib
import re
import urllib.request
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "resultados.json"
BASE = "https://cas.gob.ar/juegos/sorteos/resultados?fecha={}&juego=quini6"

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag in ("h1", "h2", "h3", "h4", "p", "div", "li", "br"):
            self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
        if tag in ("h1", "h2", "h3", "h4", "p", "div", "li"):
            self.parts.append("\n")
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

MODES = [
    ("Tradicional", r"Tradicional"),
    ("La Segunda", r"(?:Segunda Vuelta|La Segunda|Segunda del Quini)"),
    ("Revancha", r"Revancha"),
    ("Siempre Sale", r"Siempre Sale"),
]

def parse(html, date, url):
    parser = TextExtractor()
    parser.feed(html)
    text = re.sub(r"[ \t]+", " ", "".join(parser.parts))
    if not re.search(r"Resultados de Quini 6", text, re.I):
        raise ValueError("Página inesperada")
    if not re.search(r"Sorteo del\s+" + str(date.day) + r"\s+de\s+", text, re.I):
        raise ValueError("La fecha publicada no coincide con la solicitada")
    positions = []
    for name, pattern in MODES:
        match = re.search(r"(?im)^\s*" + pattern + r"\s*$", text)
        if not match:
            raise ValueError("Falta la modalidad " + name)
        positions.append((name, match.end(), match.start()))
    if positions != sorted(positions, key=lambda x: x[2]):
        raise ValueError("Orden de modalidades inesperado")
    result = []
    draw_numbers = []
    for i, (name, start, _) in enumerate(positions):
        end = positions[i + 1][2] if i + 1 < len(positions) else len(text)
        segment = text[start:end]
        draw = re.search(r"Sorteo\s*N[°ºo.]?\s*(\d+)", segment, re.I)
        if not draw:
            raise ValueError("No se encontró el número de sorteo para " + name)
        draw_numbers.append(int(draw.group(1)))
        tail = segment[draw.end():]
        # Las seis bolillas aparecen en líneas individuales, antes del texto informativo.
        nums = [int(x) for x in re.findall(r"(?m)^\s*(\d{1,2})\s*$", tail)[:6]]
        if len(nums) != 6 or len(set(nums)) != 6 or any(n > 45 for n in nums):
            raise ValueError("Números incompletos o inválidos para " + name)
        result.append({"nombre": name, "numeros": sorted(nums)})
    if len(set(draw_numbers)) != 1:
        raise ValueError("Número de sorteo inconsistente")
    return {"fecha": date.isoformat(), "numeroSorteo": draw_numbers[0], "fuente": url, "modalidades": result}

def main():
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).date()
    old = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else None
    # Solo fechas de miércoles y domingo, nunca fechas futuras.
    for offset in range(0, 22):
        date = now - dt.timedelta(days=offset)
        if date.weekday() not in (2, 6):
            continue
        url = BASE.format(date.isoformat())
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MiQuini6/1.0 (GitHub Actions)"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            data = parse(html, date, url)
            if old and (data["fecha"] < old["fecha"] or (data["fecha"] == old["fecha"] and data["numeroSorteo"] < old["numeroSorteo"])):
                raise ValueError("El sorteo encontrado es anterior al guardado")
            if data != old:
                OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print("Actualizado:", data["fecha"], data["numeroSorteo"])
            else:
                print("Sin cambios:", data["fecha"])
            return
        except Exception as exc:
            print("No se pudo validar", date, ":", exc)
    raise SystemExit("No se encontró un sorteo reciente verificable; se conservan los datos anteriores.")

if __name__ == "__main__":
    main()

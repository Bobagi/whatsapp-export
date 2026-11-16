"""process.py · transforma o JSON do exporter.js num registro legivel, com midias e transcricoes.

Uso:
    .venv\\Scripts\\python.exe process.py D:\\Downloads\\wa-Dayse-....json
    opcoes: --out conversas  --model large-v3  --cpu  --no-transcribe

Saida (por conversa e exportacao): conversas/<chat>/<AAAA-MM-DD_HHMM>/
    conversa.md    registro completo, audios transcritos inline
    conversa.txt   mesmo conteudo em texto puro
    mensagens.json metadados sem base64 (+ transcricao)
    midia/         audios (.ogg), imagens, figurinhas, documentos
Transcricoes ficam em cache (midia/<arquivo>.txt): rodar de novo nao retranscreve.
"""
import argparse
import base64
import json
import mimetypes
import os
import re
import site
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDIO_TYPES = {"ptt", "audio"}
EXT = {
    "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/aac": ".aac",
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "video/mp4": ".mp4",
    "application/pdf": ".pdf",
}
TYPE_LABEL = {"ptt": "audio", "audio": "audio", "image": "imagem", "video": "video",
              "document": "documento", "sticker": "figurinha", "gif": "gif"}


def add_cuda_dlls():
    """No Windows, o CTranslate2 precisa achar cuBLAS/cuDNN instalados via pip (nvidia-*-cu12)."""
    if os.name != "nt":
        return
    for sp in site.getsitepackages():
        nv = Path(sp) / "nvidia"
        if nv.is_dir():
            for b in nv.glob("*/bin"):
                os.add_dll_directory(str(b))
                os.environ["PATH"] = str(b) + os.pathsep + os.environ["PATH"]


def ext_for(mime, filename):
    base = (mime or "").split(";")[0].strip().lower()
    if filename and Path(filename).suffix:
        return Path(filename).suffix
    return EXT.get(base) or mimetypes.guess_extension(base) or ".bin"


def slug(s):
    return re.sub(r"[^\w\-]+", "_", s, flags=re.UNICODE).strip("_") or "conversa"


class Transcriber:
    def __init__(self, model_name, cpu):
        add_cuda_dlls()
        from faster_whisper import WhisperModel
        self.model = None
        if not cpu:
            try:
                self.model = WhisperModel(model_name, device="cuda", compute_type="float16")
                self.device = "cuda"
            except Exception as e:  # sem GPU/DLL: cai para CPU
                print(f"[aviso] GPU indisponivel ({e}); usando CPU", file=sys.stderr)
        if self.model is None:
            self.model = WhisperModel(model_name, device="cpu", compute_type="int8")
            self.device = "cpu"

    def __call__(self, path):
        segs, _info = self.model.transcribe(str(path), language="pt", beam_size=5, vad_filter=True)
        return " ".join(s.text.strip() for s in segs).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export_json")
    ap.add_argument("--out", default=str(ROOT / "conversas"))
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--no-transcribe", action="store_true")
    a = ap.parse_args()

    data = json.loads(Path(a.export_json).read_text(encoding="utf-8"))
    stamp = datetime.fromisoformat(data["exportedAt"].replace("Z", "+00:00")).astimezone()
    outdir = Path(a.out) / slug(data["chat"]) / stamp.strftime("%Y-%m-%d_%H%M")
    mdir = outdir / "midia"
    mdir.mkdir(parents=True, exist_ok=True)

    tr = None
    msgs = data["messages"]
    for i, m in enumerate(msgs, 1):
        dt = datetime.fromtimestamp(m["t"])
        b64 = m.pop("mediaB64", None)
        if b64:
            fname = f"{dt:%Y%m%d_%H%M%S}_{slug(m['author'])}_{TYPE_LABEL.get(m['type'], m['type'])}{ext_for(m.get('mimetype'), m.get('filename'))}"
            fpath = mdir / fname
            if not fpath.exists():
                fpath.write_bytes(base64.b64decode(b64))
            m["file"] = f"midia/{fname}"
            if m["type"] in AUDIO_TYPES and not a.no_transcribe:
                cache = fpath.with_suffix(fpath.suffix + ".txt")
                if cache.exists():
                    m["transcription"] = cache.read_text(encoding="utf-8")
                else:
                    if tr is None:
                        print(f"carregando Whisper {a.model}...", flush=True)
                        tr = Transcriber(a.model, a.cpu)
                        print(f"Whisper em {tr.device}", flush=True)
                    print(f"[{i}/{len(msgs)}] transcrevendo {fname}", flush=True)
                    m["transcription"] = tr(fpath)
                    cache.write_text(m["transcription"], encoding="utf-8")

    (outdir / "mensagens.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# Conversa com {data['chat']}", "",
             f"Periodo: {datetime.fromisoformat(data['from'].replace('Z', '+00:00')).astimezone():%d/%m/%Y %H:%M} ate "
             f"{stamp:%d/%m/%Y %H:%M} · {len(msgs)} mensagens", ""]
    day = None
    for m in msgs:
        dt = datetime.fromtimestamp(m["t"])
        if dt.date() != day:
            day = dt.date()
            lines += ["", f"## {dt:%d/%m/%Y}", ""]
        body = []
        if m.get("quoted"):
            q = (m["quoted"].get("text") or "").replace("\n", " ")
            body.append(f"> respondendo: {q[:200]}")
        t = m["type"]
        if t in AUDIO_TYPES:
            dur = f" {int(m.get('duration') or 0)//60}:{int(m.get('duration') or 0)%60:02d}" if m.get("duration") else ""
            link = f" ([{Path(m['file']).name}]({m['file']}))" if m.get("file") else ""
            body.append(f"[audio{dur}]{link}")
            if m.get("transcription") is not None:
                body.append(f"_transcricao:_ {m['transcription'] or '(sem fala detectada)'}")
        elif t != "chat":
            label = TYPE_LABEL.get(t, t)
            link = f" ([{Path(m['file']).name}]({m['file']}))" if m.get("file") else ""
            extra = f" {m['filename']}" if m.get("filename") and t == "document" else ""
            body.append(f"[{label}{extra}]{link}" + (f" {m['text']}" if m.get("text") else ""))
        else:
            body.append(m.get("text") or "")
        if m.get("mediaError"):
            body.append(f"(midia nao baixada: {m['mediaError']})")
        if m.get("edited"):
            body.append("(editada)")
        if m.get("reactions"):
            body.append("reacoes: " + " ".join(m["reactions"]))
        lines.append(f"**{dt:%H:%M} {m['author']}:** " + "  \n".join(body))
        lines.append("")
    md = "\n".join(lines)
    (outdir / "conversa.md").write_text(md, encoding="utf-8")
    txt = re.sub(r"\*\*|_transcricao:_", lambda x: "transcricao:" if x.group(0).startswith("_") else "", md)
    (outdir / "conversa.txt").write_text(txt, encoding="utf-8")
    print(f"pronto: {outdir}")


if __name__ == "__main__":
    main()

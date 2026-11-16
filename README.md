# whatsapp-export

Exporta uma conversa do WhatsApp Web (texto, áudios, imagens, figurinhas, documentos) de um período e
transcreve os áudios localmente com Whisper na GPU. Nada sai da máquina.

## Como funciona

1. `exporter.js` roda dentro de `web.whatsapp.com` (logado). Usa os módulos internos do WhatsApp Web
   (`require('WAWebCollections')`, `WAWebChatLoadMessages`, `msg.downloadMedia`), os mesmos do
   [whatsapp-web.js](https://github.com/wwebjs/whatsapp-web.js): carrega o histórico até o corte, baixa e
   decifra a mídia e salva **um JSON** (`wa-<conversa>-<data>.json`) na pasta de downloads do navegador
   (no PC de casa: `D:\Downloads`).
2. `process.py` lê esse JSON, grava as mídias, transcreve áudios (`faster-whisper`, `large-v3`, CUDA) e
   escreve o registro em `conversas/<conversa>/<AAAA-MM-DD_HHMM>/`:
   - `conversa.md` / `conversa.txt`: tudo em ordem, áudios transcritos inline, link para cada mídia
   - `mensagens.json`: metadados + transcrições (sem base64)
   - `midia/`: arquivos `.ogg`, `.jpg`, `.webp`, `.pdf`... e o cache `*.txt` das transcrições

## Uso

**Pelo Claude Code** (Claude in Chrome): "exporta a conversa com Fulano dos últimos N dias". O Claude abre
o WhatsApp Web, injeta `exporter.js` com `javascript_tool` e chama:

```js
await waExport({ chat: 'Fulano', hours: 48 })          // ou { chat: 'Fulano', since: '2026-11-01' }
```

`chat` casa por trecho do nome da conversa; se mais de uma casar, precisa ser o nome exato.

**Na mão**: em `web.whatsapp.com`, F12 > Console, cole o conteúdo de `exporter.js`, Enter, depois a linha acima.

Depois:

```powershell
cd D:\Projetos\whatsapp-export
.\.venv\Scripts\python.exe process.py D:\Downloads\wa-Fulano-....json
# --model large-v3-turbo (mais rápido) · --cpu · --no-transcribe · --out <pasta>
```

## Instalação (uma vez)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

O primeiro uso baixa o modelo Whisper (~3 GB, cache do Hugging Face). Em 8 GB de VRAM (RTX 3060 Ti) o
`large-v3` em float16 cabe; 26 áudios de até 1:30 levaram poucos minutos.

## Armadilhas

- **PyAV 19+ quebra o faster-whisper 1.2.1** (`open() got an unexpected keyword argument 'metadata_errors'`):
  `requirements.txt` fixa `av<17`.
- No Windows o CTranslate2 precisa das DLLs de cuBLAS/cuDNN: vêm dos pacotes `nvidia-*-cu12` e o
  `process.py` registra as pastas `nvidia/*/bin` sozinho. Sem GPU, cai para CPU (int8).
- Os nomes dos módulos internos do WhatsApp Web mudam com atualizações. Se `waExport` quebrar, ver como o
  whatsapp-web.js faz hoje (`src/structures/Chat.js` `fetchMessages`, `src/util/Injected/Utils.js`
  `resolveMediaBlob`). Em 2026-11: `loadEarlierMsgs({ chat })` recebe um objeto, não o chat direto.
- Mídia muito antiga pode ter expirado no servidor: aparece como `mediaError` no JSON e no registro.
- `conversas/` e os JSON exportados são dados pessoais: ficam fora do Git (`.gitignore`).

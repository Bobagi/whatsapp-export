// exporter.js · roda dentro de https://web.whatsapp.com (Claude in Chrome javascript_tool ou console do DevTools).
// Usa os modulos internos do WhatsApp Web (window.require), os mesmos que o whatsapp-web.js usa.
// Uso: depois de colar este arquivo, chame:
//   await waExport({ chat: 'Dayse', hours: 48 })
// Resultado: baixa "wa-<chat>-<data>.json" na pasta Downloads, com todas as mensagens do periodo
// e a midia (audio, imagem, video, documento, figurinha) em base64. Depois rode process.py nele.
window.waExport = async function waExport({ chat: chatQuery, hours = 48, since = null, media = true } = {}) {
  const C = require('WAWebCollections');
  const LM = require('WAWebChatLoadMessages');
  const q = String(chatQuery || '').toLowerCase();
  const chats = C.Chat.getModelsArray().filter(c => (c.formattedTitle || '').toLowerCase().includes(q));
  if (!q || chats.length === 0) throw new Error('Conversa nao encontrada: ' + chatQuery);
  if (chats.length > 1) {
    const exact = chats.find(c => (c.formattedTitle || '').toLowerCase() === q);
    if (!exact) throw new Error('Mais de uma conversa casa com "' + chatQuery + '": ' + chats.map(c => c.formattedTitle).join(' / '));
    chats.splice(0, chats.length, exact);
  }
  const chat = chats[0];
  const cutoff = since ? Math.floor(new Date(since).getTime() / 1000) : Math.floor(Date.now() / 1000 - hours * 3600);

  // Carrega historico ate passar do corte (ou acabar a conversa).
  for (let i = 0; i < 200; i++) {
    const arr = chat.msgs.getModelsArray();
    if (arr.length && arr[0].t < cutoff) break;
    const got = await LM.loadEarlierMsgs({ chat });
    if (!got || !got.length) break;
  }

  const toB64 = buf => new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(String(fr.result).split(',')[1]);
    fr.onerror = rej;
    fr.readAsDataURL(new Blob([buf]));
  });

  async function getMediaBlob(m) {
    if (!m.mediaData || m.mediaData.mediaStage === 'REUPLOADING') return null;
    try { await m.downloadMedia({ downloadEvenIfExpensive: true, rmrReason: 1, isUserInitiated: true }); } catch (e) { /* tenta o cache mesmo assim */ }
    let blob = null;
    try { blob = require('WAWebMediaInMemoryBlobCache').InMemoryMediaBlobCache.get(m.mediaObject?.filehash); } catch (e) { }
    if (!blob && m.mediaObject?.mediaBlob) blob = await m.mediaObject.mediaBlob.forceToBlob();
    return blob || null;
  }

  const name = c => c?.formattedName || c?.pushname || c?.name || c?.verifiedName || '';
  const me = 'Eu';
  const out = [];
  const msgs = chat.msgs.getModelsArray().filter(m => m.t >= cutoff).sort((a, b) => a.t - b.t);
  for (const m of msgs) {
    const fromMe = !!m.id?.fromMe;
    const item = {
      id: m.id?.id,
      t: m.t,
      iso: new Date(m.t * 1000).toISOString(),
      fromMe,
      author: fromMe ? me : (name(m.senderObj) || chat.formattedTitle),
      type: m.type,
      text: m.type === 'chat' ? (m.body || '') : (m.caption || ''),
      edited: !!m.latestEditMsgKey || !!m.editMsgType,
      duration: m.duration ? Number(m.duration) : undefined,
      filename: m.filename || undefined,
      mimetype: m.mimetype || undefined,
      quoted: m.quotedMsg ? { type: m.quotedMsg.type, text: m.quotedMsg.type === 'chat' ? m.quotedMsg.body : (m.quotedMsg.caption || '[' + m.quotedMsg.type + ']') } : undefined,
      reactions: undefined,
    };
    if (m.type === 'location') item.text = 'Localizacao: ' + m.lat + ',' + m.lng;
    if (m.type === 'vcard') item.text = 'Contato: ' + (m.vcardFormattedName || '');
    if (m.type === 'revoked') item.text = '[mensagem apagada]';
    if (media && m.mediaData && ['ptt', 'audio', 'image', 'video', 'document', 'sticker', 'gif'].includes(m.type)) {
      try {
        const blob = await getMediaBlob(m);
        if (blob) {
          item.mediaB64 = await toB64(await blob.arrayBuffer());
          item.mimetype = item.mimetype || blob.type;
        } else item.mediaError = 'midia indisponivel (expirada ou nao baixada)';
      } catch (e) { item.mediaError = String(e && e.message || e); }
    }
    out.push(item);
  }

  // Reacoes (melhor esforco; modulo pode mudar).
  try {
    for (const item of out) {
      const r = C.Reactions.get(chat.msgs.getModelsArray().find(m => m.id?.id === item.id)?.id?._serialized);
      if (r?.reactions?.length) item.reactions = r.reactions.getModelsArray?.().map(x => x.aggregateEmoji).filter(Boolean);
    }
  } catch (e) { }

  const payload = {
    exporter: 'whatsapp-export/1',
    chat: chat.formattedTitle,
    isGroup: !!chat.isGroup,
    exportedAt: new Date().toISOString(),
    from: new Date(cutoff * 1000).toISOString(),
    count: out.length,
    messages: out,
  };
  const safe = chat.formattedTitle.replace(/[^\p{L}\p{N}_-]+/gu, '_');
  const fname = 'wa-' + safe + '-' + new Date().toISOString().slice(0, 16).replace(/[:T]/g, '') + '.json';
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload)], { type: 'application/json' }));
  const a = document.createElement('a');
  a.href = url; a.download = fname; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
  const withMedia = out.filter(x => x.mediaB64).length;
  const failed = out.filter(x => x.mediaError).length;
  return 'ok ' + fname + ' · ' + out.length + ' mensagens · ' + withMedia + ' midias · ' + failed + ' falhas';
};
'waExport pronto';

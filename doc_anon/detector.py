"""CPU token classification. No server, Hub client or external API is used."""
from __future__ import annotations

import bisect
import os
from .resources import configure_offline, model_dir, verify_resources
from .rizzo_detectors import detect_regex, complete_time, SOFT_REGEX_LABELS


def merge_entities(candidates, text):
    ordered = sorted(candidates, key=lambda e: (e.get('validated', False),
        e.get('source') == 'regex' and e['label'] not in SOFT_REGEX_LABELS,
        e.get('score', 0), e['end'] - e['start']), reverse=True)
    kept = []
    for original in ordered:
        e = dict(original)
        if not 0 <= e['start'] < e['end'] <= len(text):
            continue
        i = bisect.bisect_right(kept, e['start'], key=lambda k: k['start'])
        if (i and kept[i-1]['end'] > e['start']) or (i < len(kept) and kept[i]['start'] < e['end']):
            continue
        kept.insert(i, e)
    for e in kept:
        while e['start'] < e['end'] and text[e['start']].isspace():
            e['start'] += 1
        while e['end'] > e['start'] and text[e['end']-1].isspace():
            e['end'] -= 1
        while e['start'] > 0 and e['start'] < len(text) and text[e['start']-1].isalnum() and text[e['start']].isalnum():
            e['start'] -= 1
        while 0 < e['end'] < len(text) and text[e['end']].isalnum() and text[e['end']-1].isalnum():
            e['end'] += 1
    merged = []
    for e in sorted(kept, key=lambda e: (e['start'], -e['end'])):
        if e['end'] <= e['start']:
            continue
        if merged and e['start'] < merged[-1]['end']:
            merged[-1]['end'] = max(merged[-1]['end'], e['end'])
        else:
            merged.append(e)
    return merged


def segments_from_entities(text, entities):
    segments, cursor = [], 0
    for e in entities:
        if e['start'] > cursor:
            segments.append({'t': text[cursor:e['start']]})
        segments.append({'t': text[e['start']:e['end']], 'label': e['label']})
        cursor = e['end']
    if cursor < len(text):
        segments.append({'t': text[cursor:]})
    return segments


class Detector:
    def __init__(self):
        self.model = None
        self.tokenizer = None

    def load(self, progress):
        if self.model is not None:
            return
        configure_offline()
        verify_resources(progress)
        progress('Caricamento del modello nella memoria del PC…', 0, 0)
        import torch
        from transformers.models.modernbert.modeling_modernbert import ModernBertForTokenClassification
        from transformers.tokenization_utils_fast import PreTrainedTokenizerFast
        torch.set_num_threads(max(1, min(4, (os.cpu_count() or 2) // 2)))
        tokenizer = PreTrainedTokenizerFast.from_pretrained(str(model_dir()), local_files_only=True)
        model = ModernBertForTokenClassification.from_pretrained(
            str(model_dir()), local_files_only=True, use_safetensors=True,
            attn_implementation='sdpa', reference_compile=False,
        )
        model.eval()
        self.tokenizer, self.model = tokenizer, model

    def analyze(self, text, progress=lambda *_: None):
        text = text.strip()
        if not text:
            return []
        self.load(progress)
        import torch
        encoded = self.tokenizer(text, return_offsets_mapping=True, return_overflowing_tokens=True,
                                 truncation=True, max_length=256, stride=64, padding=False)
        candidates = []
        chunks = len(encoded['input_ids'])
        for n in range(chunks):
            progress(f'Analisi locale · blocco {n+1} di {chunks}', n, chunks)
            ids = torch.tensor([encoded['input_ids'][n]], dtype=torch.long)
            mask = torch.tensor([encoded['attention_mask'][n]], dtype=torch.long)
            with torch.inference_mode():
                logits = self.model(input_ids=ids, attention_mask=mask).logits[0]
                scores, labels = logits.softmax(-1).max(-1)
            active = None
            for index, (start, end) in enumerate(encoded['offset_mapping'][n]):
                tag = self.model.config.id2label[int(labels[index])]
                if start == end or tag == 'O':
                    active = None
                    continue
                prefix, _, label = tag.partition('-')
                if not label:
                    prefix, label = 'B', tag
                score = float(scores[index])
                if active is not None and prefix == 'I' and active['label'] == label:
                    active['end'] = end
                    active['score'] = min(active['score'], score)
                else:
                    active = {'start': start, 'end': end, 'label': label, 'score': score,
                              'source': 'modello', 'validated': False}
                    candidates.append(active)
        progress('Controllo dei formati e preparazione delle selezioni…', chunks, chunks)
        complete_time(candidates, text)
        return segments_from_entities(text, merge_entities(candidates + detect_regex(text), text))

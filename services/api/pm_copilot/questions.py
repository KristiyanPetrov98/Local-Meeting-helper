"""Conservative explicit-question extraction. No inference and no inferred questions."""
import re
from dataclasses import dataclass

# Interrogative syntax must be present; '?' alone does not make a statement a question.
EN_WH=r'(?:what|when|where|why|how|who|which|whose)\b'
EN_AUX=r'(?:can|could|would|will|should|do|does|did|is|are|was|were|has|have|may|must)\s+(?:you|we|i|it|this|that|there|the|our|a|an|they|he|she|any|all|[A-Z][\w-]*)\b'
BG_WH=r'(?:какво|каква|какъв|какви|кога|къде|защо|как|кой|коя|кое|кои|колко|дали)\b'
BG_AUX=r'(?:може(?:те|ш|м)?\s+ли|трябва\s+ли|има\s+ли|ще\s+(?:има|бъде|може)\s+ли|вярно\s+ли)\b'
PREFIX=re.compile(r'^(?:(?:so|and|but|then|okay|ok|please|а|и|но|добре|моля)[, ]+)*(?:'+EN_WH+'|'+EN_AUX+'|'+BG_WH+'|'+BG_AUX+')',re.I)
REPORTED=re.compile(r'^(?:the question (?:is|was)|(?:he|she|they|someone) (?:asked|said)|(?:въпросът|въпроса) (?:е|беше)|(?:той|тя|те) (?:попита|попитаха|каза))\b',re.I)
INDIRECT=re.compile(r'^(?:(?:what|how|when|where|why|who|which).{0,80})\s+(?:is|was|are|remains)\s+(?:clear|unclear|known|unknown|important|obvious|irrelevant)\b',re.I)

def _interrogative(text):
    value=text.strip(' \t\r\n"“”«»\'')
    if REPORTED.match(value) or INDIRECT.match(value): return False
    # Quoted/reported questions and code-like text are not direct meeting requests.
    if text.lstrip().startswith(('"','“','«','`')): return False
    if re.search(r'\b(?:is|are|was|were|do|does|did|will|would|should|can|could|has|have)\s*[?.!]*$',value,re.I): return False
    if re.match(r'^(?:will|would|can|could|should|may|must)\s+(?:do|be|have|see|check|try|send)\b',value,re.I): return False
    if re.match(r'^(?:what|where|when|how|why|which)\s+(?:we|i|you|they|he|she)\b',value,re.I): return False
    if not PREFIX.match(value): return False
    if not value.endswith('?'):
        if re.match(r'^(?:what|when|where|why|how|which|whose)\b',value,re.I) and not re.match(r"^(?:what|when|where|why|how|which|whose)\s+(?:(?:\w+\s+){0,3})?(?:is|are|was|were|do|does|did|will|would|should|can|could|has|have)\b",value,re.I):
            return False
        if re.search(r'\b(?:е|са|беше)\s+(?:ясно|важно|известно|очевидно)\b',value,re.I): return False
    return True


@dataclass(frozen=True)
class Question:
    text: str
    segment_ids: tuple[int,...]
    start: float
    end: float


def latest_question(segments):
    groups=[]
    for row in sorted(segments,key=lambda r:(r['start'],r['end'],r['id'])):
        if groups and groups[-1]['speaker']==row['speaker_id'] and groups[-1]['source']==row['source'] and row['start']-groups[-1]['end']<=1.5:
            group=groups[-1];offset=len(group['text'])+1
            group['text']+=' '+row['text'];group['end']=row['end'];group['ids'].append(row['id'])
            group['pieces'].append((offset,offset+len(row['text']),row['id'],row['start'],row['end']))
        else: groups.append({'text':row['text'],'start':row['start'],'end':row['end'],'speaker':row['speaker_id'],'source':row['source'],'ids':[row['id']],'pieces':[(0,len(row['text']),row['id'],row['start'],row['end'])]})
    candidates=[]
    for group in groups:
        # Retain '?' to distinguish question fragments; no cross-session/source merging.
        parts=re.split(r'(?<=[.!?])\s+|\n+',group['text'])
        cursor=0
        for ordinal,raw in enumerate(parts):
            pos=group['text'].find(raw,cursor);cursor=pos+len(raw)
            part=raw.strip()
            if len(part)>=4 and _interrogative(part):
                spans=[p for p in group['pieces'] if p[1]>pos and p[0]<cursor]
                if spans:
                    q=Question(part,tuple(p[2] for p in spans),spans[0][3],spans[-1][4])
                    candidates.append((q.end,spans[-1][2],ordinal,q))
    return max(candidates,key=lambda x:(x[0],x[1],x[2]))[3] if candidates else None

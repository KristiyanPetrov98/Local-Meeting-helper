"""Bounded, media-in-memory-only audio primitives, independent of GPU libraries."""
import base64
import math
import sys
from array import array

RATE = 16000


def packet(message):
    source = message.get('source')
    sequence = message.get('sequence')
    start = message.get('start')
    if source not in ('local','remote') or type(sequence) is not int or sequence < 0:
        raise ValueError('invalid_audio_header')
    if type(start) not in (int,float) or not math.isfinite(start) or start < 0:
        raise ValueError('invalid_audio_timestamp')
    pcm = base64.b64decode(message['pcm'], validate=True)
    count = message.get('samples')
    if message.get('sample_rate') != RATE or type(count) is not int or not 0 < count <= 3200 or len(pcm) != count*4:
        raise ValueError('invalid_audio_size')
    samples = array('f'); samples.frombytes(pcm)
    if sys.byteorder != 'little': samples.byteswap()
    if any(not math.isfinite(x) or abs(x)>1.01 for x in samples):
        raise ValueError('invalid_audio_sample')
    return source, sequence, float(start), pcm


class Chunks:
    def __init__(self, seconds=4, overlap_seconds=0, silence_seconds=None, min_seconds=1):
        if not 0 <= overlap_seconds < seconds: raise ValueError("invalid_chunk_overlap")
        self.overlap = int(overlap_seconds*RATE)*4
        self.target = int(seconds*RATE)*4
        self.pending = bytearray()
        self.start = 0.
        self.expected = None
        self.sequence = None
        if silence_seconds is not None and not 0<min_seconds<=seconds:raise ValueError('invalid_endpoint_minimum')
        if silence_seconds is not None and silence_seconds<=0:raise ValueError('invalid_endpoint_silence')
        self.silence_target=int(silence_seconds*RATE)*4 if silence_seconds is not None else None
        self.minimum=int(min_seconds*RATE)*4;self.quiet=0;self.voiced=False

    def push(self, sequence, start, pcm, *, audible=None):
        gap = (self.sequence is not None and sequence != self.sequence+1) or (self.expected is not None and abs(start-self.expected)>.35)
        if gap:self.pending.clear();self.quiet=0;self.voiced=False
        if not self.pending: self.start = start
        self.expected = start+len(pcm)/4/RATE
        self.sequence = sequence
        self.pending.extend(pcm)
        if self.silence_target is not None:
            if audible is None:
                samples=array('f');samples.frombytes(pcm)
                audible=bool(samples) and sum(x*x for x in samples)/len(samples)>=1e-7
            if audible:self.voiced=True;self.quiet=0
            else:self.quiet+=len(pcm)
        result = []
        while len(self.pending)>=self.target:
            result.append((self.start,bytes(self.pending[:self.target])))
            del self.pending[:self.target-self.overlap]
            self.start += (self.target-self.overlap)/4/RATE
        if self.silence_target is not None and self.voiced and self.quiet>=self.silence_target and len(self.pending)>=self.minimum:
            result.append(self.flush())
        return result, bool(gap)

    def flush(self):
        if not self.pending: return None
        result = self.start, bytes(self.pending)
        self.pending.clear()
        self.voiced=False;self.quiet=0
        return result


def overlap(a,b,c,d):
    return max(0,min(b,d)-max(a,c))


class SpeakerStitcher:
    """Stable provisional IDs through temporal overlap, never inferred human names."""
    def __init__(self):
        self.previous = []
        self.next_id = 1

    def assign(self, turns, offset):
        candidates = {}
        for turn in turns:
            for old in self.previous:
                score = overlap(turn['start']+offset,turn['end']+offset,old['start'],old['end'])
                key = turn['label'],old['speaker']
                candidates[key] = candidates.get(key,0)+score
        mapping, used = {},set()
        for (label,speaker),score in sorted(candidates.items(),key=lambda x:x[1],reverse=True):
            if score>.3 and label not in mapping and speaker not in used:
                mapping[label]=speaker;used.add(speaker)
        for label in dict.fromkeys(t['label'] for t in turns):
            if label not in mapping:
                mapping[label]=f'speaker-{self.next_id}';self.next_id+=1
        result = [{'start':t['start']+offset,'end':t['end']+offset,'speaker':mapping[t['label']]} for t in turns]
        self.previous = result
        return result

"""Short-phrase collection measurements, not real Whisper speed or quality claims."""
from array import array
from pm_copilot.audio import Chunks,RATE

def test_spoken_phrase_submits_after_quiet_before_four_second_batch():
    chunks=Chunks(overlap_seconds=.5,silence_seconds=.6)
    voice=array('f',[.1]*1600).tobytes();quiet=bytes(6400);result=[]
    for index in range(18):
        output,gap=chunks.push(index,index*.1,voice if index<12 else quiet)
        assert not gap;result.extend(output)
        if index<17:assert not output
    assert len(result)==1 and result[0][0]==0
    assert len(result[0][1])/4/RATE==1.8
    assert not chunks.pending

def test_silence_does_not_create_short_phantom_speech_chunks():
    chunks=Chunks(silence_seconds=.6);result=[]
    for index in range(30):result.extend(chunks.push(index,index*.1,bytes(6400))[0])
    assert not result

def test_gap_discards_endpoint_history_and_continuous_speech_keeps_context():
    chunks=Chunks(overlap_seconds=.5,silence_seconds=.6);voice=array('f',[.1]*1600).tobytes()
    for index in range(10):assert not chunks.push(index,index*.1,voice)[0]
    output,gap=chunks.push(20,2.,bytes(6400));assert gap and not output
    for index in range(21,50):assert not chunks.push(index,index*.1,bytes(6400))[0]
    chunks=Chunks(overlap_seconds=.5,silence_seconds=.6);result=[]
    for index in range(40):result.extend(chunks.push(index,index*.1,voice)[0])
    assert len(result)==1 and len(result[0][1])/4/RATE==4

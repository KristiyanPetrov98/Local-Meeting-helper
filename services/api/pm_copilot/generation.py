import re
from .ollama_http import ollama_client
from .briefing import MODEL,CONTEXT,MAX_OUTPUT_TOKENS,BriefingInvalid
from .resources import PROFILE


class GenerationUnavailable(RuntimeError):pass


class OllamaGeneration:
    model=MODEL
    async def _call(self,path,body=None):
        try:
            import httpx
            async with ollama_client(timeout=55) as client:
                response=await client.request('GET' if body is None else 'POST','http://127.0.0.1:11434/api/'+path,json=body)
                if response.status_code!=200:raise GenerationUnavailable('Local Ollama rejected the generation request; check model/runtime compatibility')
                return response.json()
        except GenerationUnavailable:raise
        except Exception as exc:raise GenerationUnavailable('Local Ollama is unavailable. Install '+self.model+'; no cloud fallback is enabled.') from exc

    async def identity(self):
        payload=await self._call('tags')
        try:
            found=next(m for m in payload['models'] if m.get('name')==self.model or m.get('model')==self.model)
            digest=found['digest']
            if not isinstance(digest,str) or not re.fullmatch(r'(?:sha256:)?[a-fA-F0-9]{64}',digest):raise ValueError('digest')
            return digest
        except (KeyError,TypeError,ValueError,StopIteration) as exc:
            raise GenerationUnavailable('The exact primary Ollama model is required: '+self.model) from exc

    async def generate(self,messages,schema):
        return await self._generate(messages,schema,MAX_OUTPUT_TOKENS)

    async def observe(self,messages,schema,image=None):
        if image:
            import base64
            messages=[*messages[:-1],{**messages[-1],'images':[base64.b64encode(image).decode()]}]
        return await self._generate(messages,schema,384)

    async def _generate(self,messages,schema,output_tokens):
        profile=PROFILE.get()
        options={'num_ctx':CONTEXT,'num_predict':output_tokens,'temperature':0}
        if profile=='cpu':options.update(num_gpu=0,num_thread=4)
        payload=await self._call('chat',{'model':self.model,'messages':messages,'format':schema,'stream':False,
            'keep_alive':0 if profile=='cpu' else '5m','options':options})
        message=payload.get('message',{})
        if payload.get('done') is not True or payload.get('done_reason')=='length' or message.get('role')!='assistant' or message.get('tool_calls'):
            raise BriefingInvalid('Ollama did not return a complete, tool-free answer')
        content=message.get('content')
        count=payload.get('prompt_eval_count')
        output_count=payload.get('eval_count')
        if (not isinstance(content,str) or len(content.encode())>20000 or type(count) is not int or
            not 0<count<=CONTEXT-output_tokens-128 or type(output_count) is not int or not 0<output_count<=output_tokens):
            raise BriefingInvalid('Generation exceeded the validated context/output bounds')
        metrics={key:payload.get(key) for key in ('prompt_eval_count','eval_count','load_duration','prompt_eval_duration','eval_duration','total_duration')}
        if any(value is not None and (type(value) is not int or value<0) for value in metrics.values()):
            raise BriefingInvalid('Ollama returned invalid performance measurements')
        return content,metrics

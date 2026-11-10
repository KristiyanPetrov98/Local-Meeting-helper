from typing import Literal
from pydantic import BaseModel,ConfigDict
from .store import DomainError

class SharingChoice(BaseModel):
    model_config=ConfigDict(extra='forbid')
    mode:Literal['unknown','none','tab','broader']='unknown'
    acknowledged:bool=False
    preview_confirmed:bool=False

class Sharing:
    def __init__(self):self.choice=SharingChoice()
    def status(self):
        return {**self.choice.model_dump(),'mini_allowed':self.choice.mode in ('none','tab') and self.choice.acknowledged,
                'capture_exclusion_verified':False,'meet_picker_enforced':False}
    def update(self,choice):
        if choice.mode in ('none','tab') and not choice.acknowledged:raise DomainError('Acknowledge the declared sharing mode first',422)
        self.choice=choice

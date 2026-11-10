import {describe,it,expect,vi} from 'vitest';
import {Shortcuts,validAccelerator} from '../../apps/desktop/src/shortcut';
import {fit} from '../../apps/desktop/src/bounds';
describe('global shortcuts',()=>{
 it('rejects ambiguous or unrestricted commands',()=>{
   for(const key of ['Space','Control+Control+P','Super+','Control+Shift+;','Control+P;rm','Control+F25'])expect(validAccelerator(key)).toBe(false);
   expect(validAccelerator('Control+Shift+Space')).toBe(true);
 });
 it('retains old registration on conflict and only unregisters after replacement',()=>{
   const register=vi.fn().mockReturnValueOnce(true).mockReturnValueOnce(false).mockReturnValueOnce(true);
   const unregister=vi.fn(),handler=vi.fn(),manager=new Shortcuts({register,unregister},handler);
   manager.set('Control+Shift+Space');
   expect(()=>manager.set('Control+Alt+P')).toThrow('unavailable');
   expect(manager.current).toBe('Control+Shift+Space');expect(unregister).not.toHaveBeenCalled();
   manager.set('Control+Shift+P');expect(unregister).toHaveBeenCalledWith('Control+Shift+Space');
   register.mock.calls[2][1]();expect(handler).toHaveBeenCalledOnce();
   manager.clear();expect(manager.current).toBeNull();
 });
});
describe('multi-monitor companion recovery',()=>{
 it('restores a companion from a disconnected display',()=>{
  expect(fit({x:2200,y:1200,width:360,height:350},[{x:0,y:0,width:1920,height:1080}])).toEqual({x:1560,y:730,width:360,height:350});
 });
 it('keeps negative-coordinate secondary monitors and clamps edges',()=>{
  expect(fit({x:-100,y:100,width:360,height:350},[{x:0,y:0,width:1920,height:1080},{x:-1280,y:0,width:1280,height:1024}]).x).toBe(-360);
 });
});

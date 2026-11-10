export interface ShortcutDriver {
  register(key:string, callback:()=>void): boolean;
  unregister(key:string): void;
}
export function validAccelerator(key:unknown): key is string {
  if (typeof key!=='string' || key.length>80) return false;
  const parts=key.split('+');
  const modifiers=parts.slice(0,-1);
  return modifiers.length>0 && new Set(modifiers).size===modifiers.length
    && modifiers.every(x=>['Control','Alt','Shift','Super'].includes(x))
    && /^(Space|[A-Z0-9]|F([1-9]|1[0-9]|2[0-4]))$/.test(parts.at(-1)!);
}
export class Shortcuts {
  current:string|null=null;
  constructor(private driver:ShortcutDriver, private callback:()=>void){}
  set(key:string) {
    if (!validAccelerator(key)) throw new Error('Use modifiers plus a letter, number, Space or F1–F24');
    if (this.current===key) return;
    if (!this.driver.register(key,this.callback)) throw new Error('Shortcut is unavailable or already in use. Choose another combination.');
    const old=this.current;
    this.current=key;
    if (old) this.driver.unregister(old);
  }
  clear(){if(this.current)this.driver.unregister(this.current);this.current=null;}
}

export type Rect={x:number;y:number;width:number;height:number};
export function fit(bounds:Rect, displays:Rect[]):Rect {
  const area=displays.find(d=>bounds.x>=d.x && bounds.x<d.x+d.width && bounds.y>=d.y && bounds.y<d.y+d.height) ?? displays[0];
  const width=Math.min(bounds.width,area.width), height=Math.min(bounds.height,area.height);
  return {...bounds,width,height,x:Math.max(area.x,Math.min(bounds.x,area.x+area.width-width)),y:Math.max(area.y,Math.min(bounds.y,area.y+area.height-height))};
}

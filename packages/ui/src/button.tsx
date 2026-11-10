// shadcn/ui-style Button, MIT pattern: Radix Slot + CVA + Tailwind utilities.
import * as React from 'react';
import {Slot} from '@radix-ui/react-slot';
import {cva,type VariantProps} from 'class-variance-authority';
import {clsx} from 'clsx';
import {twMerge} from 'tailwind-merge';
const variants=cva('inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-300 disabled:pointer-events-none disabled:opacity-40',{
  variants:{variant:{default:'bg-[#bce8c1] text-[#142a1c] hover:bg-[#d3f5d7]',secondary:'bg-white/7 text-[#e1e8e2] hover:bg-white/12 border border-white/10',ghost:'text-[#afbeb3] hover:text-white hover:bg-white/5',danger:'bg-red-400/10 text-red-200 border border-red-300/20 hover:bg-red-400/20'}},defaultVariants:{variant:'default'}
});
export function Button({className,variant,asChild=false,...props}:React.ComponentProps<'button'>&VariantProps<typeof variants>&{asChild?:boolean}){
 const Comp=asChild?Slot:'button';return <Comp className={twMerge(clsx(variants({variant}),className))} {...props}/>;
}

import {describe,it,expect} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {RiskIndicator} from '../../apps/web/src/ScreenPanel';
import type {Snapshot} from '../../packages/contracts/src';

describe('potential-risk presentation',()=>{
 it('keeps untrusted evidence escaped and labels findings as potential concerns',()=>{
  const state={screen:{risk_count:1,analysis_deferred:false,risks:[{kind:'security',text:'A potential issue: <script>alert(1)</script>',screen_evidence:false,segments:[{id:9,text:'<img src=x onerror=alert(1)>'}],citations:[{citation_id:'fixture',filename:'security.md',quote:'<b>untrusted document text</b>'}]}]}} as unknown as Snapshot;
  const html=renderToStaticMarkup(createElement(RiskIndicator,{state}));
  expect(html).toContain('potential concern');expect(html).toContain('Transcript #');expect(html).toContain('security.md');
  expect(html).not.toContain('<script>');expect(html).not.toContain('<img');expect(html).toContain('&lt;script&gt;');expect(html).toContain('&lt;b&gt;');
 });
 it('does not interpret zero current findings as proof of safety',()=>{
  const state={screen:{risk_count:0,risks:[],analysis_deferred:true}} as unknown as Snapshot;
  const html=renderToStaticMarkup(createElement(RiskIndicator,{state}));
  expect(html).toContain('deferred');expect(html).toContain('does not establish that the project is risk-free');
 });
});

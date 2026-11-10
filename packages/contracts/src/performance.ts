import type {Snapshot} from './index';
export function performanceReport(state:Snapshot){
 return {schema:1,created_at:new Date().toISOString(),audio_state:state.meeting.state,counts:state.meeting.counts,queue_depth:state.meeting.queue_depth,
  actual_asr_device:state.meeting.counts.asr_cuda_active===undefined?'not measured':state.meeting.counts.asr_cuda_active?'cuda':'cpu',
  gpus:state.resources.gpus.map(g=>({name:g.name,total_mib:g.total_mib,free_mib:g.free_mib})),active_profile:state.resources.profile,
  scope:'Local timing and hardware metadata only; no transcript, audio, frames or credentials. Not a qualification verdict.'};
}

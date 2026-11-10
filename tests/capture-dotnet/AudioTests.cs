using NAudio.Wave;
using NAudio.Wave.SampleProviders;
using Xunit;
public class AudioTests {
 sealed class Samples(float[] samples, int channels, int rate) : ISampleProvider {
  int position;
  public WaveFormat WaveFormat {get;} = WaveFormat.CreateIeeeFloatWaveFormat(rate,channels);
  public int Read(float[] buffer,int offset,int count) {int n=Math.Min(count,samples.Length-position); Array.Copy(samples,position,buffer,offset,n);position+=n;return n;}
 }
 [Fact] public void DownmixAveragesChannelsWithoutCrossingFrames() {
  var mono=new Downmix(new Samples([1,-1,.4f,.8f],2,48000));var output=new float[2];
  Assert.Equal(2,mono.Read(output,0,2));Assert.Equal(0,output[0]);Assert.InRange(output[1],.599f,.601f);
  Assert.Equal(0,mono.Read(output,0,2));
 }
 [Fact] public void ResamplerProducesBoundedFiniteMonoOutput() {
  var input=Enumerable.Range(0,48000).Select(i=>(float)(.3*Math.Sin(i*.1))).ToArray();
  var resampler=new WdlResamplingSampleProvider(new Downmix(new Samples(input,1,48000)),16000);
  var output=new float[20000];var n=resampler.Read(output,0,output.Length);
  Assert.InRange(n,15990,16010);Assert.All(output.Take(n),v=>Assert.True(float.IsFinite(v)&&Math.Abs(v)<=1));
 }
}

public class NotificationTests {
 [Fact] public void OnlyMultimediaDefaultChangesTriggerRecovery() {
  var changes=new List<NAudio.CoreAudioApi.DataFlow>();
  var observer=new EndpointNotifications(changes.Add);
  observer.OnDefaultDeviceChanged(NAudio.CoreAudioApi.DataFlow.Render,NAudio.CoreAudioApi.Role.Communications,"fixture");
  Assert.Empty(changes);
  observer.OnDefaultDeviceChanged(NAudio.CoreAudioApi.DataFlow.Render,NAudio.CoreAudioApi.Role.Multimedia,"fixture");
  Assert.Equal([NAudio.CoreAudioApi.DataFlow.Render],changes);
 }
}

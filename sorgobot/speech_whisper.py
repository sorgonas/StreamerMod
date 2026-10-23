"""Local Whisper utterance decoding and bounded microphone segmentation."""
import collections,math,queue,threading,time,unicodedata


def normalized(text,case_sensitive=False):
 chars=[];ends=[]
 for index,char in enumerate(text):
  value=unicodedata.normalize('NFKC',char)
  if not case_sensitive:value=value.casefold()
  for c in value:
   if c.isalnum():chars.append(c);ends.append(index+1)
   elif chars and chars[-1]!=' ':chars.append(' ');ends.append(index+1)
 if chars and chars[-1]==' ':chars.pop();ends.pop()
 return ''.join(chars),ends


def canonical(text):return normalized(text)[0]


class Segmenter:
 """30 ms PCM frames, 300 ms preroll, 900 ms end pause; bounded to 12 s."""
 def __init__(self,vad):
  self.vad=vad;self.before=collections.deque(maxlen=10);self.votes=collections.deque(maxlen=5);self.frames=[];self.silence=0;self.voiced=0
 def feed(self,frame):
  voiced=self.vad.is_speech(frame,16000);self.votes.append(voiced)
  if not self.frames:
   self.before.append(frame)
   if sum(self.votes)<3:return None
   self.frames=list(self.before);self.before.clear();self.voiced=sum(self.votes);self.silence=0
  else:self.frames.append(frame);self.voiced+=int(voiced);self.silence=0 if voiced else self.silence+1
  if self.silence<30 and len(self.frames)<400:return None
  audio=b''.join(self.frames);valid=self.voiced>=8
  self.frames=[];self.votes.clear();self.voiced=0;self.silence=0
  return audio if valid else None


DEFAULT_VOCABULARY='StreamerMod'

def decode(model,audio,language,grammar=None,vocabulary=DEFAULT_VOCABULARY):
 import numpy as np
 samples=np.frombuffer(audio,dtype='<i2').astype(np.float32)/32768
 if not len(samples) or np.max(np.abs(samples))<.002:return None
 # Bounded gain helps quiet microphones without amplifying near-silence indefinitely.
 rms=float(np.sqrt(np.mean(samples*samples)));samples=np.clip(samples*min(4,.08/max(rms,.001)),-1,1)
 segments,_=model.transcribe(samples,language=language,beam_size=5,temperature=0,condition_on_previous_text=False,word_timestamps=True,vad_filter=False,no_speech_threshold=.6,log_prob_threshold=-1.0,compression_ratio_threshold=2.4,hotwords=vocabulary.strip() or None)
 parts=[];probabilities=[]
 for seg in segments:
  if seg.no_speech_prob>.6 or seg.avg_logprob< -1.0 or seg.compression_ratio>2.4:continue
  parts.append(seg.text.strip());probabilities.extend(w.probability for w in (seg.words or []))
 text=' '.join(parts).strip()
 if not text:return None
 confidence=round(100*sum(probabilities)/len(probabilities)) if probabilities else 0
 if grammar:
  choices={canonical(p):p for p in grammar if p!='[unk]'}
  text=choices.get(canonical(text))
  if not text:return None
 return {'text':text[:10000],'confidence':max(0,min(100,confidence))}


def run(args,emit):
 import os,subprocess,wave
 import webrtcvad
 from faster_whisper import WhisperModel
 # Heartbeats keep the owning runtime responsive even on older CPUs during model load.
 done=threading.Event()
 def heartbeat():
  while not done.wait(1):emit('heartbeat')
 beat=threading.Thread(target=heartbeat,daemon=True);beat.start()
 process=None;stop=threading.Event();decoder=None
 try:
  import json,sys
  grammar=json.loads(sys.stdin.readline(65536)) if args.grammar_stdin else json.loads(args.grammar) if args.grammar else None
  if grammar is not None and (not isinstance(grammar,list) or not all(isinstance(p,str) for p in grammar)):raise ValueError('Invalid grammar')
  model=WhisperModel(args.model,device='cpu',compute_type='int8',cpu_threads=3,num_workers=1,local_files_only=True)
  if args.wav:
   with wave.open(args.wav,'rb') as wav:
    if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate())!=(1,2,16000):raise ValueError('PCM WAV 16 kHz mono required')
    audio=wav.readframes(wav.getnframes())
   emit('ready');result=decode(model,audio,args.language,grammar,getattr(args,'vocabulary',DEFAULT_VOCABULARY))
   if result:emit('final',**result)
   return
  pending=queue.Queue(maxsize=1)
  def transcribe():
   try:
    while not stop.is_set():
     try:audio=pending.get(timeout=.2)
     except queue.Empty:continue
     if stop.is_set():return
     started=time.monotonic();emit('processing',text='Sprache wird erkannt …')
     result=decode(model,audio,args.language,grammar,getattr(args,'vocabulary',DEFAULT_VOCABULARY))
     if not stop.is_set():
      if result:emit('final',**result,latencyMs=round((time.monotonic()-started)*1000))
      emit('processing',text='')
   except Exception as exc:
    emit('error',message='Whisper-Erkennung fehlgeschlagen ('+type(exc).__name__+').');stop.set()
  decoder=threading.Thread(target=transcribe,daemon=True);decoder.start()
  command=['parec','--raw','--format=s16le','--rate=16000','--channels=1','--latency-msec=100','--client-name=StreamerMod Voice','--stream-name=StreamerMod Speech Recognition']
  if args.device!='@default':command.append('--device='+args.device)
  process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=dict(os.environ,LC_ALL='C.UTF-8'))
  segmenter=Segmenter(webrtcvad.Vad(2));active=False;last=0
  while not stop.is_set():
   frame=process.stdout.read(960)
   if len(frame)!=960:raise RuntimeError('Audio source disconnected')
   if not active:emit('ready');active=True
   audio=segmenter.feed(frame)
   if audio:
    try:pending.put_nowait(audio)
    except queue.Full:
     # Drop this whole utterance instead of accumulating actions delayed by minutes.
     emit('busy',message='Erkennung ausgelastet; bitte nach der laufenden Erkennung erneut sprechen.')
   now=time.monotonic()
   if now-last>.25:
    import array
    samples=array.array('h',frame)
    if sys.byteorder!='little':samples.byteswap()
    level=min(100,round(math.sqrt(sum(x*x for x in samples)/len(samples))/32768*100))
    emit('meter',level=level);last=now
 finally:
  stop.set();done.set()
  if process:
   if process.poll() is None:process.terminate()
   try:process.wait(timeout=2)
   except subprocess.TimeoutExpired:process.kill();process.wait()

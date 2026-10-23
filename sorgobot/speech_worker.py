"""Isolated Vosk decoder. Audio stays in memory; stdout carries bounded JSON events."""
import argparse,array,json,math,os,signal,subprocess,sys,time,wave

_output_lock=__import__("threading").Lock()
def emit(kind,**value):
 with _output_lock:print(json.dumps(dict(kind=kind,**value),ensure_ascii=False),flush=True)

def result(value):
 value=json.loads(value);text=str(value.get('text','')).strip();words=value.get('result',[])
 confidence=sum(float(w.get('conf',0)) for w in words)/len(words) if words else 0
 if text and '[unk]' not in text:emit('final',text=text[:10000],confidence=round(max(0,min(1,confidence))*100))

def run(args):
 from vosk import Model,KaldiRecognizer,SetLogLevel
 SetLogLevel(-1);model=Model(args.model)
 grammar=json.loads(sys.stdin.readline(65536)) if args.grammar_stdin else json.loads(args.grammar) if args.grammar else None
 if grammar is not None and (not isinstance(grammar,list) or not all(isinstance(v,str) for v in grammar)):raise ValueError('Ungültiges Command-Vokabular')
 rec=KaldiRecognizer(model,16000,json.dumps(grammar,ensure_ascii=False)) if grammar else KaldiRecognizer(model,16000);rec.SetWords(True)
 process=None;stream=None
 try:
  if args.wav:
   stream=wave.open(args.wav,'rb')
   if (stream.getnchannels(),stream.getsampwidth(),stream.getframerate())!=(1,2,16000):raise ValueError('PCM WAV 16 kHz mono erforderlich')
  else:
   command=['parec','--raw','--format=s16le','--rate=16000','--channels=1','--latency-msec=100','--client-name=StreamerMod Voice','--stream-name=StreamerMod Speech Recognition']
   if args.device!='@default':command.append('--device='+args.device)
   process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=dict(os.environ,LC_ALL='C.UTF-8'))
  active=False;last=0
  while True:
   chunk=stream.readframes(1600) if stream else process.stdout.read(3200)
   if not chunk:break
   if not active:emit('ready');active=True
   if rec.AcceptWaveform(chunk):result(rec.Result())
   now=time.monotonic()
   if now-last>=.25:
    samples=array.array('h',chunk[:len(chunk)//2*2])
    if sys.byteorder!='little':samples.byteswap()
    level=min(100,round(math.sqrt(sum(x*x for x in samples)/max(1,len(samples)))/32768*100))
    emit('partial',text=str(json.loads(rec.PartialResult()).get('partial',''))[:1000],level=level);last=now
  if stream:result(rec.FinalResult())
  else:raise RuntimeError('Audioeingang wurde geschlossen oder ist nicht verfügbar')
 finally:
  if stream:stream.close()
  if process:
   if process.poll() is None:process.terminate()
   try:process.wait(timeout=2)
   except subprocess.TimeoutExpired:process.kill();process.wait()

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--engine',choices=['vosk','whisper-small','whisper-base'],default='vosk');parser.add_argument('--language',choices=['de','en'],default='de');parser.add_argument('--model',required=True);parser.add_argument('--device',default='@default');parser.add_argument('--wav');parser.add_argument('--grammar');parser.add_argument('--grammar-stdin',action='store_true');parser.add_argument('--options-stdin',action='store_true');args=parser.parse_args()
 def terminate(*_):raise SystemExit(0)
 signal.signal(signal.SIGTERM,terminate)
 try:
  if args.options_stdin:
   options=json.loads(sys.stdin.readline(65536))
   if not isinstance(options,dict) or set(options)!={'grammar','vocabulary'}:raise ValueError('Invalid recognition options')
   if not isinstance(options['vocabulary'],str) or len(options['vocabulary'])>1000 or any(ord(c)<32 for c in options['vocabulary']):raise ValueError('Invalid vocabulary')
   args.vocabulary=options['vocabulary'];args.grammar=json.dumps(options['grammar']) if options['grammar'] is not None else None;args.grammar_stdin=False
  if args.engine=='vosk':run(args)
  else:
   from .speech_whisper import run as whisper
   whisper(args,emit)
 except (Exception,KeyboardInterrupt) as exc:
  emit('error',message='Spracherkennung konnte nicht gestartet oder fortgesetzt werden ('+type(exc).__name__+').');return 1
 return 0

if __name__=='__main__':sys.exit(main())

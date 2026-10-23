"""Local OpenCV camera with original, stylized replacement effects.

Frames stay on the local machine. Uses a bundled Haar face detector, no cloud API.
These are deliberately new illustrations, not reproductions of proprietary Lenses.
"""
import threading
import time

EFFECTS = {'Ghul', 'Traurig', 'Rasiert', 'Glatze', 'Alt', 'Anime', 'Uncle', 'Gremlin', 'Lost', 'IQ'}


def render(frame, faces, effect, cv2, np):
    image = frame.copy()
    if effect in ('Ghul', 'Gremlin'):
        tint = np.full_like(image, (35, 95, 25))
        image = cv2.addWeighted(image, .78, tint, .22, 0)
    elif effect in ('Traurig', 'Alt'):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        image = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    elif effect == 'Anime':
        smooth = cv2.bilateralFilter(image, 9, 75, 75)
        edges = cv2.adaptiveThreshold(cv2.medianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 7),255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY,9,5)
        image = cv2.bitwise_and(smooth, smooth, mask=edges)
    for x, y, w, h in faces:
        x,y,w,h = map(int,(x,y,w,h))
        point = lambda a,b: (int(x+w*a), int(y+h*b))
        scale = max(.4,w/210)
        if effect in ('Ghul','Gremlin'):
            cv2.ellipse(image,point(.3,.42),(int(w*.12),int(h*.06)),0,0,360,(15,15,100),-1)
            cv2.ellipse(image,point(.7,.42),(int(w*.12),int(h*.06)),0,0,360,(15,15,100),-1)
            for cx in (.38,.62):
                cv2.fillPoly(image,[np.array([point(cx-.06,.72),point(cx+.06,.72),point(cx,.91)])],(235,240,230))
            if effect == 'Gremlin':
                for side in (-.1,1.1):
                    cv2.fillPoly(image,[np.array([point(side,.3),point(side + (-.3 if side<0 else .3),.15),point(side,.65)])],(65,135,75))
        elif effect == 'Traurig':
            for cx in (.32,.68):
                cv2.ellipse(image,point(cx,.59),(max(2,int(w*.04)),int(h*.1)),0,0,360,(245,160,70),-1)
        elif effect == 'Glatze':
            skin = tuple(int(v) for v in frame[min(y+h//2,frame.shape[0]-1),min(x+w//2,frame.shape[1]-1)])
            cv2.ellipse(image,point(.5,.12),(int(w*.52),int(h*.35)),0,180,360,skin,-1)
            cv2.ellipse(image,point(.5,.12),(int(w*.52),int(h*.35)),0,180,360,(125,115,105),2)
        elif effect == 'Rasiert':
            # Stylized shaving-foam mask and razor illustration, not beard removal.
            cv2.ellipse(image,point(.5,.8),(int(w*.4),int(h*.2)),0,0,180,(235,240,245),-1)
            cv2.line(image,point(.87,.7),point(1.05,1.05),(190,190,190),max(3,int(w*.035)))
            cv2.line(image,point(.74,.66),point(.97,.76),(65,75,90),max(5,int(w*.06)))
        elif effect == 'Alt':
            for cy in (.22,.27,.32):
                cv2.ellipse(image,point(.5,cy),(int(w*.25),max(2,int(h*.025))),0,0,180,(80,80,80),1)
            for cx in (.21,.79):
                cv2.line(image,point(cx,.5),point(cx+(.08 if cx<.5 else -.08),.54),(65,65,65),2)
            cv2.ellipse(image,point(.5,.1),(int(w*.5),int(h*.2)),0,180,350,(210,210,210),max(4,int(w*.06)))
        elif effect == 'Uncle':
            for cx in (.39,.61):
                cv2.ellipse(image,point(cx,.68),(int(w*.15),int(h*.045)),15 if cx<.5 else -15,0,360,(25,20,20),-1)
            cv2.rectangle(image,point(.17,-.18),point(.83,.02),(40,25,20),-1)
            cv2.line(image,point(.02,.02),point(.98,.02),(40,25,20),max(4,int(h*.06)))
        elif effect in ('Lost','IQ'):
            label = '???' if effect == 'Lost' else 'IQ 9000'
            cv2.putText(image,label,point(.08,-.12),cv2.FONT_HERSHEY_DUPLEX,scale,(100,245,185),2,cv2.LINE_AA)
    return image


class Camera:
    def __init__(self, device=0):
        self.device = device
        self.frame = None
        self.effect = ''
        self.expires = 0
        self.error = ''
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def activate(self, effect, seconds=300):
        if effect not in EFFECTS:
            raise ValueError('Unbekannter Kameraeffekt')
        if self.error or self.frame is None:
            raise RuntimeError(self.error or 'Kamera liefert noch kein Bild')
        self.effect, self.expires = effect, time.monotonic() + min(600, max(1, seconds))

    def run(self):
        cap = None
        try:
            import cv2
            import numpy as np
            cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            cap = cv2.VideoCapture(self.device)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            if not cap.isOpened():
                raise RuntimeError('Kamera kann nicht geöffnet werden; camera_device prüfen')
            while not self.stop.is_set():
                ok, frame = cap.read()
                if not ok: raise RuntimeError('Kamerabild unterbrochen')
                effect = self.effect if time.monotonic() < self.expires else ''
                faces = cascade.detectMultiScale(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),1.2,5,minSize=(60,60)) if effect else []
                frame = render(frame,faces,effect,cv2,np)
                ok, jpeg = cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,80])
                if ok: self.frame = jpeg.tobytes()
                self.stop.wait(1/25)
        except Exception as exc:
            self.error = str(exc)
        finally:
            if cap is not None: cap.release()
            self.frame = None

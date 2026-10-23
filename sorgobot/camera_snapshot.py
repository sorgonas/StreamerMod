"""One local camera frame in a killable process for bounded desktop previews."""
import sys
import cv2

def main():
    value=sys.argv[1];device=int(value) if value.isdigit() else value
    capture=cv2.VideoCapture(device,cv2.CAP_V4L2)
    try:
        if not capture.isOpened():raise RuntimeError('Kamera kann nicht geöffnet werden')
        ok,frame=capture.read()
        if not ok:raise RuntimeError('Kamera liefert kein Bild')
        ok,image=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,80])
        if not ok:raise RuntimeError('Kamerabild kann nicht dekodiert werden')
        sys.stdout.buffer.write(image.tobytes())
    finally:capture.release()

if __name__=='__main__':main()

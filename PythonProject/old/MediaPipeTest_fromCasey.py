import cv2
import mediapipe as mp
from pythonosc.udp_client import SimpleUDPClient

LISAIP = "127.0.0.1"
LISAPORT = 8880
LISAClient = SimpleUDPClient(LISAIP,LISAPORT)

def main():

    #address for the OCP Command
    src1Pan = "/ext/scr/1/p"


    mpFaceDetection = mp.solutions.face_detection
    mpDrawing = mp.solutions.drawing_utils

    faceDetection = mpFaceDetection.FaceDetection(
        model_selection=0,
        min_detection_confidence=0.5
    )

    cap = cv2.VideoCapture(0)

    while True:
        success, img = cap.read()
        imgRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = faceDetection.process(imgRGB)

        if results.detections:
            myDetection = results.detections[0]
            conf = myDetection.score
            print(conf)
            mpDrawing.draw_detection(img, myDetection)

        cv2.imshow("myFace", img)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

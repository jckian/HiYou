#   WhisperClass + Audio_playSound
#   WHISPERCLASS duration = 5sec

#from Audio_prerecordReaperLoad import run_complete_workflow
from Audio_playSound import run_complete_workflow
import time
import os
import  WhisperClass


class WhisperCommand:
    def __init__(self):
        self.myWhisper = WhisperClass.WhisperAgent()
        self.base_folder = os.path.join(os.path.dirname(__file__), "..", "YenhsingDeyingAudio", "dialogue")

    def whisperCall(self):
        whisperOut = self.myWhisper.listen()
        #if len(whisperOut) < 5:
        #    whisperOut = "a conversation about current news topics"
        print(whisperOut)
        return whisperOut

    def play_and_wait(self,filename, duration):
        file_path = os.path.join(self.base_folder, filename)

        run_complete_workflow(file_path)

        time.sleep(duration)


    def run_command_center(self):
        print("Command Center Started")

        #   duration - 5sec (lag)
        #self.play_and_wait("0-hihihi.wav",1)
        #print("play 0")
        self.play_and_wait("1-comehereQ1.wav",8)         # 16s
        print("play 1")

        self.whisperCall()

        self.play_and_wait("2-Q2.wav",6)
        print("play 2")
        self.whisperCall()

        self.play_and_wait("3-Q3.wav",6)
        print("play 3")
        self.whisperCall()

        self.play_and_wait("4-profile.wav", 8)
        print("play 4")
        self.play_and_wait("5-matching.wav", 0)
        print("play 5")
        #self.play_and_wait("6-matched.wav", 3)
        #print("play 6")




"""---------------------------------------------------------------------
def play_and_wait(filename, extra_pause=True):
    file_path = os.path.join(base_folder, filename)

    run_complete_workflow(file_path)

    with wave.open(file_path, 'rb') as f:
        duration = f.getnframes() / float(f.getframerate())

    wait_time = duration + pause_duration if extra_pause else duration
    time.sleep(wait_time)
"""
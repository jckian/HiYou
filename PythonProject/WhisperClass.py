# ! python3.7

import argparse
import os
import numpy as np
import speech_recognition as sr
import whisper
import torch
import time
from datetime import datetime, timedelta
from queue import Queue
from time import sleep
from sys import platform


class WhisperAgent:
    def __init__(self):

        parser = argparse.ArgumentParser()
        parser.add_argument("--model", default="base", help="Model to use",        #   default="turbo"
                            choices=["tiny", "base", "small", "medium", "large"])
        parser.add_argument("--energy_threshold", default=500,
                            help="Energy level for mic to detect.", type=int)
        parser.add_argument("--record_timeout", default=8,
                            help="How real time the recording is in seconds.", type=float)
        parser.add_argument("--phrase_timeout", default=10,
                            help="How much empty space between recordings before we "
                                 "consider it a new line in the transcription.", type=float)

        self.args = parser.parse_args()

        # The last time a recording was retrieved from the queue.
        self.phrase_time = None
        # Thread safe Queue for passing data from the threaded recording callback.
        self.data_queue = Queue()
        # We use SpeechRecognizer to record our audio because it has a nice feature where it can detect when speech ends.
        self.recorder = sr.Recognizer()
        self.recorder.energy_threshold = self.args.energy_threshold
        # Definitely do this, dynamic energy compensation lowers the energy threshold dramatically to a point where the SpeechRecognizer never stops recording.
        self.recorder.dynamic_energy_threshold = False

        # Important for linux users.
        # Prevents permanent application hang and crash by using the wrong Microphone


        self.source = sr.Microphone(sample_rate=16000)

        # Load / Download model
        model = self.args.model
        if self.args.model != "large":
            model = model + ".en"
        self.audio_model = whisper.load_model(model)

        self.record_timeout = self.args.record_timeout
        self.phrase_timeout = self.args.phrase_timeout

        self.transcription = ['']

        with self.source:
            self.recorder.adjust_for_ambient_noise(self.source)
        # Create a background thread that will pass us raw audio bytes.
        # We could do this manually but SpeechRecognizer provides a nice helper.


        # Cue the user that we're ready to go.
        self.recorder.listen_in_background(self.source, self.record_callback, phrase_time_limit=self.record_timeout)
        print("Model loaded.\n")

        # save the answer
        self.DIR = 'C:/SCI-Arc/F25-STUDIO/FINAL/data/YenhsingDeyingData'
        os.makedirs(self.DIR, exist_ok=True)

    def record_callback(self,_, audio: sr.AudioData) -> None:
        """
        Threaded callback function to receive audio data when recordings finish.
        audio: An AudioData containing the recorded bytes.
        """
        # Grab the raw bytes and push it into the thread safe queue.
        data = audio.get_raw_data()
        self.data_queue.put(data)


    def listen(self):
        startTime = time.time()
        while True:
            if time.time() - startTime > 5:    # duration
                break

            try:
                now = datetime.utcnow()
                # Pull raw recorded audio from the queue.
                if not self.data_queue.empty():
                    phrase_complete = False

                    # 分段
                    # If enough time has passed between recordings, consider the phrase complete.
                    # Clear the current working audio buffer to start over with the new data.
                    if self.phrase_time and now - self.phrase_time > timedelta(seconds=self.phrase_timeout):
                        phrase_complete = True
                    # This is the last time we received new audio data from the queue.
                    self.phrase_time = now

                    # Combine audio data from queue
                    audio_data = b''.join(self.data_queue.queue)
                    self.data_queue.queue.clear()

                    # Convert in-ram buffer to something the model can use directly without needing a temp file.
                    # Convert data from 16 bit wide integers to floating point with a width of 32 bits.
                    # Clamp the audio stream frequency to a PCM wavelength compatible default of 32768hz max.
                    audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

                    # audio to text
                    result = self.audio_model.transcribe(audio_np, fp16=torch.cuda.is_available())
                    text = result['text'].strip()

                    # If we detected a pause between recordings, add a new item to our transcription.
                    # Otherwise edit the existing one.
                    if phrase_complete:
                        self.transcription.append(text)
                        break
                    else:
                        self.transcription[-1] = text

            except:
                continue

        # 如果沒有收到聲音顯示的預設文字
        if len(self.transcription)<1:
            outText = "AI is going to destroy architecture. Aesthetics will stagnate on empty sci-fiction tropes. I disagree it will expand the potentials of design."
            print(outText)
            return outText

        outText = " ".join(self.transcription).strip()
        self.transcription = [""]

        self.save_txt(outText)

        return outText

    def save_txt(self, text):
        t = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"answer_{t}.txt"
        filepath = os.path.join(self.DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"[TIME] {t}\n")
            f.write(f"[TEXT] {text}\n")




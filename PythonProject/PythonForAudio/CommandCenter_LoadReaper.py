"""

"""

from Audio_prerecordReaperLoad import run_complete_workflow
import time
import os
import wave


base_folder = r"C:\SCI-Arc\F25-STUDIO\FINAL\data\YenhsingDeyingAudio\dialogue"

pause_duration = 3

# play [0]
file_path = os.path.join(base_folder, "0-hihihi.wav")
run_complete_workflow(file_path)
with wave.open(file_path, 'rb') as f:
    frames = f.getnframes()
    rate = f.getframerate()
    duration = frames / float(rate)
time.sleep(duration + pause_duration)
# play [1]
file_path = os.path.join(base_folder, "1-comehereQ1.wav")
run_complete_workflow(file_path)
with wave.open(file_path, 'rb') as f:
    frames = f.getnframes()
    rate = f.getframerate()
    duration = frames / float(rate)
time.sleep(duration + pause_duration)



# play [2]
file_path = os.path.join(base_folder, "2-Q2.wav")
run_complete_workflow(file_path)
with wave.open(file_path, 'rb') as f:
    frames = f.getnframes()
    rate = f.getframerate()
    duration = frames / float(rate)
time.sleep(duration + pause_duration)

# play [3]
file_path = os.path.join(base_folder, "3-Q3.wav")
run_complete_workflow(file_path)
with wave.open(file_path, 'rb') as f:
    frames = f.getnframes()
    rate = f.getframerate()
    duration = frames / float(rate)
time.sleep(duration + pause_duration)

# play [4]
file_path = os.path.join(base_folder, "4-profile.wav")
run_complete_workflow(file_path)
with wave.open(file_path, 'rb') as f:
    frames = f.getnframes()
    rate = f.getframerate()
    duration = frames / float(rate)
time.sleep(duration)
# play [5]
# searching-----看要找多久可以重複播放
file_path = os.path.join(base_folder, "5-matching.wav")
run_complete_workflow(file_path)
with wave.open(file_path, 'rb') as f:
    frames = f.getnframes()
    rate = f.getframerate()
    duration = frames / float(rate)
time.sleep(duration + pause_duration)

# play [6]
file_path = os.path.join(base_folder, "6-matched.wav")
run_complete_workflow(file_path)
with wave.open(file_path, 'rb') as f:
    frames = f.getnframes()
    rate = f.getframerate()
    duration = frames / float(rate)
time.sleep(duration + pause_duration)

"""
run_complete_workflow(fr"{base_folder}\0-hihihi.wav")
time.sleep(pause_duration)
run_complete_workflow(fr"{base_folder}\1-comehereQ1.wav")
time.sleep(pause_duration)

run_complete_workflow(fr"{base_folder}\2-Q2.wav")
time.sleep(pause_duration)

run_complete_workflow(fr"{base_folder}\3-Q3.wav")
time.sleep(pause_duration)

run_complete_workflow(fr"{base_folder}\4-profile.wav")
time.sleep(pause_duration)

run_complete_workflow(fr"{base_folder}\5-matching.wav")
time.sleep(pause_duration)

run_complete_workflow(fr"{base_folder}\6-matched.wav")
time.sleep(pause_duration)

run_complete_workflow(fr"{base_folder}\match_call.mp3")
time.sleep(pause_duration)
"""
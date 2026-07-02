import reapy
import os
from reapy import reascript_api as RPR

def main():
    DIR = "C:/data/SCI_Arc/F25/Studio/datasets/Audio"
    songs = []
    files = os.listdir(DIR)
    for file in files:
        if file.endswith(".mp3"):
            spath = os.path.join(DIR, file)
            songs.append(spath)

    project = reapy.Project()
    play_pos = project.play_position

    track = project.add_track()
    track.name = "addTrack"
    track.selected = True

    RPR.InsertMedia(songs[0], 0)

    track.parent_send = False
    hwID = RPR.CreateTrackSend(track.id, None)

    dstMono = 4 | 1024
    RPR.SetTrackSendInfo_Value(track.id, 1, hwID, "I_DSTCHAN", float(dstMono))


if __name__ == '__main__':
    main()

import reapy
from reapy import reascript_api as RPR
import os


class ReaperManager:
    def __init__(self):
        #reapy.config.use_local_rpr_config()
        self.project = reapy.Project()

    def newest(self,path):
        files = os.listdir(path)
        paths = [os.path.join(path, basename) for basename in files]
        return max(paths, key=os.path.getctime)

    def loadTrackToReaper(self):
        DIR = r"C:\SCI-Arc\F25-STUDIO\FINAL\data\YenhsingDeyingAudio\dialogue"
        #DIR = 'C:/SCI-Arc/F25-STUDIO/FINAL/data/audio'
        songs = []
        song = self.newest(DIR)
        #songs.reverse()
        check = True
        while check:
            play_pos = self.project.play_position
            if play_pos < .1:
                RPR.SetEditCurPos(0.0, False, False)

                track = RPR.GetTrack(0, 0)
                item_count = RPR.CountTrackMediaItems(track)
                for i in range(item_count):
                    item = RPR.GetTrackMediaItem(track, 0)  # always index 0 because they shift down
                    RPR.DeleteTrackMediaItem(track, item)
                total_tracks = RPR.CountTracks(0)
                for i in range(total_tracks):
                    RPR.SetTrackSelected(RPR.GetTrack(0, i), False)
                #track.name = "dialogue"
                #self.project.unmute_all_tracks()
                RPR.SetTrackSelected(track, True)
                RPR.InsertMedia(song, 0)
                check = False
        return True





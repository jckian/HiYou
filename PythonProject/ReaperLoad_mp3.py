import reapy
from reapy import reascript_api as RPR
import os

mp3_path = os.path.join(os.path.dirname(__file__), "..", "YenhsingDeyingAudio", "dialogue", "questions", "Q1.mp3")

class ReaperManager:
    def __init__(self):
        #reapy.config.use_local_rpr_config()
        self.project = reapy.Project()

    def loadTrackToReaper(self, mp3_path):

        if not os.path.isfile(mp3_path):
            raise FileNotFoundError(f"檔案不存在：{mp3_path}")

        # -------------------------------------------------STOP
        RPR.OnStopButton()

        # -------------------------------------------------BACK TO 0sec
        RPR.SetEditCurPos(0.0, True, False)

        # TRACK CHECK
        if RPR.CountTracks(0) == 0:
            RPR.InsertTrackAtIndex(0, True)

        track = RPR.GetTrack(0, 0)

        # CLEAR track 0
        item_count = RPR.CountTrackMediaItems(track)
        for i in range(item_count):
            item = RPR.GetTrackMediaItem(track, 0)
            RPR.DeleteTrackMediaItem(track, item)

        # SELECT track 0
        total_tracks = RPR.CountTracks(0)
        for i in range(total_tracks):
            RPR.SetTrackSelected(RPR.GetTrack(0, i), False)

        RPR.SetTrackSelected(track, True)

        # --------------------------------------------------IMPORT mp3
        RPR.InsertMedia(mp3_path, 0)

        # --------------------------------------------------START FROM __sec <<<<<<<<<<<<<<<CHANGE HERE
        RPR.SetEditCurPos(0.0, True, False)

        # --------------------------------------------------PLAY
        RPR.OnPlayButton()

        return True

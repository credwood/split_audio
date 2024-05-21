import json
import os
import pickle

from collections import OrderedDict
from dataclasses import dataclass


def set_session_id(name):
    if not os.path.isdir("data"):
        os.makedirs("data")
        sessions = {
            "count": 0,
            "users": {
            },
        }
    else:
        sessions = json.load(open("data/sessions.json", "r+"))
    count = sessions["count"]
    if name not in sessions["users"].keys():
        user_id = count
        sessions["users"][name] = count
        count += 1
        sessions["count"] = count
        json.dump(sessions, open("data/sessions.json", 'w+'), indent=4)
    else:
        user_id = sessions["users"][name]
    return user_id

@dataclass
class StreamSession:
    def __init__(self, name=None, session_id=None, offset=0, index=0, 
                 playlist = OrderedDict(), play_state = None, 
                 user_vol=0.25,
                 ):
        
        self.name = name if name is not None else "null"
        self.session_id = set_session_id(self.name)
        self.PLAYLIST = playlist
        self.USER_VOL = user_vol
        self.PLAY_STATE = None
        self.OFFSET = 0
        self.INDEX = 0
        self.MODEL_SELECTION = None
        self.CANCEL_SPLIT = False
        self.CHANNELS = dict()
        self.PYGAME_SOUNDS = dict()
        self.STEM_OFFSETS = dict()
        self.STEMS_CACHE = dict()
        self.STEM_PLAY_STATE = dict()
        self.STEM_LEVELS = dict()
        self.STEM_SAMPLERATE = None
        self.USER_FILES = {
            "songs": {},
            "stems": {},
        }
        self.NAME_SPLIT_SONG = None
        self.ALL_STEMS = None
        self.KILL_SPLIT = False
        self.ORIGINAL_AUDIO = None
        self.STEM_LENGTH = dict()
    
def save_session(session):
    session.PLAY_STATE = None
    session.OFFSET = 0
    session.INDEX = 0
    session.MODEL_SELECTION = None
    session.CANCEL_SPLIT = False
    session.CHANNELS = dict()
    session.PYGAME_SOUNDS = dict()
    session.STEM_OFFSETS = dict()
    session.STEMS_CACHE = dict()
    session.STEM_PLAY_STATE = dict()
    session.STEM_LEVELS = dict()
    session.STEM_SAMPLERATE = None
    session.NAME_SPLIT_SONG = None
    session.ALL_STEMS = None
    session.KILL_SPLIT = False
    session.ORIGINAL_AUDIO = None
    session.STEM_LENGTH = dict()
    with open(f"data/{session.name}.pickle", "wb") as f:
        pickle.dump(session, f)

def load_session(name):
    with open(f"data/{name}.pickle", "rb") as f:
        try:
            session = pickle.load(f)
        except EOFError:
            print("session could not load, creating new session")
            session = StreamSession(name)
    return session

def remove_stems(path):
    assert os.path.isfile(path), "path must be a file"
    os.remove(path)

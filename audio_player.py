import argparse
import atexit
import logging
import os
import threading
import time
import webbrowser
from collections import OrderedDict
from multiprocessing import Process


import dearpygui.dearpygui as dpg
import pygame
from demucs.api import save_audio
from mutagen.mp3 import MP3
from pygame import mixer

from audio_utils import remove_stems, StreamSession, load_session, save_session
from model import separate, save_stems

#------------- Logging -------------#

logger = logging.getLogger(__name__)
logging.basicConfig(filename='source_stream.log', level=logging.INFO)

#------------- Thread monitoring Events and Data Structures -------------#

splitting_event = threading.Event()
save_event = threading.Event()
save_thread_event = threading.Event()
curr_stem_pos = threading.Event()
stem_events = {stem: threading.Event() for stem in ["vocals", "bass", "drums", "piano", "guitar", "other"]}
stem_pos_thread = {}

#------------- Audio Player Init and Params -------------#

DEFAULT_VOL = 0.25
mixer.init()
mixer.music.set_volume(DEFAULT_VOL)

#------------- Session Init and Params -------------#

dpg.create_context()
parser = argparse.ArgumentParser()
parser.add_argument("--name", default="null", help="Unique username. Use to cerate individualized accounts")
args = parser.parse_args()
if os.path.exists(f"data/{args.name}.pickle"):
    session = load_session(args.name)
else:
    session = StreamSession(args.name)

#------------- Audio Player Functions -------------#

def update_volume(sender=None, app_data=None):
    if app_data is not None:
        mixer.music.set_volume(app_data / 100.0)

def update_position():
    while (mixer.music.get_busy() or session.PLAY_STATE != 'paused'):
        dpg.configure_item(item="curr_position",default_value=(mixer.music.get_pos()/1000)+session.OFFSET)
        time.sleep(0.7)

def global_pos_update(sender, data):
    current = mixer.music.get_pos()/1000 + session.OFFSET
    mixer.music.set_pos(data)
    session.OFFSET += data-current

def get_current_song():
    if len(session.PLAYLIST.keys()):
        return list(session.PLAYLIST.keys())[session.INDEX]
    return "Add music to library"

def get_current_song_path():
    if session.PLAY_STATE == None:
        dpg.show_item("play_popup")
        return None
    return list(session.PLAYLIST.values())[session.INDEX]

def play(sender=None, app_data=None, user_data=None):
    song_name, song_path = user_data
    session.OFFSET = 0
    session.INDEX = list(session.PLAYLIST.keys()).index(song_name)
    if user_data:
        mixer.music.load(song_path)
        current_audio = MP3(song_path)
        dpg.configure_item(item="curr_position", max_value=current_audio.info.length)
        dpg.configure_item(item="current_song", show=True, default_value=song_name)
        mixer.music.play()
        slider_thread = threading.Thread(target=update_position, name="main_volume").start()
        if pygame.mixer.music.get_busy():
            dpg.configure_item("play",label="Pause")
            session.PLAY_STATE="playing"

def play_or_pause():        
    if session.PLAY_STATE == "playing":
        mixer.music.pause()
        dpg.configure_item("play",label="Play")
        session.PLAY_STATE = "paused"
    elif session.PLAY_STATE == "paused":
        mixer.music.unpause()
        dpg.configure_item("play",label="Pause")
        session.PLAY_STATE = "playing"  
    elif session.PLAY_STATE == "stopped":
        dpg.configure_item("play",label="Pause")
        session.PLAY_STATE = "playing"
    else:
        dpg.show_item("play_popup")

def previous_song():
    prev_song = list(session.PLAYLIST.keys())[session.INDEX-1]
    session.INDEX -= 1
    play(user_data=[prev_song, session.PLAYLIST[prev_song]])

def next_song():
    prev_song = list(session.PLAYLIST.keys())[(session.INDEX+1)%len(session.PLAYLIST)]
    session.INDEX += 1
    play(user_data=[prev_song, session.PLAYLIST[prev_song]])

def stop():
    mixer.music.stop()
    session.OFFSET = 0
    session.PLAY_STATE="stopped"
    dpg.configure_item("play",label="Play")

def get_songs(sender, app_data):
    song_dict = app_data['selections']
    for name, song_path in song_dict.items():
        session.USER_FILES["songs"][name] = song_path
    load_database()
    session.INDEX = 0

def load_database():
    songs =  session.USER_FILES["songs"]
    for filename, song_path in songs.items():
        if not dpg.does_item_exist(filename):
            dpg.add_button(label=filename, tag=filename, callback=play, width=-1,
                        height=25, user_data=[filename, song_path], parent="songs")
            
            dpg.add_spacer(height=2, parent="songs")
    
    session.PLAYLIST = OrderedDict(songs)
    session.INDEX = 0

def removeallsongs():
    session.USER_FILES["songs"] = {}
    dpg.delete_item("songs", children_only=True)
    session.PLAYLIST = OrderedDict()
    session.INDEX = 0
    dpg.configure_item("current_song", default_value="")
    dpg.hide_item("confirm_clear_songs")

#------------- Stem Splitting and Audio Player Functions -------------#

def init_stem_channels(stems):
    stop_all_stems()
    stop_all_stem_threads()
    for stem in session.CHANNELS.keys():
        dpg.hide_item(stem)
    for n, (name, stem) in enumerate(stems.items()):
        if name in stem_pos_thread.keys():
            if stem_pos_thread[name].is_alive():
                stem_events[name].set()
        save_audio(stem, "temp.wav", session.STEM_SAMPLERATE)
        session.CHANNELS[name] = mixer.Channel(n)
        session.PYGAME_SOUNDS[name] = mixer.Sound("temp.wav")
        session.STEM_OFFSETS[name] = 0
        session.STEM_PLAY_STATE[name] = None
        session.STEM_LEVELS[name] = DEFAULT_VOL
        session.NAME_SPLIT_SONG = get_current_song()
        session.STEM_LENGTH[name] = session.PYGAME_SOUNDS[name].get_length()
        dpg.configure_item(item=f"{name}_position", max_value=session.STEM_LENGTH[name])

    remove_stems("temp.wav")
    for stem in stems.keys():
        stem_events[stem].clear()
        stopwatch_handler(stem)
    dpg.configure_item("now_playing", default_value=f"Stems for: {session.NAME_SPLIT_SONG}")


def play_or_pause_all_stems(): 
    if session.ALL_STEMS == "playing":
        mixer.pause()
        dpg.configure_item("all_play",label="Play All")
        session.ALL_STEMS = "paused"
        for stem in session.STEM_PLAY_STATE.keys():
            session.STEM_PLAY_STATE[stem] = "paused"
            dpg.configure_item(f"{stem}_play",label="Play")
    elif session.ALL_STEMS == "paused":
        mixer.unpause()
        dpg.configure_item("all_play",label="Pause All")
        session.ALL_STEMS = "playing"
        for stem in session.STEM_PLAY_STATE.keys():
            session.STEM_PLAY_STATE[stem] = "playing"
            dpg.configure_item(f"{stem}_play",label="Pause")
    else:
        for stem in session.CHANNELS.keys():
            sound = session.PYGAME_SOUNDS[stem]
            session.CHANNELS[stem].play(sound)
            session.STEM_PLAY_STATE[stem] = "playing"
            dpg.configure_item(f"{stem}_play",label="Pause")
        dpg.configure_item("all_play",label="Pause All")
        session.ALL_STEMS = "playing"

def stop_all_stems():
    mixer.stop()
    for stem in session.STEM_PLAY_STATE.keys():
        session.STEM_PLAY_STATE[stem] = "stopped"
        session.ALL_STEMS = None
        dpg.configure_item(f"{stem}_play",label="Play")
        dpg.configure_item(f"{stem}_position",default_value=0.0)
    dpg.configure_item("all_play",label="Play All")

def play_or_pause_stem(sender, data):
    stem = sender.split("_")[0]
    sound = session.PYGAME_SOUNDS[stem]
    if session.STEM_PLAY_STATE[stem] == None:
        session.CHANNELS[stem].play(sound)
        session.STEM_PLAY_STATE[stem] = "playing"
        dpg.configure_item(sender,label="Pause")
    elif session.STEM_PLAY_STATE[stem] == "playing":
        session.STEM_PLAY_STATE[stem] = "paused"
        session.CHANNELS[stem].pause()
        dpg.configure_item(sender,label="Play")
    else:
        session.STEM_PLAY_STATE[stem] = "playing"
        session.CHANNELS[stem].unpause()
        dpg.configure_item(sender,label="Pause")

def mute_unmute_stem(sender, data):
    stem = sender.split("_")[0]
    if session.STEM_LEVELS[stem] == "muted":
        session.CHANNELS[stem].set_volume(0.25)
        session.STEM_LEVELS[stem] = session.CHANNELS[stem].get_volume()
        dpg.configure_item(sender,label="Mute")
    else:
        session.CHANNELS[stem].set_volume(0.0)
        session.STEM_LEVELS[stem] = "muted"
        dpg.configure_item(sender,label="Unmute")

def set_stem_level(sender, app_data):
    stem = sender.split("_")[0]
    if app_data is not None:
        curr_vol = session.CHANNELS[stem].get_volume()
        if curr_vol == 0.0:
            session.CHANNELS[stem].set_volume(app_data / 100.0)
        else:
            session.CHANNELS[stem].set_volume(app_data / (100.0*curr_vol + 1e-5))
        if session.STEM_LEVELS[stem] == "muted":
            dpg.configure_item(f"{stem}_mute",label="Mute")
        session.STEM_LEVELS[stem] = app_data / 100.0

def stopwatch(seconds, stem):
    start = time.time()
    offset = elapsed = 0.

    while elapsed < float(seconds) and not stem_events[stem].is_set():
        if "stopped" == session.STEM_PLAY_STATE[stem]:
            start = time.time()
            offset = elapsed = 0.
            continue
        elif "playing" != session.STEM_PLAY_STATE[stem]:
            offset = time.time() - (elapsed + start)
            continue
        
        elapsed = time.time() - start - offset
        dpg.configure_item(f"{stem}_position", default_value=elapsed)
        time.sleep(.7)

def stopwatch_handler(stem):
    if stem in stem_pos_thread.keys() and stem_pos_thread[stem].is_alive():
        return
    stem_pos_thread[stem] = None
    stem_pos_thread[stem] = threading.Thread(target=stopwatch, args=[session.STEM_LENGTH[stem], stem])
    stem_pos_thread[stem].start()

def init_and_play_saved_stem_channels(data):
    stop_all_stem_threads()
    for stem in session.CHANNELS.keys():
        dpg.hide_item(stem)
    stems = session.USER_FILES["stems"][data]
    for n, (name, stem) in enumerate(stems.items()):
        if name in stem_pos_thread.keys():
            if stem_pos_thread[name].is_alive():
                stem_events[name].set()
        session.CHANNELS[name] = mixer.Channel(n)
        session.PYGAME_SOUNDS[name] = mixer.Sound(stem)
        session.STEM_OFFSETS[name] = 0
        session.STEM_PLAY_STATE[name] = None
        session.STEM_LEVELS[name] = DEFAULT_VOL
        session.STEM_LENGTH[name] = session.PYGAME_SOUNDS[name].get_length()
        dpg.configure_item(item=f"{name}_position", max_value=session.STEM_LENGTH[name])
    
    for item in ["all_play", "all_stop", "save_stems"]:
        dpg.show_item(item)

    for stem in stems.keys():
        dpg.show_item(stem)
        stem_events[stem].clear()
        stopwatch_handler(stem)
        
    dpg.configure_item("now_playing", default_value=f"Stems for: {data}")
      
def load_stems():
    stems = session.USER_FILES["stems"]
    return list(stems.keys())

def load_selected_stems(sender, data):
    stop_all_stems()
    if data != "Choose a song":
        init_and_play_saved_stem_channels(data)
            
def clear_stems():
    for song in session.USER_FILES["stems"].keys():
        for stem in session.USER_FILES["stems"][song].values():
            remove_stems(stem)
    
    for ctrl in ["all_play", "all_stop", "save_stems"]:
        dpg.hide_item(ctrl)
    for stem in session.CHANNELS.keys():
        dpg.hide_item(stem)
        if stem in stem_pos_thread.keys():
            if stem_pos_thread[stem].is_alive():
                stem_events[stem].set()

    session.USER_FILES["stems"] = {}
    dpg.configure_item(items=load_stems(), item="load_stems")
    dpg.configure_item("now_playing", default_value=f"")
    dpg.hide_item("confirm_clear")

def stop_all_stem_threads():
    for stem in stem_pos_thread.keys():
        if stem_pos_thread[stem].is_alive():
            stem_events[stem].set()

def get_model_selection(sender, data):
    session.MODEL_SELECTION = data
    return data

def hyperlink(text, address):
    b = dpg.add_button(label=text, callback=lambda:webbrowser.open(address))

def split_song():
    splitting_event.clear()
    model = session.MODEL_SELECTION
    stop_all_stem_threads()
    if model is None:
        dpg.show_item("select_model_pop")
        return 
    song_path = get_current_song_path()
    if song_path == None:
        dpg.show_item("play_popup")
        return 
    dpg.configure_item("separate_section", enabled=False)
    results = []
    sep_thread = threading.Thread(target=separate, args=[results, model, song_path])
    sep_thread.start()
    dpg.show_item("splitting")
    while sep_thread.is_alive():
        time.sleep(0.1)
    dpg.hide_item("splitting")
    try:
        session.ORIGINAL_AUDIO, session.STEMS_CACHE, session.STEM_SAMPLERATE = results
    except ValueError:
        logger.error("splitting failed.")
        dpg.configure_item("separate_section", enabled=True)
        return
        
    init_stem_channels(session.STEMS_CACHE)
    dpg.configure_item("separate_section", enabled=True)
    for ctrl in ["all_play", "all_stop", "save_stems"]:
        dpg.show_item(ctrl)
    for stem in session.STEMS_CACHE.keys():
        dpg.show_item(stem)  
    dpg.configure_item("now_playing", default_value=f"Stems for: {session.NAME_SPLIT_SONG}")
    dpg.configure_item("model_used", default_value=model)
    return

def handle_splitting():
    split_function = threading.Thread(target=split_song)
    split_function.start()
    return

def save_stem_helper():
    save_event.clear()
    song_name = ".".join(session.NAME_SPLIT_SONG.split(".")[:-1])
    model_used = dpg.get_value("model_used")
    song_name = model_used + "_" + song_name
    stems_paths = []
    save_thread = threading.Thread(target=save_stems, args=[session.ORIGINAL_AUDIO, session.STEMS_CACHE, song_name, session.MODEL_SELECTION, session.STEM_SAMPLERATE, stems_paths])
    save_thread.start()
    dpg.show_item("saving")
    while save_thread.is_alive():
        time.sleep(0.1)
    dpg.hide_item("saving")
    try:
        stems_paths = stems_paths[0]
    except IndexError:
        logger.debug("Saving failed.")
        return
    
    session.USER_FILES["stems"][song_name] = stems_paths
    dpg.configure_item(items=load_stems(), item="load_stems")

def handle_saving():
    save_function = threading.Thread(target=save_stem_helper)
    save_function.start()
    save_event.clear()

#------------- GUI -------------#

with dpg.window(tag="main",label="window title"):
    dpg.add_spacer(height=2)
    with dpg.group(horizontal=True):
        with dpg.child_window(width=400,tag="sidebar"):
            dpg.add_text("Library")
            dpg.add_spacer(height=2)
            dpg.add_spacer(height=5)
            with dpg.file_dialog(directory_selector=False, show=False, callback=get_songs, tag="file_dialog_tag", width=700 ,height=400):
                dpg.add_file_extension(".mp3", color=(255, 255, 0, 255))
                dpg.add_file_extension(".wav", color=(255, 0, 255, 255))

            with dpg.group(horizontal=True):
                dpg.add_button(label="Import Songs", callback=lambda: dpg.show_item("file_dialog_tag"))
                dpg.add_button(label="Clear Library", callback=lambda: dpg.show_item("confirm_clear_songs"))
            
            dpg.add_separator()
            dpg.add_spacer(height=2)
            dpg.add_spacer(height=3)
            with dpg.child_window(autosize_x=True,tag="songs"):
                load_database()
        
        with dpg.child_window(autosize_x=True,height=80,no_scrollbar=True, tag="control"):
            with dpg.group(horizontal=True):
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Prev",tag="prev",show=True,callback=previous_song,width=65,height=30)
                    dpg.add_button(label="Play",tag="play",show=True,callback=play_or_pause,width=65,height=30)
                    dpg.add_button(label="next",tag="next",show=True,callback=next_song,width=65,height=30)
                    dpg.add_button(label="Stop",tag="stop",show=True,callback=stop,width=65,height=30)
                    with dpg.child_window(height=60, width=450, pos=(315, 10), no_scrollbar=True):
                        dpg.add_text(get_current_song(), show=False, tag="current_song")
                        dpg.add_slider_float(tag="curr_position",callback=global_pos_update, pos=(50, 30), width=350,height=1, format="")

                dpg.add_slider_float(width=200,height=30, pos=(790, 10), format="%.0f%.0%",default_value=DEFAULT_VOL * 100, callback=update_volume)
        
        with dpg.window(show=False, modal=True, tag="model_info", pos=(525, 100)):
            dpg.add_text("htdemucs: Original model, splits audio into 4 stems: voice, bass, drums and other.")
            dpg.add_text("htdemucs_ft: fine-tuned version of htdemucs, separation will take 4 times more time but might be a bit better.")
            dpg.add_text("htdemucs_6s: splits audio into six sources with piano and guitar added to the original four.")
            dpg.add_text("Note that the htdemucs_6s piano source is not working great at the moment.")
            dpg.add_spacer(height=8)
            dpg.add_text("For more information, see the Demucs project README.")
            hyperlink("Demucs README", "https://github.com/facebookresearch/demucs/blob/main/README.md")
            dpg.add_button(label="Close", pos=(350, 200), width=100, height=30, callback=lambda: dpg.hide_item("model_info"))
        
        with dpg.window(show=False, modal=True, tag="play_popup", pos=(525, 100)):
            dpg.add_text("Choose a song from the library sidebar, or import songs to get started.")
            dpg.add_button(label="OK", pos=(230, 60), callback=lambda: dpg.hide_item("play_popup"))

        with dpg.window(show=False, modal=True, tag="select_model_pop", pos=(525, 100)):
            dpg.add_text("Choose a model.")
            dpg.add_button(label="OK", pos=(50, 60), callback=lambda: dpg.hide_item("select_model_pop"))
            dpg.add_text("", show=False, tag="model_used")

        with dpg.child_window(autosize_x=True, pos=(416, 100), tag="visualizer"):
            dpg.add_text("Separate current track or load saved stems:")
            dpg.add_spacer(height=2)
            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_combo(["htdemucs", "htdemucs_ft", "htdemucs_6s"],  pos=(10, 50), tag="models", default_value="Choose a model", callback=get_model_selection, width=200)
                dpg.add_button(label="About Models", tag="get_model_info", pos=(10, 80), width=100, height=20, callback=lambda: dpg.show_item("model_info"))
                dpg.add_button(label="Separate", tag="separate_section", pos=(250, 50), width=100, height=20, callback=split_song)
                dpg.add_text("Load saved stems: ",  pos=(550, 50))
                dpg.add_combo(load_stems(), tag="load_stems", default_value="Choose a song", callback=load_selected_stems, width=200, pos=(680, 50))
                dpg.add_button(label="Delete Stems", tag="clear_stems", pos=(890, 50), width=100, height=20, callback=lambda: dpg.show_item("confirm_clear"))

            dpg.add_spacer(height=12)

            with dpg.group(horizontal=True):   
                dpg.add_button(label="Play All Stems",tag=f"all_play",show=False,callback=play_or_pause_all_stems, pos=(350, 100),width=110,height=30)
                dpg.add_button(label="Stop Stems",tag=f"all_stop",show=False,callback=stop_all_stems, pos=(465, 100),width=110,height=30)
                dpg.add_button(label="Save Stems",tag=f"save_stems",show=False,callback=handle_saving, pos=(580, 100),width=110,height=30)
        
            dpg.add_spacer(height=12)

            dpg.add_text("", show=True, tag="now_playing")
            with dpg.child_window(autosize_x=True,show=False,height=80,no_scrollbar=True, tag="vocals"):
                with dpg.group(horizontal=True):
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Play",tag=f"vocals_play",show=True,callback=play_or_pause_stem,width=65,height=30)
                        dpg.add_button(label="Mute",tag=f"vocals_mute",show=True,callback=mute_unmute_stem,width=65,height=30)
                        dpg.add_text("elapsed time (not adjustable): ", tag="vocals_timer", label=str(0.0))
                        dpg.add_slider_float(tag="vocals_position", width=350,height=1, format="Vocals")

                    dpg.add_slider_float(tag="vocals_volume", label="vocals_volume", width=200,height=30, pos=(800, 10), format="%.0f%.0%",default_value=DEFAULT_VOL * 100, callback=set_stem_level)
            
            with dpg.child_window(autosize_x=True,show=False,height=80,no_scrollbar=True, tag="bass"):
                with dpg.group(horizontal=True):
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Play",tag=f"bass_play",show=True,callback=play_or_pause_stem,width=65,height=30)
                        dpg.add_button(label="Mute",tag=f"bass_mute",show=True,callback=mute_unmute_stem,width=65,height=30)
                        dpg.add_text("elapsed time (not adjustable): ", tag="bass_timer", label=str(0.0))
                        dpg.add_slider_float(tag="bass_position", width=350,height=1, format="Bass")

                    dpg.add_slider_float(tag="bass_volume", label="bass_volume", width=200,height=30, pos=(800, 10), format="%.0f%.0%",default_value=DEFAULT_VOL * 100, callback=set_stem_level)
            
            with dpg.child_window(autosize_x=True,show=False,height=80,no_scrollbar=True, tag="drums"):
                with dpg.group(horizontal=True):
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Play",tag=f"drums_play",show=True,callback=play_or_pause_stem,width=65,height=30)
                        dpg.add_button(label="Mute",tag=f"drums_mute",show=True,callback=mute_unmute_stem,width=65,height=30)
                        dpg.add_text("elapsed time (not adjustable): ", tag="drums_timer", label=str(0.0))
                        dpg.add_slider_float(tag="drums_position", width=350,height=1, format="Drums")
                    
                    dpg.add_slider_float(tag="drums_volume", label="drums_volume", width=200,height=30, pos=(800, 10), format="%.0f%.0%",default_value=DEFAULT_VOL * 100, callback=set_stem_level)
            
            with dpg.child_window(autosize_x=True,show=False,height=80,no_scrollbar=True, tag="guitar"):
                with dpg.group(horizontal=True):
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Play",tag=f"guitar_play",show=True,callback=play_or_pause_stem,width=65,height=30)
                        dpg.add_button(label="Mute",tag=f"guitar_mute",show=True,callback=mute_unmute_stem,width=65,height=30)
                        dpg.add_text("elapsed time (not adjustable): ", tag="guitar_timer", label=str(0.0))
                        dpg.add_slider_float(tag="guitar_position", width=350,height=1, format="Guitar")

                    dpg.add_slider_float(tag="guitar_volume", label="guitar_volume", width=200,height=30, pos=(800, 10), format="%.0f%.0%",default_value=DEFAULT_VOL * 100, callback=set_stem_level)
            
            with dpg.child_window(autosize_x=True,show=False,height=80,no_scrollbar=True, tag="piano"):
                with dpg.group(horizontal=True):
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Play",tag=f"piano_play",show=True,callback=play_or_pause_stem,width=65,height=30)
                        dpg.add_button(label="Mute",tag=f"piano_mute",show=True,callback=mute_unmute_stem,width=65,height=30)
                        dpg.add_text("elapsed time (not adjustable): ", tag="piano_timer", label=str(0.0))
                        dpg.add_slider_float(tag="piano_position", width=350,height=1, format="Piano")

                    dpg.add_slider_float(tag="piano_volume", label="piano_volume", width=200,height=30, pos=(800, 10), format="%.0f%.0%",default_value=DEFAULT_VOL * 100, callback=set_stem_level)
            
            with dpg.child_window(autosize_x=True,show=False,height=80,no_scrollbar=True, tag="other"):
                with dpg.group(horizontal=True):
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Play",tag=f"other_play",show=True,callback=play_or_pause_stem,width=65,height=30)
                        dpg.add_button(label="Mute",tag=f"other_mute",show=True,callback=mute_unmute_stem,width=65,height=30)
                        dpg.add_text("elapsed time (not adjustable): ", tag="other_timer", label=str(0.0))
                        dpg.add_slider_float(tag="other_position", width=350,height=1, format="Other")

                    dpg.add_slider_float(tag="other_volume", label="other_volume", width=200,height=30, pos=(800, 10), format="%.0f%.0%",default_value=DEFAULT_VOL * 100, callback=set_stem_level)
    
        with dpg.window(show=False, modal=True, tag="confirm_clear_songs", pos=(525, 100)):
            dpg.add_text("Are you sure you want to delete all songs?")
            dpg.add_button(label="Cancel", tag="cancel_clear_dong", pos=(90, 60), callback=lambda: dpg.hide_item("confirm_clear_songs"))
            dpg.add_button(label="Confirm", tag="confirm_clear_song_button", pos=(160, 60), callback=removeallsongs)

        with dpg.window(show=False, modal=True, tag="confirm_clear", pos=(525, 100)):
            dpg.add_text("Are you sure you want to delete all saved and loaded stems?")
            dpg.add_button(label="Cancel", tag="cancel_clear_stem", pos=(135, 60), callback=lambda: dpg.hide_item("confirm_clear"))
            dpg.add_button(label="Confirm", tag="confirm_clear_button", pos=(215, 60), callback=clear_stems)

        with dpg.window(show=False, modal=True, tag="saving", pos=(525, 100)):
            dpg.add_text("Saving in progress.")
            #dpg.add_button(label="Cancel", tag="cancel_saving", pos=(50, 60), callback=lambda: save_event.set())
        
        with dpg.window(show=False, modal=True, tag="splitting", pos=(525, 100)):
            dpg.add_text("Splitting in progress.")
            #dpg.add_button(label="Cancel", tag="cancel_splitting", pos=(60, 60), callback=lambda: splitting_event.set())

def safe_exit():
    stop_all_stem_threads()
    save_session(session)
    mixer.music.stop()
    pygame.quit()


atexit.register(safe_exit)

dpg.create_viewport(title='Source Stream Music Player')
dpg.setup_dearpygui()
dpg.show_viewport()
dpg.set_primary_window("main", True)
dpg.maximize_viewport()
dpg.start_dearpygui()
dpg.destroy_context()

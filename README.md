# Source Stream Music Player

![alt text](https://github.com/credwood/split_audio/blob/main/img/source_stream.png)

## About
- The Source Stream music player allows users to import and listen to local audio files and separate them into discrete instruments called stems. The stems can be played individually or in any combination and saved for later use. 

- This project is written in Python and makes use of the Python GUI framework [DearPyGui](https://github.com/hoffstadt/DearPyGui/) and the [Pygame](https://github.com/pygame/pygame) audio module.

- This project uses the Demucs model, a Hybrid Transformer based source separation model. The original repository can be found here: [here](https://github.com/facebookresearch/demucs/blob/main/README.md).


## Instruction

### Setup
This project requires Python 3.9.0 (or later). To get started, once you've cloned this repository, navigate to the root folower, create a virtual environment and install the requirements:

```
conda create -n split_audio python=3.9.0
```

Once the environment is successfully made:

```
conda activate split_audio
```

Install the dependencies:
```
pip install -r requirements.txt
```

## Launching the Music Player
Once the dependencies are installed, run the app:

```
python audio_player.py
```

You can create a specific user account by providing a user name and launching the player with the user name each session:

```
python audio_player.py --name user_name
```

### Using the interface
- Once you load local audio files into the library, you're free to play them as you would with any other audio player or split them into stems and listen to any combination thereof.
- There are three Demucs models available for splitting the audio, see the `About Models` button for more information.
-  Saved stems will be listed in the dropdown on the right-hand side of the window.
- The `Clear Library` and `Delete Stems` options currently only allow for deleting every song/stem, selected song deletion unsupported.
- Because of limitations with the base audio player, the stem progress bars are not interactive.

## License
- Licensed Under [GPL-3.0](https://github.com/credwood/split_audio/blob/main/LICENSE)

## Maintenance and Development
- Developed and maintained By [Charysse Redwood](https://github.com/credwod)
- Contributions and feature requests are welcomed!
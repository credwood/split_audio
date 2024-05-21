# adapted from https://github.com/credwood/demucs/blob/main/demucs/separate.py
# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import argparse
import os
import sys
from pathlib import Path

import torch as th

from demucs.api import Separator, save_audio

from demucs.apply import BagOfModels
from demucs.htdemucs import HTDemucs
from demucs.pretrained import ModelLoadingError

kwargs = {
    "bitrate": 320,
    "preset": 2,
    "clip": "rescale",
    "as_float": False,
    "bits_per_sample": 16,
}

def save_stems(origin, stems, track, model_name, samplerate, result, directory=None, ext="mp3", other_method=None, one_stem=None, kwargs=kwargs):
    out = "separated" + "/" +  model_name
    os.makedirs(out, exist_ok=True)
    filename ="{track}/{stem}.{ext}"
    out_dict = dict()
    if one_stem is None:
        for name, source in stems.items():
            stem = out + "/" + filename.format(
                track=track.rsplit(".", 1)[0],
                trackext=track.rsplit(".", 1)[-1],
                stem=name,
                ext=ext,
            )
            stem_dir = "/".join(stem.split("/")[:-1])
            out_dict[name] = stem
            os.makedirs(stem_dir, exist_ok=True)
            save_audio(source, str(stem), samplerate=samplerate, **kwargs)
    else:
        stem = out + "/" + filename.format(
            track=track.rsplit(".", 1)[0],
            trackext=track.rsplit(".", 1)[-1],
            stem="minus_" + one_stem,
            ext=ext,
        )
        if other_method == "minus":
            stem_dir = "/".join(stem.split("/")[:-1])
            out_dict[name] = stem
            os.makedirs(stem_dir, exist_ok=True)
            save_audio(origin - stems[one_stem], str(stem), samplerate=samplerate, **kwargs)
        stem = out + "/" + filename.format(
            track=track.rsplit(".", 1)[0],
            trackext=track.rsplit(".", 1)[-1],
            stem=one_stem,
            ext=ext,
        )
        stem_dir = "/".join(stem.split("/")[:-1])
        out_dict[name] = stem
        os.makedirs(stem_dir, exist_ok=True)
        save_audio(stems.pop(one_stem), str(stem), samplerate=samplerate, **kwargs)
        # Warning : after poping the stem, selected stem is no longer in the dict 'res'
        if other_method == "add":
            other_stem = th.zeros_like(next(iter(stems.values())))
            for i in stems.values():
                other_stem += i
            stem = out + "/" + filename.format(
                track=track.rsplit(".", 1)[0],
                trackext=track.rsplit(".", 1)[-1],
                stem="no_" + one_stem,
                ext=ext,
            )
            stem_dir = "/".join(stem.split("/")[:-1])
            out_dict[name] = stem
            os.makedirs(stem_dir, exist_ok=True)
            save_audio(other_stem, str(stem), samplerate=samplerate, **kwargs)
    result.append(out_dict)
    return result

def separate(result_list, model_name, track, file_type="mp3", one_stem=None, other_method=None):
    device = "cuda" if th.cuda.is_available() else "mps" if th.backends.mps.is_available() else "cpu"
    try:
        separator = Separator(model=model_name,
                              device=device,
                              progress=True,
                              )
    except ModelLoadingError as error:
        error.args[0]

    max_allowed_segment = float('inf')
    if isinstance(separator.model, HTDemucs):
        max_allowed_segment = float(separator.model.segment)
    elif isinstance(separator.model, BagOfModels):
        max_allowed_segment = separator.model.max_allowed_segment

    if isinstance(separator.model, BagOfModels):
        print(
            f"Selected model is a bag of {len(separator.model.models)} models. "
            "You will see that many progress bars per track."
        )

    out = "separated" + "/" +  model_name
    #os.makedirs(out, exist_ok=True)
    filename ="{track}/{stem}.{ext}"
    print(f"Separated tracks will be stored in {out}")
    if not os.path.exists(track):
        print(f"File {track} does not exist. If the path contains spaces, "
                'please try again after surrounding the entire path with quotes "".',
                file=sys.stderr)
        return
    print(f"Separating track {track}")
    ext = file_type
    origin, res = separator.separate_audio_file(Path(track))
    result_list.append(origin)
    result_list.append(res)
    result_list.append(separator.samplerate)
       
    return origin, res, separator.samplerate

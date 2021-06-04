import json
import logging
import math
import os
import subprocess
import time
from collections import defaultdict
from functools import reduce
from pathlib import Path
from types import MethodType
import numpy as np

import click as click
import coloredlogs as coloredlogs
import pytomlpp as pytomlpp
from pymediainfo import MediaInfo

HERE = Path(__file__).parent

LOG_FORMAT = "{asctime} [{levelname[0]}] {name} : {message}"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_STYLE = "{"
LOG_FORMATTER = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT, LOG_STYLE)

CODEC_MAP = {"MPEG-2 Video": "V_MPEG2"}

cfg = (HERE.parent / "config.toml")
if cfg.is_file():
    with cfg.open(encoding="utf8") as f:
        cfg = pytomlpp.loads(f.read())
else:
    cfg = {}


def setup_log(log: logging.Logger, level: int = logging.INFO, stream_handler=False, color=True, patch=True):
    log.setLevel(level)
    if log.name == "root" or stream_handler:
        sh = logging.StreamHandler()
        sh.setFormatter(LOG_FORMATTER)
        log.addHandler(sh)
    if color:
        coloredlogs.install(level=level, logger=log, fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT, style=LOG_STYLE)
    if patch:
        def custom_emit(self, record):
            self.orig_emit(record)
            if record.levelno == logging.CRITICAL:
                raise SystemExit(-1)

        handler = log.handlers[0]
        setattr(handler, "orig_emit", handler.emit)
        setattr(handler, "emit", MethodType(custom_emit, handler))


def dict_to_list(var: dict) -> list:
    return list(reduce(lambda x, y: x + y, var.items()))


def auto_codec(arg, codec, default=None):
    return cfg["ffmpeg"]["auto"][arg].get(codec, default)


def auto_res(arg, res, default=None):
    return next(iter(sorted(
        [(int(x), y) for x, y in cfg["ffmpeg"]["auto"][arg].items() if int(x) <= res],
        key=lambda x: x[0],
        reverse=True
    )), [None, default])[1]


def encode(file: Path, out: Path):
    log = logging.getLogger("encode")
    log.info("Encoding: %s", file)
    log.info("Saving to: %s", out)

    media_info = MediaInfo.parse(file)

    video_track = media_info.video_tracks[0]
    video_codec = video_track.codec_id or video_track.commercial_name
    video_codec = CODEC_MAP.get(video_codec, video_codec)

    ffmpeg = cfg["ffmpeg"]["args"].copy()
    for in_arg in np.where(np.array(ffmpeg) == "-i")[0]:
        ffmpeg[in_arg + 1] = ffmpeg[in_arg + 1].format_map(defaultdict(str, file=str(file)))
    for key in ["-preset", "-crf"]:
        index = ffmpeg.index(key) + 1
        ffmpeg[index] = auto_codec(key, video_codec, ffmpeg[index])
    for key in ["-profile", "-level", "-maxrate", "-bufsize"]:
        index = ffmpeg.index(key) + 1
        ffmpeg[index] = auto_res(key, video_track.height, ffmpeg[index])
    log.info(
        "\tProfile [%s], Level [%.1f], Bitrate [%s], CRF [%.2f] @ %s Speed",
        ffmpeg[ffmpeg.index("-profile") + 1],
        ffmpeg[ffmpeg.index("-level") + 1],
        ffmpeg[ffmpeg.index("-maxrate") + 1],
        ffmpeg[ffmpeg.index("-crf") + 1],
        ffmpeg[ffmpeg.index("-preset") + 1]
    )
    ffmpeg = list(map(str, ffmpeg))
    log.debug("FFMPEG arguments:\n%s", json.dumps(ffmpeg))

    vs = cfg["vs"].copy()
    del vs["script"]
    if "--y4m" in vs:
        if vs["--y4m"]:
            vs["--y4m"] = None
        else:
            del vs["--y4m"]
    vs["-a"] = f"Input={file}"
    vs = list(map(str, filter(lambda x: x is not None, dict_to_list(vs))))
    log.debug("VS arguments:\n%s", json.dumps(vs))

    # jump start vs script, let it initialize, why? if the script prints out data it would be sent to FFMPEG
    # which would be invalid data, ffmpeg would panic and exit. Just render 0 frames ("validate") and hope
    # next run won't print anything to stdout (which is sent to FFMPEG).
    log.info("Jump-starting VS Pipe...")
    print(["vspipe"] + vs + [
        "--end", "0", cfg["vs"]["script"], "-"
    ])
    vs_pipe = subprocess.Popen(["vspipe"] + vs + [
        "--end", "0", cfg["vs"]["script"], "-"
    ], stdout=open(os.devnull, "w"))
    vs_pipe.wait()
    if vs_pipe.returncode != 0:
        log.critical("An unexpected error occurred when jump-starting VS Pipe...")
    log.info(" + Success")

    t0 = time.time()

    log.info("Starting VS Pipe render pipeline...")
    vs_pipe = subprocess.Popen(["vspipe"] + vs + [cfg["vs"]["script"], "-"], stdout=subprocess.PIPE)
    log.info("Starting FFMPEG encoding intake...")
    ffmpeg_pipe = subprocess.Popen(["ffmpeg"] + ffmpeg + [str(out)], stdin=vs_pipe.stdout)

    vs_pipe.wait()
    log.info(" + vs-pipe has rendered and passed all frames to ffmpeg")
    ffmpeg_pipe.wait()
    log.info(" + ffmpeg has encoded all rendered frames")

    for e in ["mpg", "mpeg", "d2v", "log", f"pfpsreset{file.suffix}.lwi", f"pfpsreset{file.suffix}"]:
        file.with_suffix(f".{e}").unlink(missing_ok=True)
    Path(f"{file}.lwi").unlink(missing_ok=True)

    log.info("Finished Encoding: %s", file)
    log.info("It took %d minutes" % (int(time.time() - t0) / 60))


@click.command(context_settings=dict(
    help_option_names=["-?", "-h", "--help"],
    max_content_width=116,  # max PEP8 line-width, -4 to adjust for initial indent
    default_map=cfg.get("general") or {}
))
@click.argument("path", type=Path)
@click.option("-e", "--ext", type=str, default="mkv",
              help="Only files with this extension are to be encoded when the provided path is a Directory.")
@click.option("-n", "--neighbour", is_flag=True, default=False,
              help="Act as if the Current Working Directory is where the file being encoded is located.")
@click.option("-f", "--filename", type=str, default="{name}-encoded",
              help="Choose the filename the encoded files should have.")
@click.option("-v", "--verbose", count=True,
              help="Verbosity level. INFO (unset), DEBUG, WARNING, ERROR, CRITICAL. e.g. -v == DEBUG -vvv == ERROR.")
def main(path: Path, ext: str, neighbour: bool, filename: str, verbose: int):
    if verbose > 4 or verbose < 0:
        raise click.BadParameter("Must be between 0 (no -v) and 4 (-vvvv).", param_hint="verbose")

    verbose = (verbose + 1) * 10
    verbose = {10: logging.INFO, 20: logging.DEBUG}.get(verbose, verbose)  # logging has 10/20 swapped, re-swap
    log = logging.getLogger()
    setup_log(log, level=verbose)

    log.info("Config file location: %s", HERE.parent / "config.toml")
    if not cfg:
        log.critical("Config file is invalid, empty, or not yet created.")

    if not path.exists():
        log.critical(f"The provided path does not exist. ({path})")

    if path.is_dir():
        files = sorted(list(path.glob(f"**/*.{ext}")), key=lambda p: p.name)
    else:
        files = [path]

    if not files:
        log.critical(f"The provided path has no .{ext} files. ({path})")
    if len(files) == 1:
        log.info(f"Encoding: {path}")
    else:
        log.info(f"Encoding {len(files)} .{ext} files in: {path}")

    for file in files:
        formatted_filename = filename.format_map(defaultdict(str, name=file.stem, ext=file.suffix.lstrip(".")))
        if neighbour:
            out = file.parent
        else:
            out = Path.cwd()
        i = 0
        new_filename = formatted_filename
        while (out / new_filename).with_suffix(".mkv").exists():  # don't shadow existing file, use `... (n).ext`
            i += 1
            new_filename = formatted_filename + f" ({i})"
        out = (out / new_filename).with_suffix(".mkv")

        encode(file, out)


if __name__ == "__main__":
    main()
